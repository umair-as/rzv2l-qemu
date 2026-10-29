// rzv2l bench front end. One session at a time; all state comes from /ws.
"use strict";

const $ = (id) => document.getElementById(id);
const KEEP = 256 * 1024;  // console transcript characters kept in the DOM

const term = new Terminal({
  convertEol: false, cursorBlink: true, fontSize: 13, scrollback: 5000,
  fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace',
  theme: { background: "#10141c", foreground: "#d8dee9" },
});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open($("term"));
fit.fit();
window.addEventListener("resize", () => fit.fit());

let profiles = [];
let state = "none";
let ws;

// ---- REST ------------------------------------------------------------------

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: body ? { "content-type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function loadProfiles() {
  profiles = await api("GET", "/api/profiles");
  $("profile").innerHTML = "";
  for (const p of profiles) {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.name;
    $("profile").append(o);
  }
  showDesc();
}

function showDesc() {
  const p = profiles.find((x) => x.id === $("profile").value);
  $("profile-desc").textContent = p ? p.description : "";
}

// ---- view ------------------------------------------------------------------

function appendConsole(text) {
  term.write(text);
  const pre = $("console-text");
  pre.textContent = (pre.textContent + text).slice(-KEEP);
}

function resetViews() {
  term.reset();
  $("console-text").textContent = "";
  $("log").textContent = "";
  $("events").textContent = "";
  $("monitor-out").textContent = "";
  $("coverage").innerHTML = "";
  $("cov-count").textContent = "0";
}

function showVerdict(s) {
  const v = $("verdict");
  v.hidden = !s.verdict;
  v.dataset.verdict = s.verdict || "";
  v.textContent = (s.verdict || "").toUpperCase();
  const why = $("verdict-why");
  const reasons = s.verdict_reasons || [];
  why.hidden = !reasons.length;
  why.textContent = reasons.join("; ");
  const gdb = $("gdb-info");
  gdb.hidden = !(s.gdb_port && s.state !== "exited");
  gdb.dataset.port = s.gdb_port || "";
  gdb.textContent = s.gdb_port
    ? `gdbstub on 127.0.0.1:${s.gdb_port}: gdb-multiarch -ex "target remote 127.0.0.1:${s.gdb_port}"`
    : "";
  const csv = $("cov-csv");
  csv.hidden = !s.run;
  if (s.run) csv.href = `/api/runs/${encodeURIComponent(s.run)}/coverage.csv`;
}

function appendPre(id, line) {
  const pre = $(id);
  const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 4;
  pre.textContent += line.endsWith("\n") ? line : line + "\n";
  if (atEnd) pre.scrollTop = pre.scrollHeight;
}

function setStatus(s) {
  state = s.state;
  const pill = $("state");
  pill.dataset.state = state;
  pill.textContent = state === "none" ? "no session" : state;
  const live = state === "running" || state === "paused" || state === "starting";
  $("start").disabled = live;
  $("start-paused").disabled = live;
  $("profile").disabled = live;
  $("stop").disabled = !live;
  $("reset").disabled = !live;
  $("pause").disabled = !(state === "running" || state === "paused");
  $("pause").textContent = state === "paused" ? "Resume" : "Pause";
  $("gdb").disabled = live;
  showVerdict(s);
  const exit = $("exit");
  if (state === "exited") {
    exit.hidden = false;
    exit.textContent = s.error ? `error: ${s.error}` : `exit ${s.exit_code}`;
    exit.dataset.code = s.exit_code ?? "";
    refreshCoverage();
    if (runsShown()) refreshRuns();
  } else {
    exit.hidden = true;
  }
  if (s.profile && live) $("profile").value = s.profile;
}

let covTimer;
function refreshCoverageSoon() {
  clearTimeout(covTimer);
  covTimer = setTimeout(refreshCoverage, 300);
}

async function refreshCoverage() {
  const { coverage } = await api("GET", "/api/session/log");
  const body = $("coverage");
  body.innerHTML = "";
  for (const r of coverage) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", "coverage-row");
    for (const v of [r.kind, r.access, r.where, r.size, r.count]) {
      const td = document.createElement("td");
      td.textContent = v;
      tr.append(td);
    }
    body.append(tr);
  }
  $("cov-count").textContent = String(coverage.length);
}

// ---- runs ------------------------------------------------------------------

let currentRun = null;

function runsShown() {
  return !document.querySelector('[data-panel="runs"]').hidden;
}

function fmtTime(t) {
  return t ? new Date(t * 1000).toLocaleString() : "";
}

async function refreshRuns() {
  const runs = await api("GET", "/api/runs");
  const body = $("runs");
  body.innerHTML = "";
  for (const r of runs) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", "run-row");
    tr.dataset.run = r.run;
    tr.setAttribute("aria-selected", String(r.run === currentRun));
    const cells = [r.profile, fmtTime(r.started) || r.run.slice(0, 15),
                   r.exit_code ?? (r.state === "exited" ? "" : r.state),
                   r.verdict ? r.verdict.toUpperCase() : ""];
    cells.forEach((v, i) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (i === 3) { td.className = "verdict"; td.dataset.verdict = r.verdict || ""; }
      tr.append(td);
    });
    tr.onclick = () => openRun(r.run);
    body.append(tr);
  }
}

async function openRun(id) {
  currentRun = id;
  document.querySelectorAll("#runs tr").forEach((tr) =>
    tr.setAttribute("aria-selected", String(tr.dataset.run === id)));
  $("run-view").hidden = false;
  $("run-name").textContent = id;
  $("run-csv").href = `/api/runs/${encodeURIComponent(id)}/coverage.csv`;
  await showRunFile("console");
}

let runFileSeq = 0;
async function showRunFile(file) {
  const seq = ++runFileSeq;           // a slower earlier fetch must not win
  const res = await fetch(`/api/runs/${encodeURIComponent(currentRun)}/${file}`);
  const text = res.ok ? await res.text()
    : `(${file}: ${(await res.json().catch(() => ({}))).error || res.statusText})`;
  if (seq !== runFileSeq) return;
  $("run-out").textContent = text;
  $("run-out").dataset.file = file;
}

document.querySelectorAll("#run-view button[data-file]").forEach((b) => {
  b.onclick = () => showRunFile(b.dataset.file);
});

// ---- websocket ---------------------------------------------------------------

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    switch (m.t) {
      case "hello":
        resetViews();
        appendConsole(m.d.console);
        m.d.log.forEach((l) => appendPre("log", l));
        setStatus(m.d.status);
        if (m.d.status.state !== "none") refreshCoverage();
        break;
      case "con": appendConsole(m.d); break;
      case "stderr": appendPre("log", m.d); break;
      case "log": appendPre("log", m.d); refreshCoverageSoon(); break;
      case "event": appendPre("events", JSON.stringify(m.d)); break;
      case "status": setStatus(m.d); break;
    }
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

term.onData((d) => {
  if (ws && ws.readyState === WebSocket.OPEN && (state === "running" || state === "paused")) {
    ws.send(JSON.stringify({ t: "key", d }));
  }
});

// ---- controls ----------------------------------------------------------------

async function start(paused) {
  resetViews();
  setStatus({ state: "starting" });
  try {
    await api("POST", "/api/session",
              { profile: $("profile").value, paused, gdb: $("gdb").checked });
    term.focus();
  } catch (e) {
    appendPre("log", `bench: ${e.message}`);
  }
}

async function action(path) {
  try { await api("POST", path); } catch (e) { appendPre("log", `bench: ${e.message}`); }
}

async function monitor(cmd) {
  $("monitor-out").textContent = `(qemu) ${cmd}\n…`;
  try {
    const r = await api("POST", "/api/session/monitor", { cmd });
    $("monitor-out").textContent = `(qemu) ${cmd}\n${r.output}`;
  } catch (e) {
    $("monitor-out").textContent = `(qemu) ${cmd}\n${e.message}`;
  }
}

$("profile").addEventListener("change", showDesc);
$("start").onclick = () => start(false);
$("start-paused").onclick = () => start(true);
$("pause").onclick = () => action(state === "paused" ? "/api/session/resume" : "/api/session/pause");
$("reset").onclick = () => action("/api/session/reset");
$("stop").onclick = () => action("/api/session/stop");

document.querySelectorAll("[data-panel=monitor] .chips button").forEach((b) => {
  b.onclick = () => monitor(b.dataset.cmd);
});
$("monitor-form").onsubmit = (e) => {
  e.preventDefault();
  const cmd = $("monitor-input").value.trim();
  if (cmd) monitor(cmd);
};

document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) =>
      x.setAttribute("aria-selected", String(x === b)));
    document.querySelectorAll(".tab-body").forEach((p) => {
      p.hidden = p.dataset.panel !== b.dataset.tab;
    });
    if (b.dataset.tab === "coverage" && state !== "none") refreshCoverage();
    if (b.dataset.tab === "runs") refreshRuns();
  };
});

loadProfiles().then(connect);
