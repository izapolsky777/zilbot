const API_BASE = "/dashboard/api";
const DATA_URL = `${API_BASE}/inbox`;
const REFRESH_MS = 30000;

const els = {
  statusText: document.querySelector("#statusText"),
  assignedCount: document.querySelector("#assignedCount"),
  myPromisesCount: document.querySelector("#myPromisesCount"),
  peopleCount: document.querySelector("#peopleCount"),
  assignmentsBoard: document.querySelector("#assignmentsBoard"),
  peopleList: document.querySelector("#peopleList"),
  myPromisesList: document.querySelector("#myPromisesList"),
  peopleDialog: document.querySelector("#peopleDialog"),
  peopleDialogClose: document.querySelector("#peopleDialogClose"),
  emptyTemplate: document.querySelector("#emptyTemplate"),
};

let lastSignature = "";

async function refresh(force = false) {
  try {
    const response = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const payload = await response.json();
    const items = Array.isArray(payload.open_items) ? payload.open_items : [];
    const archivedItems = Array.isArray(payload.archived_items) ? payload.archived_items : [];
    const people = Array.isArray(payload.people) ? payload.people : [];
    const signature = JSON.stringify({ items, archivedItems, people });

    if (signature !== lastSignature && (force || !isEditing())) {
      render(items, archivedItems, people);
      lastSignature = signature;
    }

    els.statusText.textContent = `Обновлено ${formatTime(new Date())}`;
  } catch (error) {
    els.statusText.textContent = "Не могу прочитать данные";
    console.error(error);
  }
}

function render(items, archivedItems, people) {
  const assignments = items.filter((item) => item.kind === "assignment");
  const archivedAssignments = archivedItems.filter((item) => item.kind === "assignment");
  const promises = items.filter((item) => item.kind === "promise");
  const myPromises = promises.filter((item) => item.actor_is_owner === true);

  els.assignedCount.textContent = assignments.length;
  els.myPromisesCount.textContent = myPromises.length;
  els.peopleCount.textContent = people.length;

  renderAssignments(assignments, archivedAssignments);
  renderPeople(people);
  renderTaskList(els.myPromisesList, myPromises, { mode: "mine" });
}

function renderPeople(people) {
  els.peopleList.replaceChildren();
  if (people.length === 0) {
    els.peopleList.append(emptyNode());
    return;
  }

  for (const person of people) {
    const row = document.createElement("article");
    row.className = "person-row";
    row.innerHTML = `
      <div class="editable-head">
        <div>
          <strong>${escapeHtml(person.label || person.raw_name)}</strong>
          <span>${escapeHtml(person.raw_name)}</span>
        </div>
        <button class="edit-button" type="button" data-edit-person title="Редактировать обозначение">✎</button>
      </div>
      <div class="inline-save person-editor">
        <input class="text-input" data-person-label="${escapeAttr(person.person_key)}" value="${escapeAttr(person.label)}" placeholder="Мое имя для человека" />
        <button class="icon-button" type="button" data-save-person="${escapeAttr(person.person_key)}" title="Сохранить обозначение">✓</button>
      </div>
      <label class="field-label person-editor">
        <span>Алиасы для голоса</span>
        <div class="inline-save">
          <input class="text-input" data-person-aliases="${escapeAttr(person.person_key)}" value="${escapeAttr(person.aliases || "")}" placeholder="Ванька, Лукин, Иван Л." />
          <button class="icon-button" type="button" data-save-aliases="${escapeAttr(person.person_key)}" title="Сохранить алиасы">✓</button>
        </div>
      </label>
      <button class="cancel-button person-editor" type="button" data-cancel-edit>Отмена</button>
    `;
    els.peopleList.append(row);
  }
}

function renderAssignments(assignments, archivedAssignments = []) {
  els.assignmentsBoard.replaceChildren();
  if (assignments.length === 0 && archivedAssignments.length === 0) {
    els.assignmentsBoard.append(emptyNode());
    return;
  }

  const groups = new Map();
  for (const item of [...assignments, ...archivedAssignments]) {
    const key = item.assignee_key || "unassigned";
    if (!groups.has(key)) {
      groups.set(key, {
        personKey: key,
        rawName: item.assignee_raw || item.assignee_name || "Без исполнителя",
        label: item.person_label || "",
        aliases: item.person_aliases || "",
        tasks: [],
        archivedTasks: [],
      });
    }
    if (item.archived_at) {
      groups.get(key).archivedTasks.push(item);
    } else {
      groups.get(key).tasks.push(item);
    }
  }

  const unrecognizedGroup = groups.get("unassigned");
  if (unrecognizedGroup) {
    els.assignmentsBoard.append(personCard(unrecognizedGroup, { unrecognized: true }));
  }

  for (const group of [...groups.values()].filter((group) => group.personKey !== "unassigned").sort(byGroupName)) {
    els.assignmentsBoard.append(personCard(group));
  }
}

function personCard(group, options = {}) {
    const aliasChips = parseAliasList(group.aliases)
      .map((alias) => `<span class="alias-chip">${escapeHtml(alias)}</span>`)
      .join("");
    const card = document.createElement("article");
    card.className = `person-card ${options.unrecognized ? "person-card--unrecognized" : ""}`;
    card.dataset.dropTarget = options.unrecognized ? "" : group.rawName;

    const head = document.createElement("header");
    head.className = "person-card__head";
    head.innerHTML = `
      <div class="person-title-row">
        <div>
          <h3 class="person-card__name">${escapeHtml(options.unrecognized ? "Нераспознанные задачи" : group.label || group.rawName)}</h3>
          <div class="person-card__meta">
            <span class="chip chip--accent">${group.tasks.length} ${plural(group.tasks.length, "задача", "задачи", "задач")}</span>
            <span class="chip">${group.archivedTasks.length} в архиве</span>
            <span>${escapeHtml(options.unrecognized ? "без исполнителя" : group.rawName)}</span>
            ${options.unrecognized || !aliasChips ? "" : `<span class="alias-list">${aliasChips}</span>`}
          </div>
        </div>
        ${options.unrecognized ? "" : `<button class="edit-button" type="button" data-edit-person title="Редактировать обозначение">✎</button>`}
      </div>
      ${options.unrecognized ? "" : `<label class="field-label person-editor">
        <span>Мое обозначение</span>
        <div class="inline-save">
          <input class="text-input" data-person-label="${escapeAttr(group.personKey)}" value="${escapeAttr(group.label)}" placeholder="Например: Иван, логистика" />
          <button class="icon-button" type="button" data-save-person="${escapeAttr(group.personKey)}" title="Сохранить обозначение">✓</button>
        </div>
      </label>
      <label class="field-label person-editor">
        <span>Алиасы для голоса</span>
        <div class="inline-save">
          <input class="text-input" data-person-aliases="${escapeAttr(group.personKey)}" value="${escapeAttr(group.aliases || "")}" placeholder="Ванька, Лукин, Иван Л." />
          <button class="icon-button" type="button" data-save-aliases="${escapeAttr(group.personKey)}" title="Сохранить алиасы">✓</button>
        </div>
      </label>
      <button class="cancel-button person-editor" type="button" data-cancel-edit>Отмена</button>`}
    `;

    const tasks = document.createElement("div");
    tasks.className = "person-card__tasks";
    if (group.tasks.length === 0) {
      tasks.append(emptySmall(options.unrecognized ? "Здесь появятся задачи без исполнителя" : "Открытых задач нет"));
    }
    let pointNumber = 1;
    for (const task of group.tasks.sort(byDueThenNewest)) {
      tasks.append(taskCard(task, { start: pointNumber }));
      pointNumber += Math.max(1, (task.points || [task.summary]).length);
    }

    if (group.archivedTasks.length > 0) {
      const archive = document.createElement("details");
      archive.className = "archive-block";
      archive.innerHTML = `<summary>Архив (${group.archivedTasks.length})</summary>`;
      const archiveList = document.createElement("div");
      archiveList.className = "archive-list";
      let archiveNumber = 1;
      for (const task of group.archivedTasks.sort(byDueThenNewest)) {
        archiveList.append(taskCard(task, { start: archiveNumber, archived: true }));
        archiveNumber += Math.max(1, (task.points || [task.summary]).length);
      }
      archive.append(archiveList);
      tasks.append(archive);
    }

    card.append(head, tasks);
    return card;
}

function renderTaskList(container, items, options) {
  container.replaceChildren();
  if (items.length === 0) {
    container.append(emptyNode());
    return;
  }

  let pointNumber = 1;
  for (const item of [...items].sort(byDueThenNewest)) {
    container.append(taskCard(item, { ...options, start: pointNumber }));
    pointNumber += Math.max(1, (item.points || [item.summary]).length);
  }
}

function taskCard(item, options = {}) {
  const urgency = options.archived ? "normal" : dueUrgency(item);
  const task = document.createElement("article");
  task.className = `task ${options.mode === "mine" ? "task--mine" : ""} ${
    options.mode === "promise" ? "task--promise" : ""
  } ${options.archived ? "task--archived" : ""} ${urgency === "overdue" ? "task--overdue" : ""} ${
    urgency === "soon" ? "task--soon" : ""
  }`;
  task.dataset.itemKey = item.id;
  task.dataset.targetLabel = item.target_label || "";
  if (item.kind === "assignment" && !options.archived) {
    task.draggable = true;
  }

  const actor = item.actor_label || item.actor_name || item.actor_username || "Неизвестно";
  const meta = [];
  if (item.kind === "promise") {
    meta.push(`от ${actor}`);
    meta.push(`кому: ${item.target_label || "не указано"}`);
  } else {
    meta.push(`поручил: ${actor}`);
  }
  if (item.due_text) meta.push(`срок: ${item.due_text}`);
  if (item.chat_title) meta.push(item.chat_title);
  if (item.created_at) meta.push(formatDate(item.created_at));
  if (item.archived_at) meta.push(`архив: ${formatDate(item.archived_at)}`);
  const completeButton = options.archived
    ? ""
    : `<button class="complete-button" type="button" data-archive-item title="Выполнено, перенести в архив">✓</button>`;
  const restoreButton = options.archived
    ? `<button class="restore-button" type="button" data-unarchive-item title="Вернуть из архива">↩</button>`
    : "";

  task.innerHTML = `
    <div class="task-view">
      <div class="editable-head">
        <ol class="task-points" start="${Number(options.start || 1)}">
          ${(item.points || [item.summary]).map((point) => `<li>${escapeHtml(point)}</li>`).join("")}
        </ol>
        <div class="task-actions">
          ${completeButton}
          ${restoreButton}
          <button class="edit-button" type="button" data-edit-item title="Редактировать задачу">✎</button>
        </div>
      </div>
      <div class="task__meta">
        ${meta.map((part) => `<span class="chip">${escapeHtml(part)}</span>`).join("")}
      </div>
    </div>
    <div class="task-editor">
      <label class="field-label">
        <span>Пункт задачи</span>
        <textarea class="text-input text-area" data-edit-summary>${escapeHtml(item.summary || "")}</textarea>
      </label>
      <div class="edit-grid">
        <label class="field-label">
          <span>${item.kind === "promise" ? "Кому обещано" : "Исполнитель"}</span>
          <input class="text-input" data-edit-target value="${escapeAttr(item.target_label || item.assignee_raw || "")}" placeholder="Не указано" />
        </label>
        <label class="field-label">
          <span>Срок</span>
          <input class="text-input" data-edit-due value="${escapeAttr(item.due_text || "")}" placeholder="Например: завтра, до 18:00" />
        </label>
      </div>
      <div class="editor-actions">
        <button class="save-button" type="button" data-save-item title="Сохранить">✓</button>
        <button class="cancel-button" type="button" data-cancel-edit>Отмена</button>
      </div>
    </div>
  `;

  return task;
}

document.addEventListener("click", async (event) => {
  const openPeopleButton = event.target.closest("[data-open-people]");
  if (openPeopleButton) {
    els.peopleDialog.showModal();
    return;
  }

  const editPersonButton = event.target.closest("[data-edit-person]");
  if (editPersonButton) {
    editPersonButton.closest(".person-card__head, .person-row").classList.add("is-editing");
    return;
  }

  const editItemButton = event.target.closest("[data-edit-item]");
  if (editItemButton) {
    editItemButton.closest(".task").classList.add("is-editing");
    return;
  }

  const cancelButton = event.target.closest("[data-cancel-edit]");
  if (cancelButton) {
    cancelEdit(cancelButton.closest(".is-editing"));
    return;
  }

  const personButton = event.target.closest("[data-save-person]");
  if (personButton) {
    const personKey = personButton.dataset.savePerson;
    const input = personButton.closest(".inline-save").querySelector("[data-person-label]");
    await postJson(`${API_BASE}/person-label`, { person_key: personKey, label: input ? input.value : "" });
    await refreshAfterSave(personButton);
    return;
  }

  const aliasesButton = event.target.closest("[data-save-aliases]");
  if (aliasesButton) {
    const personKey = aliasesButton.dataset.saveAliases;
    const input = aliasesButton.closest(".inline-save").querySelector("[data-person-aliases]");
    await postJson(`${API_BASE}/person-aliases`, { person_key: personKey, aliases: input ? input.value : "" });
    await refreshAfterSave(aliasesButton);
    return;
  }

  const itemButton = event.target.closest("[data-save-item]");
  if (itemButton) {
    const card = itemButton.closest(".task");
    await postJson(`${API_BASE}/item-edit`, {
      item_key: card.dataset.itemKey,
      summary: card.querySelector("[data-edit-summary]").value,
      target_label: card.querySelector("[data-edit-target]").value,
      due_text: card.querySelector("[data-edit-due]").value,
    });
    await refreshAfterSave(itemButton);
    return;
  }

  const archiveButton = event.target.closest("[data-archive-item]");
  if (archiveButton) {
    const card = archiveButton.closest(".task");
    await postJson(`${API_BASE}/item-archive`, { item_key: card.dataset.itemKey });
    await refreshAfterSave(archiveButton);
    return;
  }

  const unarchiveButton = event.target.closest("[data-unarchive-item]");
  if (unarchiveButton) {
    const card = unarchiveButton.closest(".task");
    await postJson(`${API_BASE}/item-unarchive`, { item_key: card.dataset.itemKey });
    await refreshAfterSave(unarchiveButton);
  }
});

els.peopleDialogClose.addEventListener("click", () => {
  els.peopleDialog.close();
});

els.peopleDialog.addEventListener("click", (event) => {
  if (event.target === els.peopleDialog) {
    els.peopleDialog.close();
  }
});

document.addEventListener("dragstart", (event) => {
  const task = event.target.closest(".task[draggable='true']");
  if (!task) return;
  task.classList.add("is-dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", task.dataset.itemKey);
});

document.addEventListener("dragend", (event) => {
  const task = event.target.closest(".task");
  if (task) task.classList.remove("is-dragging");
  for (const target of document.querySelectorAll(".is-drop-target")) {
    target.classList.remove("is-drop-target");
  }
});

document.addEventListener("dragover", (event) => {
  const target = event.target.closest("[data-drop-target]");
  if (!target) return;
  event.preventDefault();
  target.classList.add("is-drop-target");
  event.dataTransfer.dropEffect = "move";
});

document.addEventListener("dragleave", (event) => {
  const target = event.target.closest("[data-drop-target]");
  if (!target || target.contains(event.relatedTarget)) return;
  target.classList.remove("is-drop-target");
});

document.addEventListener("drop", async (event) => {
  const target = event.target.closest("[data-drop-target]");
  if (!target) return;
  event.preventDefault();
  target.classList.remove("is-drop-target");
  const itemKey = event.dataTransfer.getData("text/plain");
  if (!itemKey) return;
  await postJson(`${API_BASE}/item-move`, {
    item_key: itemKey,
    target_label: target.dataset.dropTarget || "",
  });
  lastSignature = "";
  await refresh(true);
});

function cancelEdit(container) {
  if (!container) return;
  for (const input of container.querySelectorAll("input, textarea")) {
    input.value = input.defaultValue;
  }
  container.classList.remove("is-editing");
}

async function refreshAfterSave(button) {
  const original = button.textContent;
  button.textContent = "OK";
  lastSignature = "";
  if (document.activeElement) document.activeElement.blur();
  await refresh(true);
  setTimeout(() => {
    button.textContent = original;
  }, 900);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function emptyNode() {
  return els.emptyTemplate.content.firstElementChild.cloneNode(true);
}

function emptySmall(text) {
  const node = document.createElement("div");
  node.className = "empty empty--small";
  node.innerHTML = `<span>${escapeHtml(text)}</span>`;
  return node;
}

function parseAliasList(value) {
  return String(value || "")
    .split(",")
    .map((alias) => alias.trim())
    .filter(Boolean);
}

function isEditing() {
  return Boolean(document.querySelector(".is-editing"));
}

function byGroupName(a, b) {
  return (a.label || a.rawName).localeCompare(b.label || b.rawName, "ru");
}

function byDueThenNewest(a, b) {
  const dueDelta = dueRank(a) - dueRank(b);
  if (dueDelta !== 0) return dueDelta;
  return String(b.created_at || "").localeCompare(String(a.created_at || ""));
}

function dueRank(item) {
  const due = parseDueText(item.due_text || item.summary || "", item.created_at);
  return due === null ? Number.MAX_SAFE_INTEGER : due.getTime();
}

function dueUrgency(item) {
  const due = parseDueText(item.due_text || item.summary || "", item.created_at);
  if (!due) return "normal";

  const now = new Date();
  if (due.getTime() < now.getTime()) return "overdue";
  const soonLimit = new Date(now.getTime() + 36 * 60 * 60 * 1000);
  return due.getTime() <= soonLimit.getTime() ? "soon" : "normal";
}

function parseDueText(value, createdAt = "") {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return null;

  const reference = parseCreatedAt(createdAt) || new Date();
  const base = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate());

  let parsedDate = null;
  if (hasRussianWord(text, "сегодня")) parsedDate = addDays(base, 0);
  if (hasRussianWord(text, "завтра")) parsedDate = addDays(base, 1);
  if (hasRussianWord(text, "послезавтра")) parsedDate = addDays(base, 2);

  const relativeMatch = text.match(/через\s+(\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+дн/i);
  if (relativeMatch) {
    parsedDate = addDays(base, russianNumber(relativeMatch[1]));
  }

  const dateMatch = text.match(/(?:до|к)?\s*([0-3]?\d)[./-]([01]?\d)(?:[./-](\d{2,4}))?/i);
  if (dateMatch) {
    const day = Number(dateMatch[1]);
    const month = Number(dateMatch[2]) - 1;
    let year = dateMatch[3] ? Number(dateMatch[3]) : reference.getFullYear();
    if (year < 100) year += 2000;
    const date = new Date(year, month, day);
    if (!Number.isNaN(date.getTime())) parsedDate = date;
  }

  const timeSource = dateMatch ? text.replace(dateMatch[0], " ") : text;
  const timeMatch = timeSource.match(/(?:до|к|в)\s*([0-2]?\d)(?:[:.]([0-5]\d))?/i);
  if (!parsedDate && timeMatch) parsedDate = new Date(base);
  if (timeMatch) {
    parsedDate.setHours(Number(timeMatch[1]), Number(timeMatch[2] || "0"), 0, 0);
  } else if (parsedDate) {
    parsedDate.setHours(23, 59, 59, 999);
  }

  return parsedDate && !Number.isNaN(parsedDate.getTime()) ? parsedDate : null;
}

function parseCreatedAt(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function hasRussianWord(text, word) {
  return new RegExp(`(^|[^а-яё])${word}([^а-яё]|$)`, "i").test(text);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + Number(days || 0));
  return next;
}

function russianNumber(value) {
  const words = {
    один: 1,
    два: 2,
    три: 3,
    четыре: 4,
    пять: 5,
    шесть: 6,
    семь: 7,
    восемь: 8,
    девять: 9,
    десять: 10,
  };
  return Number(value) || words[value] || 0;
}

function formatDate(value) {
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTime(date) {
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function plural(count, one, few, many) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}

refresh();
setInterval(refresh, REFRESH_MS);
