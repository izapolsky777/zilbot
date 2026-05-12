const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

const scoreEl = document.getElementById("score");
const bestScoreEl = document.getElementById("best-score");
const killsEl = document.getElementById("kills");
const overlayEl = document.getElementById("overlay");
const menuScreenEl = document.getElementById("menu-screen");
const gameoverScreenEl = document.getElementById("gameover-screen");
const finalScoreLineEl = document.getElementById("final-score-line");
const finalTitleEl = document.getElementById("final-title");
const restartButton = document.getElementById("restart-button");
const startButton = document.getElementById("start-button");
const saveForm = document.getElementById("save-form");
const saveButton = saveForm.querySelector("button[type='submit']");
const playerNameInput = document.getElementById("player-name");
const overlayLeaderboardEl = document.getElementById("overlay-leaderboard");
const touchControlsEl = document.querySelector(".touch-controls");
const touchJumpButton = document.getElementById("touch-jump");
const touchFireButton = document.getElementById("touch-fire");
const globalBackButton = document.getElementById("global-back-button");
const leaderboardSyncEl = document.getElementById("leaderboard-sync");
const inlineSyncNoteEl = document.getElementById("inline-sync-note");

const STORAGE_KEY = "contra-popki-leaderboard";
const SERVER_LEADERBOARD_URL =
  window.location.protocol === "file:" ? "" : "/game/api/leaderboard";
const WORLD_WIDTH = canvas.width;
const WORLD_HEIGHT = canvas.height;
const GROUND_Y = WORLD_HEIGHT - 96;

const input = {
  jumpQueued: false,
  shootQueued: false,
};

let state = createInitialState();
let leaderboard = loadLeaderboard();
let lastTimestamp = 0;
let appScreen = "menu";
let hasSavedCurrentResult = false;
let syncMessage = SERVER_LEADERBOARD_URL
  ? "Подключаюсь к серверу..."
  : "Локальный режим: общий рейтинг доступен в версии /game/";
const defaultSaveButtonLabel = saveButton.textContent;

const audio = createAudioController();
const previewMode = new URLSearchParams(window.location.search).get("preview");

function createAudioController() {
  let context = null;
  let masterGain = null;
  let musicTime = 0;
  let sequenceIndex = 0;

  const bassLine = [110, null, 110, null, 147, null, 165, null];
  const leadLine = [330, 392, 440, 392, 523, 440, 392, 330];

  function ensureReady() {
    if (!context) {
      const AudioCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtor) {
        return;
      }

      context = new AudioCtor();
      masterGain = context.createGain();
      masterGain.gain.value = 0.09;
      masterGain.connect(context.destination);
      musicTime = context.currentTime;
    }

    if (context.state === "suspended") {
      context.resume();
    }
  }

  function playTone({
    frequency,
    duration,
    type = "square",
    volume = 0.1,
    attack = 0.004,
    release = 0.06,
    when = null,
    sweep = null,
  }) {
    if (!context || !masterGain) {
      return;
    }

    const startAt = when ?? context.currentTime;
    const oscillator = context.createOscillator();
    const gain = context.createGain();

    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, startAt);
    if (sweep) {
      oscillator.frequency.exponentialRampToValueAtTime(
        Math.max(20, sweep),
        startAt + duration,
      );
    }

    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(volume, startAt + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration + release);

    oscillator.connect(gain);
    gain.connect(masterGain);
    oscillator.start(startAt);
    oscillator.stop(startAt + duration + release + 0.01);
  }

  function tickMusic() {
    if (!context || appScreen !== "running") {
      return;
    }

    const lookAhead = context.currentTime + 0.18;
    if (musicTime < context.currentTime) {
      musicTime = context.currentTime;
    }

    while (musicTime < lookAhead) {
      const bass = bassLine[sequenceIndex % bassLine.length];
      const lead = leadLine[sequenceIndex % leadLine.length];

      if (bass) {
        playTone({
          frequency: bass,
          duration: 0.13,
          type: "square",
          volume: 0.05,
          when: musicTime,
        });
      }

      playTone({
        frequency: lead,
        duration: 0.08,
        type: "triangle",
        volume: 0.035,
        when: musicTime + 0.02,
        sweep: lead * 0.96,
      });

      musicTime += 0.18;
      sequenceIndex += 1;
    }
  }

  return {
    ensureReady,
    resetMusic() {
      if (!context) {
        return;
      }

      musicTime = context.currentTime + 0.04;
      sequenceIndex = 0;
    },
    tickMusic,
    playStart() {
      ensureReady();
      playTone({ frequency: 392, duration: 0.06, volume: 0.08 });
      playTone({ frequency: 523, duration: 0.08, volume: 0.09, when: context.currentTime + 0.08 });
      playTone({ frequency: 659, duration: 0.1, volume: 0.1, when: context.currentTime + 0.16 });
    },
    playShoot() {
      ensureReady();
      playTone({ frequency: 780, duration: 0.04, volume: 0.06, sweep: 320 });
    },
    playJump() {
      ensureReady();
      playTone({ frequency: 240, duration: 0.07, type: "square", volume: 0.07, sweep: 420 });
    },
    playHit() {
      ensureReady();
      playTone({ frequency: 220, duration: 0.05, type: "triangle", volume: 0.06, sweep: 140 });
      playTone({ frequency: 165, duration: 0.08, type: "square", volume: 0.04, when: context.currentTime + 0.04 });
    },
    playGameOver() {
      ensureReady();
      playTone({ frequency: 294, duration: 0.08, type: "square", volume: 0.07 });
      playTone({ frequency: 196, duration: 0.1, type: "square", volume: 0.07, when: context.currentTime + 0.08 });
      playTone({ frequency: 131, duration: 0.16, type: "triangle", volume: 0.08, when: context.currentTime + 0.18 });
    },
    playMenuBlip() {
      ensureReady();
      playTone({ frequency: 523, duration: 0.05, type: "triangle", volume: 0.04 });
    },
  };
}

function loadLeaderboard() {
  if (SERVER_LEADERBOARD_URL) {
    return [];
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLeaderboard() {
  if (!SERVER_LEADERBOARD_URL) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(leaderboard.slice(0, 10)));
  }
}

function setSyncMessage(message) {
  syncMessage = message;
  if (leaderboardSyncEl) {
    leaderboardSyncEl.textContent = message;
  }
  if (inlineSyncNoteEl) {
    inlineSyncNoteEl.textContent = message;
  }
}

async function refreshLeaderboard() {
  if (!SERVER_LEADERBOARD_URL) {
    setSyncMessage(syncMessage);
    renderLeaderboard();
    return leaderboard;
  }

  try {
    setSyncMessage("Синхронизация с сервером...");
    const response = await fetch(`${SERVER_LEADERBOARD_URL}?t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    leaderboard = Array.isArray(payload.entries) ? payload.entries : [];
    setSyncMessage("Лидерборд синхронизирован");
    renderLeaderboard();
    return leaderboard;
  } catch (error) {
    console.error(error);
    setSyncMessage("Не могу обновить лидерборд");
    renderLeaderboard();
    return leaderboard;
  }
}

async function submitLeaderboardScore(name, score) {
  if (!SERVER_LEADERBOARD_URL) {
    leaderboard.push({ name, score });
    leaderboard.sort((a, b) => b.score - a.score);
    leaderboard = leaderboard.slice(0, 10);
    saveLeaderboard();
    renderLeaderboard();
    return leaderboard;
  }

  setSyncMessage("Сохраняю результат...");
  const response = await fetch(SERVER_LEADERBOARD_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      score,
      source: /mobile/i.test(navigator.userAgent) ? "mobile" : "desktop",
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const payload = await response.json();
  leaderboard = Array.isArray(payload.entries) ? payload.entries : [];
  setSyncMessage("Результат сохранен");
  renderLeaderboard();
  return leaderboard;
}

function goBackToPreviousSection() {
  if (window.history.length > 1 && document.referrer) {
    window.history.back();
    return;
  }

  if (window.location.protocol === "file:") {
    return;
  }

  window.location.href = "/";
}

function renderLeaderboard() {
  overlayLeaderboardEl.innerHTML = "";

  const entries = leaderboard.slice(0, 10);
  if (entries.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Пока пусто — твой забег может стать первым.";
    overlayLeaderboardEl.appendChild(li);
  } else {
    entries.forEach((entry, index) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${index + 1}. ${entry.name}</span><strong>${entry.score}</strong>`;
      overlayLeaderboardEl.appendChild(li);
    });
  }

  bestScoreEl.textContent = String(entries[0]?.score ?? 0);
}

function createInitialState() {
  return {
    score: 0,
    kills: 0,
    distance: 0,
    time: 0,
    speed: 360,
    bulletCooldown: 0,
    enemyTimer: 0.75,
    groundOffset: 0,
    skyOffset: 0,
    decorationsOffset: 0,
    player: {
      x: 180,
      y: GROUND_Y - 74,
      width: 42,
      height: 74,
      vy: 0,
      onGround: true,
    },
    bullets: [],
    enemies: [],
    particles: [],
  };
}

function resetRunState() {
  state = createInitialState();
  input.jumpQueued = false;
  input.shootQueued = false;
  hasSavedCurrentResult = false;
  saveButton.disabled = false;
  saveButton.textContent = defaultSaveButtonLabel;
  playerNameInput.value = "";
  scoreEl.textContent = "0";
  killsEl.textContent = "0";
}

function showScreen(screen) {
  appScreen = screen;
  overlayEl.classList.toggle("hidden", screen === "running");
  menuScreenEl.classList.toggle("hidden", screen !== "menu");
  gameoverScreenEl.classList.toggle("hidden", screen !== "gameover");
  touchControlsEl.classList.toggle("is-hidden", screen !== "running");
}

function startGame() {
  audio.ensureReady();
  audio.resetMusic();
  audio.playStart();
  resetRunState();
  showScreen("running");
  refreshLeaderboard();
}

function returnToMenu() {
  audio.playMenuBlip();
  resetRunState();
  showScreen("menu");
}

function queueJump() {
  if (appScreen === "running") {
    input.jumpQueued = true;
  }
}

function queueShoot() {
  if (appScreen === "running") {
    input.shootQueued = true;
  }
}

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowUp") {
    event.preventDefault();
    if (appScreen === "menu") {
      startGame();
      return;
    }
    queueJump();
  }

  if (event.key === " ") {
    event.preventDefault();
    if (appScreen === "menu") {
      startGame();
      return;
    }
    queueShoot();
  }

  if (appScreen === "gameover" && ["r", "R"].includes(event.key)) {
    event.preventDefault();
    returnToMenu();
  }
});

canvas.addEventListener("pointerdown", () => {
  if (appScreen === "running") {
    queueShoot();
  }
});

function bindTouchButton(button, handler) {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    if (appScreen === "menu") {
      startGame();
      return;
    }
    handler();
  });

  button.addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });
}

bindTouchButton(touchJumpButton, queueJump);
bindTouchButton(touchFireButton, queueShoot);

startButton.addEventListener("click", startGame);
restartButton.addEventListener("click", startGame);
globalBackButton.addEventListener("click", goBackToPreviousSection);

saveForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (hasSavedCurrentResult) {
    return;
  }

  const name = playerNameInput.value.trim() || "Боец";
  const score = Math.floor(state.score);

  try {
    saveButton.disabled = true;
    saveButton.textContent = "Сохраняю...";
    await submitLeaderboardScore(name, score);
    hasSavedCurrentResult = true;
    saveButton.textContent = "Сохранено";
  } catch (error) {
    console.error(error);
    setSyncMessage("Ошибка сохранения результата");
    saveButton.disabled = false;
    saveButton.textContent = defaultSaveButtonLabel;
  }
});

function spawnEnemy() {
  const isTall = Math.random() > 0.72;
  const size = isTall ? 84 : 62;
  const speedFactor = isTall ? 0.88 : 1;

  state.enemies.push({
    x: WORLD_WIDTH + 40,
    y: GROUND_Y - size,
    width: size,
    height: size,
    speed: state.speed * (0.78 + Math.random() * 0.28) * speedFactor,
    hp: isTall ? 2 : 1,
    bob: Math.random() * Math.PI * 2,
    variant: isTall ? "brute" : "runner",
  });
}

function spawnParticleBurst(x, y, color, spreadX, spreadY, count) {
  for (let i = 0; i < count; i += 1) {
    state.particles.push({
      x,
      y,
      vx: Math.random() * spreadX - spreadX * 0.25,
      vy: (Math.random() - 0.5) * spreadY,
      life: 0.16 + Math.random() * 0.16,
      size: 2 + Math.random() * 2,
      color,
    });
  }
}

function shootBullet() {
  if (state.bulletCooldown > 0) {
    return;
  }

  const bulletX = state.player.x + state.player.width + 10;
  const bulletY = state.player.y + state.player.height * 0.45;

  state.bullets.push({
    x: bulletX,
    y: bulletY,
    width: 16,
    height: 6,
    vx: 860,
  });
  state.bulletCooldown = 0.18;
  audio.playShoot();
  spawnParticleBurst(bulletX, bulletY, "#ffd166", 170, 90, 6);
}

function hurtPlayer() {
  if (appScreen !== "running") {
    return;
  }

  audio.playGameOver();
  spawnParticleBurst(
    state.player.x + state.player.width / 2,
    state.player.y + state.player.height / 2,
    "#ff7575",
    260,
    180,
    18,
  );
  finalTitleEl.textContent =
    state.score > (leaderboard[0]?.score ?? 0) ? "Новый рекорд" : "Попки догнали тебя";
  finalScoreLineEl.textContent = `Ваш счет: ${Math.floor(state.score)}`;
  hasSavedCurrentResult = false;
  saveButton.disabled = false;
  saveButton.textContent = defaultSaveButtonLabel;
  playerNameInput.value = "";
  showScreen("gameover");
  refreshLeaderboard();
  playerNameInput.focus();
}

function update(delta) {
  if (appScreen === "running") {
    state.time += delta;
    state.distance += state.speed * delta;
    state.score += delta * 35 + state.speed * delta * 0.04;
    state.speed = Math.min(760, 360 + state.time * 18);
    state.enemyTimer -= delta;
    state.bulletCooldown = Math.max(0, state.bulletCooldown - delta);
    state.groundOffset = (state.groundOffset + state.speed * delta) % 120;
    state.skyOffset = (state.skyOffset + state.speed * delta * 0.14) % WORLD_WIDTH;
    state.decorationsOffset = (state.decorationsOffset + state.speed * delta * 0.32) % 280;

    if (input.jumpQueued && state.player.onGround) {
      state.player.vy = -760;
      state.player.onGround = false;
      audio.playJump();
      spawnParticleBurst(
        state.player.x + state.player.width * 0.45,
        state.player.y + state.player.height,
        "#7fffd4",
        120,
        80,
        7,
      );
    }

    if (input.shootQueued) {
      shootBullet();
    }

    input.jumpQueued = false;
    input.shootQueued = false;

    state.player.vy += 1900 * delta;
    state.player.y += state.player.vy * delta;

    if (state.player.y >= GROUND_Y - state.player.height) {
      state.player.y = GROUND_Y - state.player.height;
      state.player.vy = 0;
      state.player.onGround = true;
    }

    if (state.enemyTimer <= 0) {
      spawnEnemy();
      const minDelay = Math.max(0.42, 1 - state.time * 0.018);
      const randomDelay = 0.16 + Math.random() * 0.54;
      state.enemyTimer = minDelay + randomDelay;
    }

    state.bullets = state.bullets.filter((bullet) => {
      bullet.x += bullet.vx * delta;
      return bullet.x < WORLD_WIDTH + 80;
    });

    state.enemies = state.enemies.filter((enemy) => {
      enemy.x -= enemy.speed * delta;
      enemy.bob += delta * 4;
      return enemy.x + enemy.width > -120;
    });
  } else {
    state.skyOffset = (state.skyOffset + 14 * delta) % WORLD_WIDTH;
    state.decorationsOffset = (state.decorationsOffset + 24 * delta) % 280;
    state.groundOffset = (state.groundOffset + 40 * delta) % 120;
    input.jumpQueued = false;
    input.shootQueued = false;
  }

  state.particles = state.particles.filter((particle) => {
    particle.x += particle.vx * delta;
    particle.y += particle.vy * delta;
    particle.life -= delta;
    particle.vx *= 0.98;
    particle.vy *= 0.98;
    return particle.life > 0;
  });

  if (appScreen === "running") {
    for (const bullet of state.bullets) {
      let hitEnemy = false;
      for (const enemy of state.enemies) {
        if (!overlaps(bullet, enemy)) {
          continue;
        }

        enemy.hp -= 1;
        bullet.x = WORLD_WIDTH + 999;
        audio.playHit();
        spawnParticleBurst(
          enemy.x + enemy.width / 2,
          enemy.y + enemy.height / 2,
          "#ff8fab",
          160,
          120,
          8,
        );

        if (enemy.hp <= 0) {
          state.kills += 1;
          state.score += enemy.variant === "brute" ? 40 : 24;
          enemy.x = -999;
        }

        hitEnemy = true;
        break;
      }

      if (hitEnemy) {
        continue;
      }
    }

    for (const enemy of state.enemies) {
      if (overlaps(state.player, enemy, 10)) {
        hurtPlayer();
        break;
      }
    }

    scoreEl.textContent = String(Math.floor(state.score));
    killsEl.textContent = String(state.kills);
    audio.tickMusic();
  }

  draw();
}

function overlaps(a, b, padding = 0) {
  return (
    a.x + padding < b.x + b.width &&
    a.x + a.width - padding > b.x &&
    a.y + padding < b.y + b.height &&
    a.y + a.height - padding > b.y
  );
}

function draw() {
  drawSky();
  drawBackdrop();
  drawGround();
  drawBullets();
  drawEnemies();
  drawPlayer();
  drawParticles();
  drawHints();
}

function drawSky() {
  ctx.fillStyle = "#6eaaf2";
  ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

  ctx.fillStyle = "#d9f4ff";
  for (let i = 0; i < 6; i += 1) {
    const x = ((i * 180 - state.skyOffset * 0.45) % (WORLD_WIDTH + 220)) - 60;
    const y = 70 + (i % 3) * 48;
    ctx.fillRect(x, y, 28, 8);
    ctx.fillRect(x + 20, y - 6, 24, 10);
    ctx.fillRect(x + 40, y, 26, 8);
  }

  ctx.fillStyle = "#0f2d62";
  for (let i = 0; i < 10; i += 1) {
    const x = ((i * 120 - state.skyOffset * 0.15) % (WORLD_WIDTH + 120)) - 10;
    const h = 24 + (i % 4) * 18;
    ctx.fillRect(x, GROUND_Y - 92 - h, 34, h);
    ctx.fillRect(x + 12, GROUND_Y - 92 - h - 20, 10, 20);
  }
}

function drawBackdrop() {
  for (let i = 0; i < 5; i += 1) {
    const x = ((i * 240 - state.decorationsOffset) % (WORLD_WIDTH + 260)) - 130;
    const h = 170 + (i % 3) * 70;
    const width = 126;

    ctx.fillStyle = i % 2 === 0 ? "#3569c4" : "#2856ab";
    ctx.fillRect(x, GROUND_Y - h, width, h);

    ctx.fillStyle = "#000000";
    ctx.fillRect(x, GROUND_Y - h, 4, h);
    ctx.fillRect(x + width - 4, GROUND_Y - h, 4, h);

    for (let row = 0; row < 5; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        const wx = x + 16 + col * 34;
        const wy = GROUND_Y - h + 20 + row * 32;
        ctx.fillStyle = "#000000";
        ctx.fillRect(wx, wy, 18, 24);
        ctx.fillStyle = "#1f4ba0";
        ctx.fillRect(wx + 3, wy + 3, 12, 18);
        ctx.fillStyle = "#91c4ff";
        ctx.fillRect(wx + 9, wy + 3, 2, 18);
      }
    }
  }
}

function drawGround() {
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, GROUND_Y, WORLD_WIDTH, WORLD_HEIGHT - GROUND_Y);

  ctx.fillStyle = "#9e5322";
  ctx.fillRect(0, GROUND_Y - 26, WORLD_WIDTH, 26);

  for (let i = -1; i < WORLD_WIDTH / 32 + 3; i += 1) {
    const x = i * 32 - (state.groundOffset % 32);
    ctx.fillStyle = "#d48c52";
    ctx.fillRect(x, GROUND_Y - 26, 24, 10);
    ctx.fillStyle = "#000000";
    ctx.fillRect(x, GROUND_Y - 26, 24, 2);
    ctx.fillRect(x, GROUND_Y - 18, 2, 10);
  }

  ctx.fillStyle = "#8a4218";
  ctx.fillRect(0, GROUND_Y, WORLD_WIDTH, 66);

  for (let row = 0; row < 4; row += 1) {
    for (let col = -1; col < WORLD_WIDTH / 40 + 2; col += 1) {
      const offset = row % 2 === 0 ? 0 : 20;
      const x = col * 40 - (state.groundOffset % 40) + offset;
      const y = GROUND_Y + row * 16;
      ctx.fillStyle = "#bb6a32";
      ctx.fillRect(x, y, 36, 12);
      ctx.fillStyle = "#000000";
      ctx.fillRect(x, y, 36, 2);
      ctx.fillRect(x, y, 2, 12);
    }
  }
}

function drawPlayer() {
  const { player } = state;
  const runPhase = Math.sin(state.time * 16) * 4;
  const legSwing = player.onGround ? runPhase : 0;
  const armSwing = player.onGround ? runPhase * 0.5 : -3;
  const capeSwing = player.onGround ? Math.sin(state.time * 11) * 4 : 8;

  ctx.save();
  ctx.translate(player.x, player.y);
  ctx.imageSmoothingEnabled = false;

  ctx.fillStyle = "#000000";
  ctx.beginPath();
  ctx.moveTo(12, 24);
  ctx.lineTo(2, 40 + capeSwing);
  ctx.lineTo(12, 50);
  ctx.lineTo(18, 26);
  ctx.fill();

  ctx.fillStyle = "#6f34b1";
  ctx.beginPath();
  ctx.moveTo(14, 25);
  ctx.lineTo(6, 40 + capeSwing * 0.8);
  ctx.lineTo(14, 46);
  ctx.lineTo(18, 26);
  ctx.fill();

  ctx.fillStyle = "#000000";
  ctx.fillRect(12, 0, 18, 6);
  ctx.fillRect(15, 6, 12, 4);

  ctx.fillStyle = "#ddd2b1";
  ctx.fillRect(15, 10, 12, 10);
  ctx.fillStyle = "#f2b13a";
  ctx.fillRect(23, 12, 11, 6);
  ctx.fillStyle = "#000000";
  ctx.fillRect(12, 13, 12, 3);

  ctx.fillStyle = "#6f34b1";
  ctx.fillRect(14, 20, 18, 18);
  ctx.fillStyle = "#efe6a9";
  ctx.fillRect(19, 24, 6, 7);
  ctx.fillStyle = "#000000";
  ctx.fillRect(18, 23, 8, 9);

  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 4;
  ctx.lineCap = "square";
  ctx.beginPath();
  ctx.moveTo(22, 24);
  ctx.lineTo(22, 47);
  ctx.moveTo(22, 30);
  ctx.lineTo(12, 41 + armSwing);
  ctx.moveTo(22, 31);
  ctx.lineTo(37, 29 - armSwing);
  ctx.moveTo(37, 29 - armSwing);
  ctx.lineTo(53, 25 - armSwing);
  ctx.moveTo(22, 47);
  ctx.lineTo(13, 66 - legSwing);
  ctx.moveTo(22, 47);
  ctx.lineTo(34, 66 + legSwing);
  ctx.stroke();

  ctx.strokeStyle = "#6f34b1";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(38, 29 - armSwing);
  ctx.lineTo(53, 25 - armSwing);
  ctx.moveTo(22, 47);
  ctx.lineTo(13, 66 - legSwing);
  ctx.moveTo(22, 47);
  ctx.lineTo(34, 66 + legSwing);
  ctx.stroke();

  ctx.fillStyle = "#c9892b";
  ctx.fillRect(51, 23 - armSwing, 13, 4);
  ctx.fillStyle = "#f0d78a";
  ctx.fillRect(64, 24 - armSwing, 7, 2);

  ctx.fillStyle = "#f2b13a";
  ctx.fillRect(11, 67 - legSwing, 6, 4);
  ctx.fillRect(33, 67 + legSwing, 6, 4);

  ctx.restore();
}

function drawEnemies() {
  for (const enemy of state.enemies) {
    const wobble = Math.sin(enemy.bob) * 3;
    const bodyX = enemy.x + enemy.width * 0.54;
    const bodyY = enemy.y + enemy.height * 0.54 + wobble;
    const scale = enemy.width / 62;

    ctx.save();
    ctx.translate(bodyX, bodyY);

    ctx.strokeStyle = "#20232b";
    ctx.lineWidth = 4 * scale;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(-20 * scale, 8 * scale);
    ctx.quadraticCurveTo(-36 * scale, -12 * scale, -18 * scale, -18 * scale);
    ctx.stroke();

    ctx.fillStyle = enemy.variant === "brute" ? "#7f858f" : "#8d939c";
    ctx.beginPath();
    ctx.ellipse(0, 0, 21 * scale, 15 * scale, -0.18, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = enemy.variant === "brute" ? "#ff364d" : "#ff415a";
    ctx.beginPath();
    ctx.ellipse(-16 * scale, 8 * scale, 12 * scale, 11 * scale, 0.08, 0, Math.PI * 2);
    ctx.ellipse(-4 * scale, 9 * scale, 12 * scale, 11 * scale, -0.08, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "rgba(110, 0, 10, 0.55)";
    ctx.lineWidth = 2 * scale;
    ctx.beginPath();
    ctx.moveTo(-11 * scale, 2 * scale);
    ctx.lineTo(-10 * scale, 17 * scale);
    ctx.stroke();

    ctx.fillStyle = "#545b65";
    ctx.beginPath();
    ctx.ellipse(17 * scale, -9 * scale, 13 * scale, 10 * scale, 0.18, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#23262d";
    ctx.beginPath();
    ctx.ellipse(21 * scale, -8 * scale, 8 * scale, 7 * scale, 0.12, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#111318";
    ctx.beginPath();
    ctx.arc(25 * scale, -10 * scale, 1.3 * scale, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "#2a2d35";
    ctx.lineWidth = 3.5 * scale;
    ctx.beginPath();
    ctx.moveTo(4 * scale, 12 * scale);
    ctx.lineTo(13 * scale, 27 * scale);
    ctx.moveTo(-8 * scale, 12 * scale);
    ctx.lineTo(-15 * scale, 27 * scale);
    ctx.moveTo(13 * scale, 4 * scale);
    ctx.lineTo(24 * scale, 18 * scale);
    ctx.moveTo(3 * scale, 2 * scale);
    ctx.lineTo(-4 * scale, 17 * scale);
    ctx.stroke();

    ctx.restore();
  }
}

function drawBullets() {
  for (const bullet of state.bullets) {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(bullet.x, bullet.y, bullet.width, bullet.height);
    ctx.fillStyle = "#000000";
    ctx.fillRect(bullet.x, bullet.y + bullet.height - 1, bullet.width, 1);
    ctx.fillStyle = "#fff1a8";
    ctx.fillRect(bullet.x - 6, bullet.y + 1, 6, 3);
  }
}

function drawParticles() {
  for (const particle of state.particles) {
    ctx.globalAlpha = Math.max(0, particle.life * 2.2);
    ctx.fillStyle = particle.color;
    ctx.fillRect(particle.x, particle.y, particle.size, particle.size);
  }

  ctx.globalAlpha = 1;
}

function drawHints() {
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 18px Courier New";
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 4;

  if (appScreen === "running") {
    ctx.strokeText("UP JUMP   SPACE FIRE", 24, 34);
    ctx.fillText("UP JUMP   SPACE FIRE", 24, 34);
  } else {
    ctx.strokeText("PRESS START", 24, 34);
    ctx.fillText("PRESS START", 24, 34);
  }
}

function frame(timestamp) {
  if (!lastTimestamp) {
    lastTimestamp = timestamp;
  }

  const delta = Math.min(0.033, (timestamp - lastTimestamp) / 1000);
  lastTimestamp = timestamp;
  update(delta);
  requestAnimationFrame(frame);
}

resetRunState();
showScreen("menu");
refreshLeaderboard();
window.addEventListener("focus", () => {
  refreshLeaderboard();
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshLeaderboard();
  }
});

if (previewMode === "running") {
  startGame();
}

if (previewMode === "leaderboard") {
  refreshLeaderboard().then(() => {
    finalTitleEl.textContent = "Лидеры района";
    finalScoreLineEl.textContent = "Введите имя после забега и таблица обновится здесь";
    playerNameInput.value = "Боец";
    showScreen("gameover");
  });
}

if (previewMode === "gameover") {
  leaderboard = [
    { name: "Ivan", score: 529 },
    { name: "Max", score: 430 },
    { name: "Roma", score: 390 },
  ];
  renderLeaderboard();
  finalTitleEl.textContent = "Новый рекорд";
  finalScoreLineEl.textContent = "Ваш счет: 1221";
  playerNameInput.value = "Боец";
  setSyncMessage("Лидерборд синхронизирован");
  showScreen("gameover");
}

requestAnimationFrame(frame);
