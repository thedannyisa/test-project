const floor = document.querySelector("#floor");
const summary = document.querySelector("#summary");
const banner = document.querySelector("#banner");
const keyNote = document.querySelector("#key-note");
const keyInput = document.querySelector("#api-key");
const clock = document.querySelector("#clock");
const meters = document.querySelector("#meters");
const resetBox = document.querySelector("#reset");
const board = document.querySelector("#board");

const FURS = ["#e7a15a", "#8d8f98", "#2c2a33", "#f3e2c4", "#d8d2cc", "#c47a4a"];
const ACCENTS = ["#f2c1b0", "#f7d7a8", "#d9d4ea", "#b7d7c5"];
const GROUPS = [
  { id: "cursor", label: "Cursor" },
  { id: "other", label: "Other" },
  { id: "grok", label: "Grok" },
];
const POSE_LABEL = {
  working: "печатает",
  resting: "отошёл",
  away: "стол свободен",
};
const METER_COPY = {
  cursorModels: { title: "Cursor Models", hint: "зарплата котов Cursor" },
  otherModels: { title: "Other Models", hint: "зарплата котов Other" },
  grokBot: { title: "Grok Bot", hint: "недельная зарплата" },
};

let mode = "demo";
let pollTimer = 0;
let limitsTimer = 0;
let latestLimits = null;
let lastRender = null;

function hash(value) {
  let total = 0;
  for (const char of String(value)) total = (total * 33 + char.charCodeAt(0)) >>> 0;
  return total;
}

function pick(list, seed) {
  return list[seed % list.length];
}

function payGroup(id) {
  return pick(GROUPS, hash(id));
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return url.href;
  } catch (_error) {
    return "";
  }
  return "";
}

function tickClock() {
  clock.textContent = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function setBanner(text) {
  if (!text) {
    banner.hidden = true;
    banner.textContent = "";
    return;
  }
  banner.hidden = false;
  banner.textContent = text;
}

function rect(svg, x, y, w, h, fill) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  node.setAttribute("x", x);
  node.setAttribute("y", y);
  node.setAttribute("width", w);
  node.setAttribute("height", h);
  node.setAttribute("fill", fill);
  svg.append(node);
}

function catSvg(seed, pose) {
  const fur = pick(FURS, seed);
  const inner = pick(ACCENTS, seed >> 3);
  const accessory = seed % 5;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("shape-rendering", "crispEdges");
  rect(svg, 2, 1, 3, 3, fur);
  rect(svg, 11, 1, 3, 3, fur);
  rect(svg, 3, 2, 1, 1, inner);
  rect(svg, 12, 2, 1, 1, inner);
  rect(svg, 3, 3, 10, 7, fur);
  rect(svg, 5, 6, 6, 3, inner);
  rect(svg, 4, 9, 8, 4, fur);
  rect(svg, 1, 8, 2, 5, fur);
  rect(svg, 6, 10, 4, 2, inner);
  if (pose === "working") {
    rect(svg, 5, 13, 2, 2, fur);
    rect(svg, 9, 13, 2, 2, fur);
  } else {
    rect(svg, 4, 13, 3, 2, fur);
    rect(svg, 9, 13, 3, 2, fur);
  }
  const eye = pose === "asleep" ? fur : "#1a120e";
  rect(svg, 5, 6, 2, pose === "asleep" ? 1 : 2, eye);
  rect(svg, 9, 6, 2, pose === "asleep" ? 1 : 2, eye);
  rect(svg, 7, 8, 2, 1, "#e07a8a");
  if (accessory === 1) {
    rect(svg, 1, 4, 3, 2, "#22324a");
    rect(svg, 12, 4, 3, 2, "#22324a");
  } else if (accessory === 2) {
    rect(svg, 4, 6, 8, 1, "#d8ecff");
  } else if (accessory === 3) {
    rect(svg, 4, 1, 8, 2, "#355f86");
  } else if (accessory === 4) {
    rect(svg, 12, 5, 3, 2, "#c4476a");
  }
  return svg;
}

function makeStation(agent, asleep) {
  const station = document.createElement("div");
  station.className = "station";
  const group = payGroup(agent.id || agent.name);
  const monitor = document.createElement("div");
  monitor.className = "monitor";
  const screen = document.createElement("div");
  screen.className = "screen";
  monitor.append(screen);
  const keyboard = document.createElement("div");
  keyboard.className = "keyboard";
  const table = document.createElement("div");
  table.className = "table";
  const chair = document.createElement("div");
  chair.className = "chair";
  const cat = document.createElement("div");
  cat.className = "cat";
  const pose = asleep ? "asleep" : agent.pose;
  cat.append(catSvg(hash(agent.id || agent.name), pose === "away" ? "resting" : pose));
  const zzz = document.createElement("span");
  zzz.className = "zzz";
  zzz.textContent = "z";
  const badge = document.createElement("span");
  badge.className = "badge " + group.id;
  badge.textContent = group.label;
  const pip = document.createElement("span");
  pip.className = "status-pip " + agent.pose;
  pip.textContent = agent.pose === "working" ? "●" : agent.pose === "resting" ? "○" : "·";
  station.append(chair, cat, zzz, table, monitor, keyboard, badge, pip);
  return station;
}

function limitLevel(groupId) {
  if (!latestLimits) return "unknown";
  const key = groupId === "cursor" ? "cursorModels" : groupId === "other" ? "otherModels" : "grokBot";
  return latestLimits[key] && latestLimits[key].level ? latestLimits[key].level : "unknown";
}

function render(agents, nextMode, error) {
  mode = nextMode;
  floor.replaceChildren();
  const awayAgents = agents.filter((agent) => agent.pose === "away");
  const visibleAway = awayAgents.slice(0, 6);
  const hiddenAway = awayAgents.length - visibleAway.length;
  const shown = agents.filter((agent) => agent.pose !== "away").concat(visibleAway);
  const resting = shown.filter((agent) => agent.pose === "resting");
  const sleeper = resting.length ? resting.slice().sort((a, b) => hash(a.id) - hash(b.id))[0].id : "";

  if (error) setBanner(error);
  else if (mode === "demo") setBanner("Это пример. Твои коты сядут за столы, когда сохранишь ключ Cursor на этом компьютере.");
  else setBanner("");

  if (!shown.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = error ? "Пока показать сотрудников не получилось." : "В офисе тихо. Рабочих агентов ещё нет.";
    floor.append(empty);
  }

  for (const agent of shown) {
    const group = payGroup(agent.id || agent.name);
    const level = limitLevel(group.id);
    const card = document.createElement("button");
    card.type = "button";
    const asleep = agent.id === sleeper;
    card.className = "desk pose-" + (agent.pose || "resting") + (asleep ? " asleep" : "") + (level === "empty" ? " no-resource" : "");
    card.append(makeStation(agent, asleep));
    const plate = document.createElement("div");
    plate.className = "nameplate";
    const name = document.createElement("p");
    name.className = "name";
    name.textContent = agent.catName || "Кот";
    const job = document.createElement("p");
    job.className = "job";
    job.textContent = agent.role || agent.name || "Без должности";
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = POSE_LABEL[agent.pose] || "на месте";
    plate.append(name, job, meta);
    if (level === "empty") {
      const resource = document.createElement("p");
      resource.className = "resource";
      resource.textContent = "нет ресурса";
      plate.append(resource);
    }
    card.append(plate);
    const url = safeUrl(agent.url);
    card.addEventListener("click", () => {
      if (url) window.open(url, "_blank", "noopener");
    });
    floor.append(card);
  }

  const working = agents.filter((agent) => agent.pose === "working").length;
  const restingCount = agents.filter((agent) => agent.pose === "resting").length;
  const away = agents.filter((agent) => agent.pose === "away").length;
  const extra = hiddenAway > 0 ? ` Ещё ${hiddenAway} в архиве не поместились.` : "";
  summary.textContent = `Печатают: ${working}. Отошли: ${restingCount}. Пустых столов: ${Math.min(away, 6)}.${extra}`;
}

function cells(used) {
  const wrap = document.createElement("div");
  wrap.className = "bar";
  const filled = used == null ? 0 : Math.round((used / 100) * 16);
  for (let index = 0; index < 16; index += 1) {
    const cell = document.createElement("span");
    cell.className = "cell" + (index < filled ? " on" : "");
    wrap.append(cell);
  }
  return wrap;
}

function renderMeter(key, meter) {
  const copy = METER_COPY[key];
  const block = document.createElement("article");
  block.className = "meter " + ((meter && meter.level) || "unknown");
  const top = document.createElement("p");
  top.className = "meter-top";
  const title = document.createElement("span");
  title.textContent = copy.title;
  const value = document.createElement("span");
  value.textContent = meter && meter.available ? meter.usedPercent + "%" : "Недоступно";
  top.append(title, value);
  const sub = document.createElement("p");
  sub.className = "meter-sub";
  if (meter && meter.available) {
    const left = meter.remainingPercent + "% осталось";
    const note = meter.level === "empty" ? "Лимит закончился" : meter.level === "hot" ? "Почти всё потрачено" : copy.hint;
    sub.textContent = left + " · " + note;
  } else {
    const reason = (meter && meter.reason) || "";
    sub.textContent = reason && reason !== "Недоступно" ? reason : "";
  }
  block.append(top, cells(meter && meter.available ? meter.usedPercent : null), sub);
  return block;
}

function renderSubscription(subscription) {
  const line = document.createElement("p");
  line.className = "subscription";
  if (!subscription || subscription.available !== true) {
    line.textContent = "Окончание подписки: " + ((subscription && subscription.reason) || "Недоступно");
    return line;
  }
  const plan = subscription.plan ? " " + subscription.plan : "";
  if (subscription.renews) {
    line.textContent = "Подписка" + plan + " продлевается сама. Даты окончания нет.";
    return line;
  }
  if (subscription.at) {
    line.textContent = "Подписка" + plan + " закончится: " + formatReset({
      available: true,
      days: subscription.days,
      at: subscription.at,
    });
    return line;
  }
  if (subscription.days != null) {
    const days = subscription.days === 0 ? "сегодня" : subscription.days + " дн.";
    line.textContent = "Пробный период" + plan + ": " + days;
    return line;
  }
  line.textContent = "Окончание подписки: " + (subscription.reason || "Недоступно");
  return line;
}

function formatReset(reset) {
  if (!reset || !reset.available || reset.at == null) return (reset && reset.reason) || "Недоступно";
  const when = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(reset.at));
  const days = reset.days === 0 ? "сегодня" : reset.days + " дн.";
  return days + " · " + when;
}

function renderLimits(payload) {
  latestLimits = payload;
  meters.replaceChildren();
  resetBox.replaceChildren();
  const source = payload || {
    cursorModels: { available: false, reason: "Недоступно" },
    otherModels: { available: false, reason: "Недоступно" },
    grokBot: { available: false, reason: "Недоступно" },
    reset: { available: false, reason: "Недоступно" },
    grokReset: { available: false, reason: "Недоступно" },
  };
  meters.append(
    renderMeter("cursorModels", source.cursorModels),
    renderMeter("otherModels", source.otherModels),
    renderMeter("grokBot", source.grokBot),
  );
  const main = document.createElement("p");
  main.textContent = "До следующего сброса: " + formatReset(source.reset);
  resetBox.append(main, renderSubscription(source.subscription));
  if (source.grokReset && source.grokReset.available) {
    const grok = document.createElement("p");
    grok.textContent = "Сброс Grok Bot: " + formatReset(source.grokReset);
    resetBox.append(grok);
  }
  const levels = ["cursorModels", "otherModels", "grokBot"].map((key) => (source[key] && source[key].level) || "unknown");
  board.classList.toggle("tense", levels.some((level) => level === "hot" || level === "warn"));
  board.classList.toggle("spent", levels.some((level) => level === "empty"));
}

async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Не получилось обновить офис");
  return payload;
}

async function loadLimits() {
  try {
    renderLimits(await readJson(await fetch("/api/limits")));
  } catch (_error) {
    renderLimits(null);
  }
  if (lastRender) render(lastRender.agents, lastRender.mode, lastRender.error);
}

async function loadAgents() {
  const payload = await readJson(await fetch("/api/office"));
  if (!payload.configured) {
    const demo = await readJson(await fetch("/api/demo"));
    lastRender = { agents: demo.agents, mode: "demo", error: null };
    render(demo.agents, "demo", null);
    stopPoll();
    return;
  }
  lastRender = { agents: payload.agents, mode: "live", error: payload.error };
  render(payload.agents, "live", payload.error);
  startPoll();
}

async function refreshAll() {
  await loadLimits();
  await loadAgents();
}

function startPoll() {
  if (pollTimer) return;
  pollTimer = window.setInterval(() => {
    if (document.hidden || mode !== "live") return;
    loadAgents().catch((error) => setBanner(error.message));
  }, 4000);
  limitsTimer = window.setInterval(() => {
    if (!document.hidden) loadLimits();
  }, 60000);
}

function stopPoll() {
  if (pollTimer) window.clearInterval(pollTimer);
  if (limitsTimer) window.clearInterval(limitsTimer);
  pollTimer = 0;
  limitsTimer = 0;
}

const settings = document.querySelector("#settings");
const settingsOpen = document.querySelector("#settings-open");

function openSettings() {
  settings.hidden = false;
  keyInput.focus();
}

function closeSettings() {
  settings.hidden = true;
  settingsOpen.focus();
}

settingsOpen.addEventListener("click", openSettings);
document.querySelector("#settings-close").addEventListener("click", closeSettings);
settings.addEventListener("click", (event) => {
  if (event.target === settings) closeSettings();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settings.hidden) closeSettings();
});

document.querySelector("#key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  keyNote.textContent = "Проверяю ключ…";
  try {
    await readJson(await fetch("/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey: keyInput.value }),
    }));
    keyInput.value = "";
    keyNote.textContent = "Ключ сохранён на этом компьютере.";
    closeSettings();
    await refreshAll();
    if (!lastRender || !lastRender.error) setBanner("Ключ сохранён на этом компьютере.");
  } catch (error) {
    keyNote.textContent = error.message;
  }
});

document.querySelector("#forget").addEventListener("click", async () => {
  await fetch("/api/key", { method: "DELETE" });
  keyNote.textContent = "Ключ удалён с этого компьютера.";
  await refreshAll();
});

document.querySelector("#refresh").addEventListener("click", () => {
  refreshAll().catch((error) => setBanner(error.message));
});

document.querySelector("#shutdown").addEventListener("click", async () => {
  summary.textContent = "Закрываю офис…";
  await fetch("/api/shutdown", { method: "POST" });
  stopPoll();
  setBanner("Офис закрыт. Окно можно закрыть.");
});

tickClock();
window.setInterval(tickClock, 10000);
refreshAll().catch((error) => setBanner(error.message));
