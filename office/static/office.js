const floor = document.querySelector("#floor");
const summary = document.querySelector("#summary");
const banner = document.querySelector("#banner");
const keyNote = document.querySelector("#key-note");
const keyInput = document.querySelector("#api-key");
const clock = document.querySelector("#clock");

const SHIRTS = ["#3d6b8c", "#c4654a", "#2f6f55", "#8a5a9a", "#b5832d", "#44515c"];
const HAIR = ["#2b241e", "#6b3f28", "#8d6a45", "#1f1a17", "#a33b3b"];
const SKIN = ["#f0c7a4", "#e0ac84", "#c68642", "#8d5524"];
const HAIR_STYLES = ["short", "bun", "curls", "cap"];
const POSE_LABEL = {
  working: "печатает",
  resting: "отошёл от стола",
  away: "стол свободен",
};

let mode = "demo";
let pollTimer = 0;

function hash(value) {
  let total = 0;
  for (const char of String(value)) total = (total * 33 + char.charCodeAt(0)) >>> 0;
  return total;
}

function pick(list, seed) {
  return list[seed % list.length];
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

function makePerson(seed) {
  const person = document.createElement("div");
  person.className = "person";
  person.style.setProperty("--shirt", pick(SHIRTS, seed));
  person.style.setProperty("--hair", pick(HAIR, seed >> 3));
  person.style.setProperty("--skin", pick(SKIN, seed >> 5));

  const head = document.createElement("div");
  head.className = "head";
  const hair = document.createElement("div");
  hair.className = "hair " + pick(HAIR_STYLES, seed >> 7);
  const eyeL = document.createElement("i");
  const eyeR = document.createElement("i");
  eyeL.className = "eye l";
  eyeR.className = "eye r";
  head.append(hair, eyeL, eyeR);

  const body = document.createElement("div");
  body.className = "body";
  const armL = document.createElement("div");
  const armR = document.createElement("div");
  armL.className = "arm l";
  armR.className = "arm r";
  const paper = document.createElement("div");
  paper.className = "paper";
  person.append(head, body, armL, armR, paper);
  return person;
}

function makeScene(agent) {
  const scene = document.createElement("div");
  scene.className = "scene";
  const chair = document.createElement("div");
  chair.className = "chair";
  const desk = document.createElement("div");
  desk.className = "desk-top";
  const monitor = document.createElement("div");
  monitor.className = "monitor";
  const screen = document.createElement("div");
  screen.className = "screen";
  const keyboard = document.createElement("div");
  keyboard.className = "keyboard";
  monitor.append(screen);
  desk.append(monitor, keyboard);
  scene.append(chair, makePerson(hash(agent.id || agent.name)), desk);
  return scene;
}

function render(agents, nextMode, error) {
  mode = nextMode;
  floor.replaceChildren();
  const visibleAway = agents.filter((agent) => agent.pose === "away").slice(0, 6);
  const hiddenAway = agents.filter((agent) => agent.pose === "away").length - visibleAway.length;
  const shown = agents.filter((agent) => agent.pose !== "away").concat(visibleAway);

  if (error) setBanner(error);
  else if (mode === "demo") setBanner("Это пример. Твои агенты сядут за столы, когда сохранишь ключ Cursor на этом компьютере.");
  else setBanner("");

  if (!shown.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = error
      ? "Пока показать сотрудников не получилось."
      : "В офисе тихо. Рабочих агентов ещё нет.";
    floor.append(empty);
  }

  for (const agent of shown) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "desk pose-" + (agent.pose || "resting");
    const url = safeUrl(agent.url);
    card.append(makeScene(agent));
    const name = document.createElement("p");
    name.className = "name";
    name.textContent = agent.name || "Без имени";
    const meta = document.createElement("p");
    meta.className = "name-meta";
    meta.textContent = POSE_LABEL[agent.pose] || "на месте";
    card.append(name, meta);
    card.addEventListener("click", () => {
      if (url) window.open(url, "_blank", "noopener");
    });
    floor.append(card);
  }

  const working = agents.filter((agent) => agent.pose === "working").length;
  const resting = agents.filter((agent) => agent.pose === "resting").length;
  const away = agents.filter((agent) => agent.pose === "away").length;
  const extra = hiddenAway > 0 ? ` Ещё ${hiddenAway} в архиве не поместились.` : "";
  summary.textContent = `Печатают: ${working}. Отошли: ${resting}. Пустых столов: ${Math.min(away, 6)}.${extra}`;
}

async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) {
    const message = payload.error || "Не получилось обновить офис";
    throw new Error(message);
  }
  return payload;
}

async function loadLive() {
  const payload = await readJson(await fetch("/api/office"));
  if (!payload.configured) {
    const demo = await readJson(await fetch("/api/demo"));
    render(demo.agents, "demo", null);
    stopPoll();
    return;
  }
  render(payload.agents, "live", payload.error);
  startPoll();
}

function startPoll() {
  stopPoll();
  pollTimer = window.setInterval(() => {
    if (document.hidden || mode !== "live") return;
    loadLive().catch((error) => setBanner(error.message));
  }, 4000);
}

function stopPoll() {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = 0;
}

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
    await loadLive();
  } catch (error) {
    keyNote.textContent = error.message;
  }
});

document.querySelector("#forget").addEventListener("click", async () => {
  await fetch("/api/key", { method: "DELETE" });
  keyNote.textContent = "Ключ удалён с этого компьютера.";
  await loadLive();
});

document.querySelector("#refresh").addEventListener("click", () => {
  loadLive().catch((error) => setBanner(error.message));
});

document.querySelector("#shutdown").addEventListener("click", async () => {
  summary.textContent = "Закрываю офис…";
  await fetch("/api/shutdown", { method: "POST" });
  stopPoll();
  setBanner("Офис закрыт. Окно можно закрыть.");
});

tickClock();
window.setInterval(tickClock, 10000);
loadLive().catch((error) => setBanner(error.message));
