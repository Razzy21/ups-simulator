"use strict";
/* UPS client. No inline scripts or styles (strict CSP); all text goes in via textContent. */

const app = { scenarios: [], info: null, run: null, history: [], summary: null, frames: [],
              mode: "picker", prev: null, notice: null, error: null, replayStep: 0, timer: null };
let token = sessionStorage.getItem("upsToken") || "";

// ---------- helpers ----------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const svg = (tag, attrs) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
};
const sign = (n) => (n > 0 ? "+" : n < 0 ? "\u2212" : "") + Math.abs(Math.round(n * 100) / 100);

async function api(method, path, body) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["X-Access-Token"] = token;
  const res = await fetch("/api" + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (_) { /* not JSON */ }
  if (res.status === 401) {
    const t = prompt("This server needs an access token:");
    if (t) { token = t; sessionStorage.setItem("upsToken", t); return api(method, path, body); }
  }
  if (!res.ok) {
    const err = new Error((data && data.error && data.error.message) || "Request failed (" + res.status + ")");
    err.code = data && data.error && data.error.code;
    throw err;
  }
  return data;
}

async function act(fn) {
  app.error = null;
  try { await fn(); } catch (e) {
    app.error = e.message;
    if (e.code === "run_not_found") { stopReplay(); app.run = null; app.mode = "picker"; }
  }
  render();
}

// ---------- actions ----------
function setRun(run) {
  app.prev = app.run ? Object.fromEntries(app.run.measures.map((m) => [m.id, m.value])) : null;
  app.run = run;
}
const start = (id) => act(async () => {
  app.info = await api("GET", "/scenarios/" + id);
  app.prev = null; app.run = null;
  setRun(await api("POST", "/runs", { scenarioId: id }));
  app.notice = null; app.mode = "dashboard";
});
const advance = (body) => act(async () => {
  app.notice = null;
  setRun(await api("POST", `/runs/${app.run.runId}/advance`, body));
  await afterChange();
});
const decide = (pd, optionId) => act(async () => {
  setRun(await api("POST", `/runs/${app.run.runId}/decisions`, { eventId: pd.eventId, decisionId: pd.decisionId, optionId }));
  const last = app.run.feed[0];
  if (last && last.type === "decision") {
    app.notice = `You chose "${last.optionLabel}": ` + last.effects.map((e) => `${e.label} ${sign(e.applied)}`).join(", ") + ".";
  }
  await afterChange();
});
async function afterChange() {
  if (app.run.status === "complete") {
    app.summary = await api("GET", `/runs/${app.run.runId}/summary`);
    app.history = (await api("GET", `/runs/${app.run.runId}/history`)).entries;
    app.mode = "summary";
  }
}
const resetRun = () => {
  if (!confirm("Reset this run? Your progress and log will be cleared.")) return;
  stopReplay();
  act(async () => { setRun(await api("POST", `/runs/${app.run.runId}/reset`)); app.prev = null; app.notice = null; app.mode = "dashboard"; });
};
const showLog = () => act(async () => { app.history = (await api("GET", `/runs/${app.run.runId}/history`)).entries; app.mode = "log"; });
const startReplay = () => act(async () => {
  app.frames = (await api("GET", `/runs/${app.run.runId}/replay`)).frames;
  app.replayStep = 0; app.mode = "replay"; playReplay();
});
function playReplay() {
  stopReplay();
  app.timer = setInterval(() => {
    if (app.replayStep >= app.frames.length - 1) { stopReplay(); render(); return; }
    app.replayStep++; render();
  }, 1600);
}
function stopReplay() { if (app.timer) { clearInterval(app.timer); app.timer = null; } }
function backToPicker() { stopReplay(); app.mode = "picker"; app.run = null; render(); }
const goto = (mode) => { stopReplay(); app.mode = mode; render(); };

// ---------- components ----------
function measureCard(m, value, prevValue) {
  const frac = (value - m.min) / (m.max - m.min);
  const health = m.higherIsBetter ? frac : 1 - frac;
  const level = health >= 0.6 ? "ok" : health >= 0.35 ? "warning" : "critical";
  const diff = prevValue == null ? 0 : value - prevValue;
  const good = m.higherIsBetter ? diff > 0 : diff < 0;
  const meter = h("div", { class: "meter " + level, role: "progressbar", "aria-label": m.label,
                           "aria-valuemin": m.min, "aria-valuemax": m.max, "aria-valuenow": value });
  const fill = h("span"); fill.style.width = Math.round(health * 100) + "%"; meter.append(fill);
  return h("div", { class: "card" },
    h("div", { class: "mlabel" }, m.label),
    h("div", { class: "mvalue" }, Math.round(value * 10) / 10, " ",
      Math.abs(diff) >= 0.05 ? h("small", { class: good ? "up" : "down" }, (diff > 0 ? "\u25B2 " : "\u25BC ") + sign(diff)) : null),
    meter,
    h("div", { class: "muted", style: null }, level === "ok" ? "Healthy" : level === "warning" ? "Under pressure" : "Critical"));
}

function effectChips(effects) {
  return effects.map((e) => h("span", { class: "chip " + (e.applied > 0 ? "pos" : e.applied < 0 ? "neg" : "") },
    `${e.label} ${sign(e.applied)}` + (e.applied !== e.delta ? ` (modeled ${sign(e.delta)}, limit reached)` : "")));
}

function timeline(run) {
  const track = h("div", { class: "track" }, h("div", { class: "line" }));
  const nowEl = h("div", { class: "now", title: "Today" });
  nowEl.style.left = (run.day / run.durationDays) * 100 + "%";
  track.append(nowEl);
  for (const ms of run.milestones) {
    const el = h("div", { class: "ms" + (ms.reached ? " reached" : "") }, h("i"), ms.label, h("br"), "Day " + ms.day);
    el.style.left = (ms.day / run.durationDays) * 100 + "%";
    track.append(el);
  }
  return track;
}

function chart(run) {
  const W = 400, H = 120, pad = 6;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Measures over time" });
  [0.25, 0.5, 0.75].forEach((f) => root.append(svg("line", { x1: 0, x2: W, y1: H * f, y2: H * f, stroke: "#e3e7ee", "stroke-width": 1 })));
  run.measures.forEach((m, i) => {
    const pts = run.series.map((p) => {
      const x = (p.day / run.durationDays) * (W - 2 * pad) + pad;
      const y = H - pad - ((p.values[m.id] - m.min) / (m.max - m.min)) * (H - 2 * pad);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    root.append(svg("polyline", { points: pts, class: "l" + i }));
  });
  return h("div", null, root, h("div", { class: "legend" }, run.measures.map((m, i) => h("span", { class: "k" + i }, m.label))));
}

function assumptions() {
  if (!app.info) return null;
  return h("details", null, h("summary", null, "Scenario assumptions"),
    h("ul", null, app.info.assumptions.map((a) => h("li", null, a))));
}

function decisionPanel(pd) {
  return h("div", { class: "card decision" },
    h("h2", null, "Decision needed: ", pd.eventTitle),
    h("p", null, pd.eventDescription),
    h("p", null, h("strong", null, pd.prompt)),
    h("div", { class: "options" }, pd.options.map((o) => h("div", { class: "option" },
      h("strong", null, o.label), h("p", null, o.tradeoff),
      h("button", { onclick: () => decide(pd, o.id) }, "Choose this")))),
    pd.queued ? h("p", { class: "muted" }, `${pd.queued} more decision(s) waiting after this one.`) : null);
}

function entryView(e) {
  if (e.type === "event") {
    return h("li", null, h("span", { class: "day" }, "Day " + e.day), h("strong", null, e.title),
      h("div", null, e.description),
      e.effects.length ? h("div", null, effectChips(e.effects)) : null,
      e.bottleneck ? h("div", { class: "muted" }, "New bottleneck: " + e.bottleneck) : null,
      e.decisionRequired ? h("div", { class: "muted" }, "This needed a decision.") : null);
  }
  return h("li", null, h("span", { class: "day" }, "Day " + e.day), h("strong", null, "You decided: " + e.optionLabel),
    h("div", { class: "muted" }, e.prompt),
    h("div", null, "Why it mattered: " + e.tradeoff),
    h("div", null, effectChips(e.effects)),
    e.resolvedBottlenecks.length ? h("div", { class: "muted" }, "Resolved: " + e.resolvedBottlenecks.join(", ")) : null);
}

// ---------- screens ----------
function pickerScreen() {
  return h("div", null, h("h2", null, "Choose a scenario"),
    h("div", { class: "grid two" }, app.scenarios.map((s) => h("div", { class: "card scenario" },
      h("h2", null, s.title), h("p", null, s.description), h("p", { class: "muted" }, s.durationDays + " days"),
      h("button", { onclick: () => start(s.id) }, "Start"),
      h("details", null, h("summary", { onclick: () => loadAssumptions(s.id) }, "Show assumptions"),
        h("ul", { id: "as-" + s.id }, h("li", { class: "muted" }, "Open to load..")))))));
}
async function loadAssumptions(id) {
  const ul = document.getElementById("as-" + id);
  if (!ul || ul.dataset.loaded) return;
  try {
    const info = await api("GET", "/scenarios/" + id);
    ul.replaceChildren(...info.assumptions.map((a) => h("li", null, a)));
    ul.dataset.loaded = "1";
  } catch (e) { ul.replaceChildren(h("li", null, e.message)); }
}

function dashboardScreen() {
  const r = app.run, pd = r.pendingDecision, blocked = r.status !== "running";
  return h("div", null,
    h("div", { class: "bar" },
      h("h2", { class: "grow" }, r.title),
      h("span", { class: "badge" }, `Day ${r.day} / ${r.durationDays}`),
      h("button", { disabled: blocked, onclick: () => advance({ days: 1 }) }, "Advance 1 day"),
      h("button", { disabled: blocked, onclick: () => advance({ days: 7 }) }, "Advance 7 days"),
      h("button", { class: "secondary", disabled: blocked, onclick: () => advance({ untilNextEvent: true }) }, "Next event"),
      h("button", { class: "secondary", onclick: showLog }, "Run log"),
      h("button", { class: "danger", onclick: resetRun }, "Reset")),
    pd ? decisionPanel(pd) : null,
    h("div", { class: "card" }, h("h2", null, "Project status"),
      h("span", { class: "big" }, r.projectStatus.score), " ",
      h("span", { class: "badge " + r.projectStatus.rating.split(" ")[0] }, r.projectStatus.rating),
      h("span", { class: "muted" }, "  overall health, 0-100")),
    h("div", { class: "grid measures" }, r.measures.map((m) => measureCard(m, m.value, app.prev && app.prev[m.id]))),
    h("div", { class: "grid two" },
      h("div", { class: "card" }, h("h2", null, "Timeline"), timeline(r), chart(r)),
      h("div", { class: "card" }, h("h2", null, "Bottlenecks"),
        r.bottlenecks.length ? h("ul", { class: "plain" }, r.bottlenecks.map((b) => h("li", null,
          b.label, " ", h("span", { class: "badge " + (b.source === "measure" ? "critical" : "warning") },
            b.source === "measure" ? "measure" : "since day " + b.sinceDay)))) : h("p", { class: "muted" }, "None right now."))),
    h("div", { class: "card" }, h("h2", null, "Events feed"),
      r.feed.length ? h("ul", { class: "plain" }, r.feed.map(entryView)) : h("p", { class: "muted" }, "Nothing has happened yet. Advance time to begin.")),
    h("div", { class: "card" }, assumptions()));
}

function logScreen() {
  return h("div", null,
    h("div", { class: "bar" }, h("h2", { class: "grow" }, "Run log: what happened and why"),
      h("button", { class: "secondary", onclick: () => goto(app.run.status === "complete" ? "summary" : "dashboard") }, "Back")),
    h("div", { class: "card" }, app.history.length
      ? h("ul", { class: "plain" }, app.history.map(entryView))
      : h("p", { class: "muted" }, "No events or decisions yet.")));
}

function summaryScreen() {
  const s = app.summary, r = app.run;
  const decisions = app.history.filter((e) => e.type === "decision");
  return h("div", null,
    h("div", { class: "bar" }, h("h2", { class: "grow" }, "Final project health: " + r.title)),
    h("div", { class: "card" },
      h("span", { class: "big" }, s.overallScore), " ", h("span", { class: "badge " + s.rating.split(" ")[0] }, s.rating),
      h("p", null, `Strongest area: ${s.best}. Weakest area: ${s.worst}.`),
      h("p", { class: "muted" }, `${s.daysElapsed} days, ${s.eventsFired} events, ${s.decisionsMade} decisions, ${s.openBottlenecks} unresolved bottleneck(s).`)),
    h("div", { class: "grid measures" }, s.measures.map((m) => h("div", { class: "card" },
      h("div", { class: "mlabel" }, m.label),
      h("div", { class: "mvalue" }, m.startValue, " \u2192 ", m.value),
      h("span", { class: "badge " + m.level }, m.level)))),
    h("div", { class: "card" }, h("h2", null, "Your decisions"),
      decisions.length ? h("ul", { class: "plain" }, decisions.map(entryView)) : h("p", { class: "muted" }, "No decisions were made.")),
    h("div", { class: "bar" },
      h("button", { onclick: showLog }, "Explain outcomes (full log)"),
      h("button", { class: "secondary", onclick: startReplay }, "Replay"),
      h("button", { class: "danger", onclick: resetRun }, "Reset and play again"),
      h("button", { class: "secondary", onclick: backToPicker }, "Choose another scenario")),
    h("div", { class: "card" }, assumptions()));
}

function replayScreen() {
  const f = app.frames[app.replayStep], r = app.run, last = app.replayStep >= app.frames.length - 1;
  return h("div", null,
    h("div", { class: "bar" }, h("h2", { class: "grow" }, "Replay: " + r.title),
      h("span", { class: "badge" }, `Step ${app.replayStep} / ${app.frames.length - 1}`),
      h("button", { class: "secondary", disabled: app.replayStep === 0, onclick: () => { stopReplay(); app.replayStep--; render(); } }, "Back"),
      app.timer ? h("button", { onclick: () => { stopReplay(); render(); } }, "Pause")
                : h("button", { onclick: () => { if (last) app.replayStep = 0; playReplay(); render(); } }, last ? "Restart" : "Play"),
      h("button", { class: "secondary", disabled: last, onclick: () => { stopReplay(); app.replayStep++; render(); } }, "Next"),
      h("button", { class: "secondary", onclick: () => goto(r.status === "complete" ? "summary" : "dashboard") }, "Exit replay")),
    h("div", { class: "card" }, h("h2", null, `Day ${f.day}: ${f.label}`),
      f.entry ? h("ul", { class: "plain" }, entryView(f.entry)) : h("p", { class: "muted" }, "Where the project began.")),
    h("div", { class: "grid measures" }, r.measures.map((m) => {
      const prevFrame = app.frames[Math.max(0, app.replayStep - 1)];
      return measureCard(m, f.measures[m.id], prevFrame.measures[m.id]);
    })));
}

// ---------- render ----------
function render() {
  const root = document.getElementById("app");
  const parts = [];
  if (app.error) parts.push(h("div", { class: "error", role: "alert" }, app.error));
  if (app.notice && app.mode === "dashboard") parts.push(h("div", { class: "notice" }, app.notice));
  if (app.mode === "picker" || !app.run) parts.push(pickerScreen());
  else if (app.mode === "dashboard") parts.push(dashboardScreen());
  else if (app.mode === "log") parts.push(logScreen());
  else if (app.mode === "summary") parts.push(summaryScreen());
  else if (app.mode === "replay") parts.push(replayScreen());
  root.replaceChildren(...parts);
}

async function init() {
  try {
    const [list, meta] = await Promise.all([api("GET", "/scenarios"), api("GET", "/meta")]);
    app.scenarios = list.scenarios;
    const r = meta.retention;
    document.getElementById("foot").textContent =
      `Data: runs are anonymous and kept in server memory only; deleted after ${r.runExpiresAfterMinutes} minutes of inactivity, on reset of the server, or when deleted.`;
  } catch (e) { app.error = e.message; }
  render();
}
init();
