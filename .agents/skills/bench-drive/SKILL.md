---
name: bench-drive
description: Run the rzv2l bench (bench/server.py) and drive a QEMU session through its web UI with the Playwright MCP tools, or through its HTTP API — start a profile, type on the console, read the transcript, the coverage list and monitor views. Use when a task needs to see the model run interactively, or to demo or check a change end to end.
---

# Driving the bench

What the bench is and its API: `bench/README.md`. The bench uses only stock QEMU interfaces; never change the fork for it.

## Start the server

```bash
mkdir -p build/bench
python3 bench/server.py --port 8090 > build/bench/server.log 2>&1 &
echo $! > build/bench/server.pid     # stop it later with: kill "$(cat build/bench/server.pid)"
```

Never stop it with `pkill -f`/`pgrep -f` on its name: the pattern matches your own shell's command line and kills it.

## Drive the UI (Playwright MCP)

The project `.mcp.json` registers a headless Playwright MCP server. A snapshot shows the page as roles and names; a tool `target` takes a snapshot ref or a CSS selector, and `[data-testid=…]` selectors are stable across runs.

| To | Do |
|---|---|
| open | `browser_navigate` `http://127.0.0.1:8090` |
| pick a profile | `browser_select_option` on combobox "Profile" (`[data-testid=profile-select]`), value = the profile's name |
| start | `browser_click` `[data-testid=btn-start]` (or `btn-start-paused`) |
| see the state | snapshot: status "Session status" (`running`, `paused`, `exited`); status "Exit status" after exit |
| read output | snapshot: log "Console transcript" (plain text of the terminal) |
| type | `browser_click` region "Terminal", then `browser_press_key` per key (`Enter` for return). `browser_type` has no target: the terminal's input is a hidden textarea |
| pause, reset, stop | buttons "Pause"/"Resume", "Reset", "Stop" |
| log, coverage, monitor | tabs "Log", "Coverage", "Monitor" (buttons mtree, qtree, roms, registers, pic; log "Monitor output"), "Events" |

A local container that runs as root may refuse Chromium's sandbox ("Chromium sandboxing failed"). Then add `--no-sandbox` to the server args in a local, uncommitted copy of the config; never commit it.

## Or skip the browser

For checks that need no screen, the HTTP API is faster and gives the same data:

```bash
curl -s -XPOST localhost:8090/api/session -H 'content-type: application/json' -d '{"profile":"rzv2l-smarc-m1-probe"}'
curl -s localhost:8090/api/session/console      # transcript
curl -s localhost:8090/api/session/log          # log lines + coverage list
```

## Rules

- Evidence from the bench is evidence from a run: record the profile, the run directory (`build/bench/<time>-<profile>/` holds the command line and logs) and the QEMU commit.
- The monitor accepts read-only `info …` commands only. State changes go through the buttons or the API.
- The bench is not acceptance: milestone acceptance stays in `tests/acceptance/`. Use the bench to look, then write the test (`qtest-golden`, `guest-probe`).
- After changing the bench, run `python3 -m pytest bench/tests/test_e2e.py`.
