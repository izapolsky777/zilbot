const els = {
  sourceCount: document.querySelector("#sourceCount"),
  apiStatus: document.querySelector("#apiStatus"),
  cacheTtl: document.querySelector("#cacheTtl"),
  sourceList: document.querySelector("#sourceList"),
  countryTabs: [...document.querySelectorAll(".country-tab")],
  countrySourceBadge: document.querySelector("#countrySourceBadge"),
  capacityValue: document.querySelector("#capacityValue"),
  registeredValue: document.querySelector("#registeredValue"),
  registeredShare: document.querySelector("#registeredShare"),
  supplyValue: document.querySelector("#supplyValue"),
  gapValue: document.querySelector("#gapValue"),
  gapLabel: document.querySelector("#gapLabel"),
  trafficDrivers: document.querySelector("#trafficDrivers"),
  trafficShare: document.querySelector("#trafficShare"),
  planFactTripsChart: document.querySelector("#planFactTripsChart"),
  funnelChart: document.querySelector("#funnelChart"),
  driverChart: document.querySelector("#driverChart"),
  tripsChart: document.querySelector("#tripsChart"),
  parkList: document.querySelector("#parkList"),
  refreshButton: document.querySelector("#refreshButton"),
  emptyTemplate: document.querySelector("#emptyTemplate"),
};

const countries = {
  belarus: {
    source: "Беларусь Supply",
    trafficDrivers: 297,
    activeSupplyHours: 353,
    gapLabel: "потенциал к добору",
    funnel: [
      { label: "Capacity", value: 1618, color: "#1c7c69" },
      { label: "В системе", value: 718, color: "#315e9c" },
      { label: "Supply hours", value: 353, color: "#b76a22" },
      { label: "С гарантией", value: 281, color: "#5b6472" },
    ],
    drivers: [
      ["20-апр", 2, 2, 2],
      ["23-апр", 228, 160, 126],
      ["26-апр", 286, 223, 192],
      ["29-апр", 347, 236, 169],
      ["2-мая", 451, 194, 157],
      ["5-мая", 512, 249, 195],
      ["8-мая", 618, 267, 205],
      ["11-мая", 718, 353, 281],
    ],
    trips: [
      ["20-апр", 36, 16],
      ["23-апр", 187, 138],
      ["26-апр", 461, 241],
      ["29-апр", 1215, 788],
      ["2-мая", 1340, 837],
      ["5-мая", 2397, 1493],
      ["8-мая", 7919, 3112],
      ["11-мая", 3788, 2576],
    ],
    planFactTrips: [
      ["20-апр", 12, 16],
      ["23-апр", 244, 138],
      ["26-апр", 259, 241],
      ["29-апр", 968, 788],
      ["2-мая", 900, 837],
      ["5-мая", 1825, 1493],
      ["8-мая", 2253, 3112],
      ["11-мая", 2253, 2576],
    ],
    parks: [
      { name: "НикВаТакс", manager: "Вика", capacity: 260, fact: 125, potential: 135 },
      { name: "Первая доставка", manager: "Илья", capacity: 75, fact: 13, potential: 62 },
      { name: "ООО Сонрер", manager: "Илья", capacity: 80, fact: 17, potential: 63 },
      { name: "Нейропарк", manager: "Илья", capacity: 70, fact: 0, potential: 70 },
      { name: "ЛБП", manager: "Илья", capacity: 60, fact: 0, potential: 60 },
      { name: "ООО МАТУРХАН", manager: "Вика", capacity: 50, fact: 21, potential: 29 },
      { name: "Корвектор", manager: "Вика", capacity: 50, fact: 34, potential: 16 },
      { name: "Ситилайнер", manager: "Илья", capacity: 45, fact: 0, potential: 45 },
    ],
  },
  uzbekistan: {
    source: "Узбекистан Supply",
    trafficDrivers: 7599,
    activeSupplyHours: 8244,
    gapLabel: "до плана месяца",
    funnel: [
      { label: "План drivers", value: 19426, color: "#1c7c69" },
      { label: "В системе", value: 14217, color: "#315e9c" },
      { label: "Supply hours", value: 8244, color: "#b76a22" },
      { label: "С гарантией", value: 7080, color: "#5b6472" },
    ],
    drivers: [
      ["1-мая", 12990, 7438, 6425],
      ["3-мая", 13165, 5978, 4759],
      ["5-мая", 13339, 7620, 6454],
      ["7-мая", 13652, 7836, 6708],
      ["9-мая", 13975, 6714, 5358],
      ["10-мая", 14038, 5986, 4625],
      ["11-мая", 14095, 7426, 5874],
      ["12-мая", 14217, 8244, 7080],
    ],
    trips: [
      ["1-мая", 159359, 118587],
      ["3-мая", 108982, 83055],
      ["5-мая", 158297, 117280],
      ["7-мая", 158939, 123981],
      ["9-мая", 119221, 94970],
      ["10-мая", 98648, 78331],
      ["11-мая", 116605, 95574],
      ["12-мая", 162238, 127386],
    ],
    planFactTrips: [
      ["1-мая", 106941, 118587],
      ["3-мая", 93229, 83055],
      ["5-мая", 108765, 117280],
      ["7-мая", 113408, 123981],
      ["9-мая", 126440, 94970],
      ["10-мая", 107780, 78331],
      ["11-мая", 102444, 95574],
      ["12-мая", 125057, 127386],
    ],
    parks: [
      { name: "IDRIVER MCHJ", manager: "Ташкент · подключение" },
      { name: "EATSEXPRESS", manager: "Ташкент · подключение" },
      { name: "NUR TAXI", manager: "Ташкент · подключение" },
      { name: "PRIME (TOLMAN TAXI)", manager: "Ташкент · подключение" },
      { name: "Daks-Drive", manager: "Ташкент · подключение" },
      { name: "Imkon Taxi", manager: "Ташкент · подключение" },
    ],
  },
  kyrgyzstan: {
    source: "Кыргызстан Supply",
    trafficDrivers: 641,
    activeSupplyHours: 746,
    gapLabel: "потенциал к добору",
    funnel: [
      { label: "Capacity", value: 2300, color: "#1c7c69" },
      { label: "В системе", value: 2108, color: "#315e9c" },
      { label: "Supply hours", value: 746, color: "#b76a22" },
      { label: "С гарантией", value: 587, color: "#5b6472" },
    ],
    drivers: [
      ["1-мая", 1668, 549, 338],
      ["3-мая", 1766, 484, 317],
      ["5-мая", 1837, 674, 439],
      ["7-мая", 2006, 698, 495],
      ["9-мая", 2041, 635, 456],
      ["10-мая", 2093, 583, 449],
      ["11-мая", 2101, 739, 571],
      ["12-мая", 2108, 746, 587],
    ],
    trips: [
      ["1-мая", 7793, 4197],
      ["3-мая", 6049, 3828],
      ["5-мая", 7583, 5398],
      ["7-мая", 8124, 6116],
      ["9-мая", 8334, 5816],
      ["10-мая", 9371, 6179],
      ["11-мая", 17910, 7625],
      ["12-мая", 16793, 7473],
    ],
    planFactTrips: [
      ["1-мая", 3923, 4197],
      ["3-мая", 2906, 3828],
      ["5-мая", 4140, 5398],
      ["7-мая", 4868, 6116],
      ["9-мая", 4765, 5816],
      ["10-мая", 4418, 6179],
      ["11-мая", 5801, 7625],
      ["12-мая", 6590, 7473],
    ],
    parks: [
      { name: "АТАМАН (Prime)", manager: "КР", capacity: 1000, fact: 33, potential: 967 },
      { name: "Global Driver", manager: "КР", capacity: 1000, fact: 59, potential: 941 },
      { name: "Элпек", manager: "КР", capacity: 200, fact: 1, potential: 199 },
      { name: "Central Office", manager: "КР", capacity: 100, fact: 104, potential: 0 },
      { name: "ДАКС драйв", manager: "КР", capacity: 50, fact: 50, potential: 0 },
    ],
  },
};

let activeCountryId = "belarus";

async function refresh() {
  els.refreshButton.disabled = true;
  try {
    const response = await fetch(`/metrics/api/status?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    els.apiStatus.textContent = "ошибка";
    els.sourceList.replaceChildren(emptyNode("Не удалось прочитать статус метрик."));
    console.error(error);
  } finally {
    els.refreshButton.disabled = false;
  }
}

function render(status) {
  const sources = Array.isArray(status.sources) ? status.sources : [];
  els.sourceCount.textContent = String(sources.length);
  els.apiStatus.textContent =
    status.cache_file_exists ? "кэш готов" : "нет кэша";
  els.cacheTtl.textContent =
    status.cache_file_age_seconds === null || status.cache_file_age_seconds === undefined
      ? `${status.cache_ttl_seconds || 300} сек`
      : `${status.cache_file_age_seconds} сек назад`;

  els.sourceList.replaceChildren();
  if (sources.length === 0) {
    els.sourceList.append(emptyNode("Источники пока не настроены."));
    return;
  }

  for (const source of sources) {
    els.sourceList.append(sourceCard(source, status));
  }
}

function renderPreview() {
  const preview = countries[activeCountryId] || countries.belarus;
  const capacity = preview.funnel[0]?.value || 0;
  const registered = preview.funnel[1]?.value || 0;
  const supply = preview.funnel[2]?.value || 0;
  const gap = Math.max(0, capacity - registered);
  const trafficRate = preview.activeSupplyHours > 0 ? Math.round((preview.trafficDrivers / preview.activeSupplyHours) * 100) : 0;
  const registeredRate = capacity > 0 ? Math.round((registered / capacity) * 100) : 0;

  els.countrySourceBadge.textContent = preview.source;
  els.capacityValue.textContent = formatNumber(capacity);
  els.registeredValue.textContent = formatNumber(registered);
  els.registeredShare.textContent = `${registeredRate}% от capacity`;
  els.supplyValue.textContent = formatNumber(supply);
  els.gapValue.textContent = formatNumber(gap);
  els.gapLabel.textContent = preview.gapLabel;
  els.trafficDrivers.textContent = formatNumber(preview.trafficDrivers);
  els.trafficShare.textContent = `${trafficRate}% от active SH`;

  renderLineChart({
    el: els.planFactTripsChart,
    rows: preview.planFactTrips,
    series: [
      { label: "план поездок", index: 1, color: "#b76a22" },
      { label: "факт выполнено", index: 2, color: "#1c7c69" },
    ],
    max: chartMax(preview.planFactTrips, [1, 2]),
  });
  renderFunnel(preview, gap);
  renderLineChart({
    el: els.driverChart,
    rows: preview.drivers,
    series: [
      { label: "в системе", index: 1, color: "#1c7c69" },
      { label: "активные SH", index: 2, color: "#315e9c" },
      { label: "с гарантией", index: 3, color: "#b76a22" },
    ],
    max: chartMax(preview.drivers, [1, 2, 3]),
  });
  renderLineChart({
    el: els.tripsChart,
    rows: preview.trips,
    series: [
      { label: "заказы всего", index: 1, color: "#315e9c" },
      { label: "выполнены", index: 2, color: "#1c7c69" },
    ],
    max: chartMax(preview.trips, [1, 2]),
  });
  renderParks(preview);
}

function renderFunnel(preview, gap) {
  const max = Math.max(...preview.funnel.map((item) => item.value));
  const bars = preview.funnel
    .map((item, index) => {
      const width = Math.max(8, (item.value / max) * 560);
      const y = 34 + index * 48;
      return `
        <text class="chart-label" x="0" y="${y + 15}">${escapeHtml(item.label)}</text>
        <rect x="116" y="${y}" width="${width}" height="28" rx="7" fill="${item.color}" opacity="0.92"></rect>
        <text class="chart-value" x="${126 + width}" y="${y + 19}">${formatNumber(item.value)}</text>
      `;
    })
    .join("");
  els.funnelChart.innerHTML = `
    <svg viewBox="0 0 760 240" role="img" aria-label="Capacity funnel">
      ${bars}
      <text class="axis-label" x="116" y="232">разрыв capacity → факт: ${formatNumber(gap)} водителей</text>
    </svg>
  `;
}

function renderLineChart({ el, rows, series, max }) {
  const width = 680;
  const height = 230;
  const left = 40;
  const right = 18;
  const top = 20;
  const bottom = 38;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const x = (index) => left + (plotW / Math.max(1, rows.length - 1)) * index;
  const y = (value) => top + plotH - (Number(value || 0) / max) * plotH;
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((tick) => {
      const yy = top + plotH - tick * plotH;
      return `<line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}" stroke="#dfe2dd"/><text class="axis-label" x="0" y="${yy + 4}">${formatNumber(Math.round(max * tick))}</text>`;
    })
    .join("");
  const lines = series
    .map((item) => {
      const points = rows.map((row, index) => `${x(index)},${y(row[item.index])}`).join(" ");
      return `<polyline points="${points}" fill="none" stroke="${item.color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
    })
    .join("");
  const dots = series
    .map((item) =>
      rows
        .map((row, index) => `<circle cx="${x(index)}" cy="${y(row[item.index])}" r="4" fill="${item.color}"></circle>`)
        .join(""),
    )
    .join("");
  const labels = rows
    .map((row, index) => `<text class="axis-label" x="${x(index) - 16}" y="${height - 10}">${escapeHtml(row[0])}</text>`)
    .join("");
  const legend = series
    .map(
      (item, index) =>
        `<circle cx="${left + index * 138}" cy="10" r="5" fill="${item.color}"></circle><text class="chart-label" x="${left + 10 + index * 138}" y="14">${escapeHtml(item.label)}</text>`,
    )
    .join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img">${legend}${grid}${lines}${dots}${labels}</svg>`;
}

function renderParks(preview) {
  els.parkList.replaceChildren();
  const parksByPotential = [...preview.parks]
    .map((park) => {
      const hasCapacity = Number(park.capacity || 0) > 0;
      const fact = Number(park.fact || 0);
      const potential = hasCapacity ? Math.max(0, park.potential ?? park.capacity - fact) : 0;
      const potentialRate = hasCapacity ? potential / park.capacity : 0;
      const factRate = hasCapacity ? fact / park.capacity : 0;
      return { ...park, fact, hasCapacity, potential, potentialRate, factRate };
    })
    .sort((left, right) => {
      if (left.hasCapacity !== right.hasCapacity) return left.hasCapacity ? -1 : 1;
      const scoreDelta = right.potential * (0.7 + right.potentialRate) - left.potential * (0.7 + left.potentialRate);
      if (scoreDelta !== 0) return scoreDelta;
      return right.potentialRate - left.potentialRate;
    });

  for (const park of parksByPotential) {
    const row = document.createElement("article");
    row.className = `park-row${park.hasCapacity ? "" : " park-row--pending"}`;
    const factWidth = park.hasCapacity ? Math.max(2, park.factRate * 100) : 0;
    const potentialWidth = Math.max(0, park.potentialRate * 100);
    const potentialPct = Math.round(park.potentialRate * 100);
    const factPct = Math.round(park.factRate * 100);
    const subtitle = park.hasCapacity
      ? `${escapeHtml(park.manager)} · остаток ${formatNumber(park.potential)} (${potentialPct}% capacity)`
      : `${escapeHtml(park.manager)} · capacity пока не размечен`;
    const numbers = park.hasCapacity
      ? `<strong>${formatNumber(park.potential)} из ${formatNumber(park.capacity)}</strong><span>${factPct}% заведено · ${potentialPct}% потенциал</span>`
      : `<strong>нет capacity</strong><span>покажем потенциал после разметки</span>`;
    row.innerHTML = `
      <div>
        <strong>${escapeHtml(park.name)}</strong>
        <span>${subtitle}</span>
      </div>
      <div class="park-track" title="Заведено и незакрытый потенциал">
        <i class="park-track__fact" style="--w: ${factWidth}%"></i>
        <i class="park-track__potential" style="--x: ${factWidth}%; --w: ${potentialWidth}%"></i>
      </div>
      <div class="park-numbers">
        ${numbers}
      </div>
    `;
    els.parkList.append(row);
  }
}

function sourceCard(source, status) {
  const sheets = Array.isArray(source.sheets) ? source.sheets : [];
  const card = document.createElement("article");
  card.className = "source-card";
  const apiReady = status.service_account_configured && status.service_account_file_exists;
  const cacheReady = status.cache_file_exists;
  card.innerHTML = `
    <div class="source-card__head">
      <div>
        <h3>${escapeHtml(source.name || "Google Sheet")}</h3>
        <code>${escapeHtml(source.spreadsheet_id || source.spreadsheet_url || "без id")}</code>
      </div>
      <span class="badge ${cacheReady ? "" : "badge--warn"}">${cacheReady ? "кэш на сервере" : "ожидает первый синк"}</span>
    </div>
    <div class="sheet-grid">
      ${sheets
        .map(
          (sheet) => `
            <div class="sheet-pill">
              <strong>${escapeHtml(sheet.name || "Лист")}</strong>
              <span>${escapeHtml(sheet.kind || "table")} · ${escapeHtml(sheet.range || "A1:ZZ1000")}</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
  return card;
}

function emptyNode(text) {
  const node = els.emptyTemplate.content.firstElementChild.cloneNode(true);
  node.textContent = text;
  return node;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
}

function chartMax(rows, indexes) {
  const max = rows.reduce((currentMax, row) => {
    const rowMax = Math.max(...indexes.map((index) => Number(row[index] || 0)));
    return Math.max(currentMax, rowMax);
  }, 0);
  return Math.max(1, Math.ceil(max * 1.12));
}

function setCountry(countryId) {
  if (!countries[countryId]) return;
  activeCountryId = countryId;
  for (const tab of els.countryTabs) {
    tab.classList.toggle("is-active", tab.dataset.country === countryId);
  }
  renderPreview();
}

els.refreshButton.addEventListener("click", refresh);
for (const tab of els.countryTabs) {
  tab.addEventListener("click", () => setCountry(tab.dataset.country));
}
renderPreview();
refresh();
