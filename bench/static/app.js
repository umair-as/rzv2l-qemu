// rzv2l bench front end. One session at a time; all state comes from /ws.
"use strict";

const $ = (id) => document.getElementById(id);
const KEEP = 256 * 1024;  // console transcript characters kept in the DOM

// ---- per-browser settings (storage may be missing or throw) ------------------

const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* keep going */ } },
};

// ---- terminal and theme --------------------------------------------------------

const term = new Terminal({
  convertEol: false, cursorBlink: true, fontSize: 13, scrollback: 5000,
  fontFamily: 'ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace',
});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open($("term"));
new ResizeObserver(() => fit.fit()).observe($("term"));

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
let themeChoice = "system";

function termTheme() {
  // The terminal takes its colours from the page tokens (style.css)
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    background: v("--term-bg"), foreground: v("--term-ink"),
    cursor: v("--term-cursor"), cursorAccent: v("--term-bg"),
    selectionBackground: v("--term-sel"),
  };
}

function applyTheme(choice, save) {
  themeChoice = ["light", "dark"].includes(choice) ? choice : "system";
  if (themeChoice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = themeChoice;
  document.querySelectorAll("[data-theme-choice]").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.themeChoice === themeChoice)));
  term.options.theme = termTheme();
  if (save) store.set("bench.theme", themeChoice);
}

document.querySelectorAll("[data-theme-choice]").forEach((b) => {
  b.onclick = () => applyTheme(b.dataset.themeChoice, true);
});
darkQuery.addEventListener("change", () => {
  if (themeChoice === "system") term.options.theme = termTheme();
});
applyTheme(store.get("bench.theme"), false);

let profiles = [];
let state = "none";
let ws;

// ---- console settings (display and keyboard only; bytes stay raw) ------------

const ENTER = { cr: "\r", lf: "\n", crlf: "\r\n" };

function applyConsoleSettings() {
  term.options.convertEol = $("lf-crlf").checked;   // draws \n as \r\n
}

function consoleDefaults() {
  const p = profiles.find((x) => x.id === $("profile").value);
  const c = (p && p.console) || { lf_to_crlf: false, enter: "cr" };
  $("lf-crlf").checked = c.lf_to_crlf;
  $("enter-sends").value = c.enter;
  applyConsoleSettings();
}

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
  consoleDefaults();
}

function showDesc() {
  const p = profiles.find((x) => x.id === $("profile").value);
  $("profile-desc").textContent = p ? p.description : "";
  showAssets(p);
}

// Before Start: is the QEMU binary there, and the guest files (or a step that builds them)?
function showAssets(p) {
  const chip = $("assets");
  const a = p && p.assets;
  chip.hidden = !a;
  if (!a) return;
  chip.dataset.status = a.status;
  const missing = a.files.filter((f) => !f.exists).map((f) => f.path);
  chip.textContent = { ready: "ready", builds: "builds on Start", missing: "missing" }[a.status];
  const lines = [`QEMU: ${a.qemu} ${a.qemu_ok ? "(found)" : "(not found or not executable)"}`];
  a.files.forEach((f) => lines.push(`${f.option} ${f.path} ${f.exists ? "(found)" : "(missing)"}`));
  if (missing.length && a.prepare) lines.push("The prepare step runs on Start and should build the missing files.");
  chip.title = lines.join("\n");
}

async function refreshAssets() {
  try {
    profiles = await api("GET", "/api/profiles");
    showDesc();
  } catch (e) { /* keep the last view */ }
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
  $("cmdline").hidden = true;
  showCoverageEmpty(0);
}

function fmtDuration(sec) {
  if (sec == null || sec < 0) return "";
  if (sec < 10) return `${sec.toFixed(1)} s`;
  if (sec < 120) return `${Math.round(sec)} s`;
  const m = Math.floor(sec / 60);
  return `${m} min ${Math.round(sec - m * 60)} s`;
}

// The readout: state, then the verdict only when a profile has markers.
// While a verdict is pending it shows marker progress instead of a second
// "running"; PASS/FAIL replace it once decided.
function showReadout(s) {
  const r = $("readout");
  r.dataset.state = s.state;
  r.dataset.verdict = s.verdict === "pass" || s.verdict === "fail" ? s.verdict : "";

  const v = $("verdict");
  v.dataset.verdict = s.verdict || "";
  v.textContent = (s.verdict || "").toUpperCase();
  v.hidden = !(s.verdict === "pass" || s.verdict === "fail");

  const markers = $("markers");
  const expect = s.expect || [];
  markers.hidden = !(s.verdict === "running" && expect.length);
  markers.textContent = `markers ${expect.length - (s.expect_missing || []).length}/${expect.length}`;

  const why = $("verdict-why");
  const reasons = s.verdict === "fail" ? s.verdict_reasons || [] : [];
  why.hidden = !reasons.length;
  why.textContent = reasons.join("; ");

  const mach = $("machine");
  mach.hidden = !s.machine;
  mach.textContent = s.machine || "";
  const pid = $("pid");
  pid.hidden = !(s.pid && s.state !== "exited");
  pid.textContent = s.pid ? `pid ${s.pid}` : "";

  const dur = $("duration");
  dur.hidden = !(s.state === "exited" && s.started && s.ended);
  dur.textContent = dur.hidden ? "" : fmtDuration(s.ended - s.started);

  const gdb = $("gdb-info");
  gdb.hidden = !(s.gdb_port && s.state !== "exited");
  gdb.dataset.port = s.gdb_port || "";
  gdb.textContent = s.gdb_port
    ? `gdbstub on 127.0.0.1:${s.gdb_port} · gdb-multiarch -ex "target remote 127.0.0.1:${s.gdb_port}", then continue in gdb`
    : "";

  const csv = $("cov-csv");
  csv.hidden = !s.run;
  if (s.run) csv.href = `/api/runs/${encodeURIComponent(s.run)}/coverage.csv`;

  if (s.run && s.run !== viewRun && s.state !== "starting") loadViews(s.run);

  if (s.cmdline) {
    $("cmdline").hidden = false;
    $("cmdline-text").textContent = s.cmdline;
    $("cmdline-bin").textContent = s.cmdline.split(" ")[0].split("/").pop();
  }
}

function appendPre(id, line) {
  const pre = $(id);
  const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 4;
  pre.textContent += line.endsWith("\n") ? line : line + "\n";
  if (atEnd) pre.scrollTop = pre.scrollHeight;
}

// QEMU's own command line is long: the Command line block holds it in full
function appendStderr(text) {
  if (text.startsWith("$ ") && text.includes(" -qmp unix:")) {
    const bin = text.slice(2).split(" ")[0].split("/").pop();
    appendPre("log", `$ ${bin} … (full command: Command line, above)`);
  } else {
    appendPre("log", text);
  }
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
  showReadout(s);
  showConsoleHint();
  const exit = $("exit");
  if (state === "exited") {
    exit.hidden = false;
    exit.textContent = s.error ? `error: ${s.error}` : `exit ${s.exit_code}`;
    exit.dataset.code = s.exit_code ?? "";
    refreshCoverage();
    refreshAssets();
    if (runsShown()) refreshRuns();
  } else {
    exit.hidden = true;
  }
  if (s.profile && live && $("profile").value !== s.profile) {
    $("profile").value = s.profile;
    showDesc();
    consoleDefaults();
  }
}

let covTimer;
function refreshCoverageSoon() {
  clearTimeout(covTimer);
  covTimer = setTimeout(refreshCoverage, 300);
}

function showCoverageEmpty(rows) {
  const empty = $("cov-empty");
  empty.hidden = rows > 0;
  empty.textContent = state === "none"
    ? "Start a session to see what the guest touches outside the model."
    : state === "exited"
      ? "Nothing touched outside the model in this run."
      : "Nothing touched outside the model so far.";
  document.querySelector('[data-testid="coverage-table"]').hidden = rows === 0;
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
  showCoverageEmpty(coverage.length);
  if (viewRun && mapShown()) loadViews(viewRun);
}

// ---- map and devices (captured at start, kept with the run) ----------------

let viewRun = null;
let mapRows = [];
let mapFilter = "all";
let mapExtra = [];
let devTree = [];

async function loadViews(run) {
  viewRun = run;
  const enc = encodeURIComponent(run);
  try {
    const m = await api("GET", `/api/runs/${enc}/map`);
    mapRows = m.windows;
    mapExtra = m.extra;
    renderMap();
  } catch (e) { mapRows = []; mapExtra = []; renderMap(e.message); }
  try {
    devTree = (await api("GET", `/api/runs/${enc}/devices`)).tree;
  } catch (e) { devTree = []; }
  renderDevices();
}

function renderMap(error) {
  const extra = mapFilter === "all" ? mapExtra : [];
  const shown = mapRows.filter((r) => mapFilter === "all"
    || (mapFilter === "live" && r.status !== "missing")
    || (mapFilter === "missing" && r.status === "missing")
    || (mapFilter === "hits" && r.hits > 0));
  const body = $("map");
  body.innerHTML = "";
  for (const r of shown) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", "map-row");
    tr.dataset.status = r.status;
    tr.dataset.hits = r.hits;
    tr.dataset.base = r.base;
    const nm = cell(tr, "", "wname");
    const nspan = document.createElement("span");
    nspan.textContent = r.name; nspan.title = r.name;
    nm.append(nspan);
    const at = cell(tr, r.base, "at");
    const sz = document.createElement("span");
    sz.className = "rname"; sz.textContent = ` +${r.size}`;
    at.append(sz);
    const live = cell(tr, "", "regions");
    const st = document.createElement("span");
    st.className = "st"; st.dataset.status = r.status; st.dataset.partial = String(r.partial);
    st.textContent = r.status;
    st.title = r.partial ? "The live regions cover only part of this window" : "";
    live.append(st);
    if (r.regions.length) {
      const rn = document.createElement("div");
      rn.className = "rname"; rn.textContent = r.regions.join(", ");
      live.append(rn);
    }
    cell(tr, r.hits, "hits");
    // The milestone's first word (M2, M3b, later); the full plan on hover
    const plan = cell(tr, (r.milestone.match(/^[\w-]+/) || [""])[0], "plan");
    plan.title = [r.milestone, r.plan].filter(Boolean).join(" · ");
    body.append(tr);
  }
  const counts = { modelled: 0, ram: 0, unimp: 0, missing: 0 };
  mapRows.forEach((r) => { counts[r.status] += 1; });
  $("map-summary").textContent = mapRows.length
    ? `${counts.modelled} modelled · ${counts.ram} RAM · ${counts.unimp} UNIMP · ${counts.missing} missing`
    : "";
  const empty = $("map-empty");
  empty.hidden = mapRows.length > 0;
  if (error) empty.textContent = error.charAt(0).toUpperCase() + error.slice(1) + ".";
  document.querySelector('[data-testid="map-table"]').hidden = mapRows.length === 0;

  const ex = $("map-extra-rows");
  ex.innerHTML = "";
  (extra || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", "map-extra-row");
    cell(tr, r.name); cell(tr, r.base); cell(tr, r.size); cell(tr, r.kind);
    ex.append(tr);
  });
  $("map-extra").hidden = !(extra && extra.length);
}

document.querySelectorAll("[data-map-filter]").forEach((b) => {
  b.onclick = () => {
    mapFilter = b.dataset.mapFilter;
    document.querySelectorAll("[data-map-filter]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
    renderMap();
  };
});

function nodeText(n) {
  return [n.label, ...n.props].join("\n").toLowerCase();
}

// A node is shown when it, or anything below it, matches the filter
function renderNode(n, q, depth) {
  const kids = n.children.map((c) => renderNode(c, q, depth + 1)).filter(Boolean);
  const hit = q && nodeText(n).includes(q);
  if (q && !hit && !kids.length) return null;
  const d = document.createElement("details");
  d.setAttribute("data-testid", n.kind === "dev" ? "device-node" : "bus-node");
  d.open = q ? true : depth < 1;
  const sum = document.createElement("summary");
  const k = document.createElement("span");
  k.className = "k"; k.textContent = n.kind + " ";
  const t = document.createElement(hit ? "mark" : "span");
  t.className = "t"; t.textContent = n.label;
  sum.append(k, t);
  d.append(sum);
  if (n.props.length) {
    const props = document.createElement("div");
    props.className = "props";
    n.props.forEach((line) => {
      const row = document.createElement("div");
      row.textContent = line;
      props.append(row);
    });
    d.append(props);
  }
  kids.forEach((c) => d.append(c));
  return d;
}

function renderDevices() {
  const q = $("dev-filter").value.trim().toLowerCase();
  const tree = $("dev-tree");
  tree.innerHTML = "";
  devTree.map((n) => renderNode(n, q, 0)).filter(Boolean).forEach((d) => tree.append(d));
  tree.hidden = devTree.length === 0;
  const empty = $("dev-empty");
  empty.hidden = devTree.length > 0 && tree.children.length > 0;
  if (devTree.length && !tree.children.length) empty.textContent = `Nothing matches “${q}”.`;
  else empty.textContent = "Start a session: its device tree is read before the guest runs.";
}
$("dev-filter").addEventListener("input", renderDevices);

// ---- runs ------------------------------------------------------------------

let currentRun = null;
const LOST_WHY = "The bench stopped (killed or restarted) before this run ended, "
  + "so it has no exit code or verdict. Its console and log are kept.";

function mapShown() {
  return !document.querySelector('[data-panel="map"]').hidden;
}

function runsShown() {
  return !document.querySelector('[data-panel="runs"]').hidden;
}

function fmtTime(t) {
  if (!t) return "";
  const d = new Date(t * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function cell(tr, text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  tr.append(td);
  return td;
}

async function refreshRuns() {
  const hideTests = $("hide-tests").checked;
  const runs = (await api("GET", "/api/runs"))
    .filter((r) => !(hideTests && r.origin === "test"));
  const body = $("runs");
  body.innerHTML = "";
  for (const r of runs) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-testid", "run-row");
    tr.dataset.run = r.run;
    tr.dataset.origin = r.origin || "";
    tr.setAttribute("aria-selected", String(r.run === currentRun));

    const prof = cell(tr, "");
    const name = document.createElement("span");
    name.className = "name"; name.textContent = r.profile; name.title = r.profile;
    prof.append(name);
    if (r.origin === "test") {
      const tag = document.createElement("span");
      tag.className = "tag"; tag.textContent = "test";
      tag.title = "Started by the bench's own tests";
      prof.append(tag);
    }
    cell(tr, fmtTime(r.started) || r.run.slice(0, 15)).title =
      r.started ? new Date(r.started * 1000).toLocaleString() : "";
    const exit = cell(tr, r.exit_code ?? (r.state === "exited" ? "" : r.state));
    if (r.state === "lost") { exit.className = "lost"; exit.title = LOST_WHY; }
    const v = cell(tr, r.verdict ? r.verdict.toUpperCase() : "", "v");
    v.dataset.verdict = r.verdict || "";
    if (r.verdict_reasons && r.verdict_reasons.length) v.title = r.verdict_reasons.join("; ");
    cell(tr, r.started && r.ended ? fmtDuration(r.ended - r.started) : "");

    tr.onclick = () => openRun(r.run);
    body.append(tr);
  }
  $("runs-empty").hidden = runs.length > 0;
  $("runs-empty").textContent = hideTests
    ? "No runs besides test runs. Clear “Hide test runs” to see them."
    : "No runs yet. Start a session and it is kept here.";
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
$("hide-tests").checked = store.get("bench.hideTests") === "1";
$("hide-tests").onchange = () => {
  store.set("bench.hideTests", $("hide-tests").checked ? "1" : "0");
  refreshRuns();
};

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
      case "stderr": appendStderr(m.d); break;
      case "log": appendPre("log", m.d); refreshCoverageSoon(); break;
      case "event": appendPre("events", JSON.stringify(m.d)); break;
      case "status": setStatus(m.d); break;
    }
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

// Above the terminal: where keys go in this state, so typing never vanishes silently
const CON_HINT = {
  none: "Start a session to type",
  starting: "Starting…",
  running: "serial + semihosting · click to type",
  paused: "Paused: keys are queued; the guest sees them on Resume",
  exited: "Run ended: keys go nowhere. Start to type again",
};

function showConsoleHint() {
  const h = $("con-hint");
  h.dataset.state = state;
  h.textContent = CON_HINT[state] || CON_HINT.none;
}

let nudgeTimer;
term.onData((d) => {
  if (!(state === "running" || state === "paused")) {
    // Typed with no guest to receive it: say so where the eye already is
    const h = $("con-hint");
    h.classList.add("nudge");
    clearTimeout(nudgeTimer);
    nudgeTimer = setTimeout(() => h.classList.remove("nudge"), 1200);
    return;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    // Enter arrives as \r: send what the profile or the menu asks for
    ws.send(JSON.stringify({ t: "key", d: d.replace(/\r/g, ENTER[$("enter-sends").value]) }));
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

$("profile").addEventListener("change", () => { showDesc(); consoleDefaults(); });
$("lf-crlf").onchange = applyConsoleSettings;
$("start").onclick = () => start(false);
$("start-paused").onclick = () => start(true);
$("pause").onclick = () => action(state === "paused" ? "/api/session/resume" : "/api/session/pause");
$("reset").onclick = () => action("/api/session/reset");
$("stop").onclick = () => action("/api/session/stop");
$("cmdline-copy").onclick = async () => {
  const b = $("cmdline-copy");
  try {
    await navigator.clipboard.writeText($("cmdline-text").textContent);
    b.textContent = "Copied";
  } catch (e) {
    // No clipboard access (plain http on a non-loopback name): select instead
    getSelection().selectAllChildren($("cmdline-text"));
    b.textContent = "Selected";
  }
  setTimeout(() => { b.textContent = "Copy"; }, 1500);
};

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
    if ((b.dataset.tab === "map" || b.dataset.tab === "devices") && viewRun) loadViews(viewRun);
  };
});

loadProfiles().then(connect);
