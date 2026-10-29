---
name: bench-drive
description: Run the rzv2l bench (bench/server.py) and drive a QEMU session through its web UI with the Playwright MCP tools, or through its HTTP API — start a profile, type on the console, read the transcript, the coverage list and monitor views. Use when a task needs to see the model run interactively, or to demo or check a change end to end.
---

# Driving the bench

What the bench is, how to run it and its API: `bench/README.md`. It uses only stock QEMU interfaces; never change the fork for it.

## Traps

- **Stopping the server:** record the PID of the Python process itself. `uv run` is a wrapper: killing its PID can leave the server holding the port. Never stop it with `pkill -f`/`pgrep -f` on its name: the pattern matches your own shell's command line and kills it.
- **Profile values are IDs** (the TOML file stem, e.g. `rzv2l-smarc-m1-probe`), not the display names.
- **The terminal input is a hidden textarea:** click region "Terminal" first, then send keys. `[data-testid=…]` selectors are stable across runs.
- **Requests need loopback `Host` and no foreign `Origin`;** POST bodies are JSON. A 403/415 from your own script means a wrong header, not a bench bug.
- **Typed input counts for the verdict:** the guest's echo of what you type lands on the console, so typing a profile's `expect` string satisfies it. Never type a marker into a run you are verifying.
- **Chromium in a root container** may refuse its sandbox. Add `--no-sandbox` to a local, uncommitted copy of `.mcp.json`; never commit it.

## Rules

- Evidence from the bench is evidence from a run: record the profile, the run directory (`build/bench/<time>-<profile>/` holds the command line and logs) and the QEMU commit.
- The monitor accepts read-only `info …` commands only. State changes go through the buttons or the API.
- The bench is not acceptance: milestone acceptance and probe verdicts stay in `tests/acceptance/` and the probe's `run.sh`. Use the bench to look, then write the test (`qtest-golden`, `guest-probe`).
- For checks without a screen, the HTTP API gives the same data faster than the browser.
- Read a run's result from `verdict` in `GET /api/session` (or `run.json` in its run directory) instead of scanning the console; a profile gets one through `expect` and `expect_exit` (`bench/README.md`). RUNNING has no timeout: stop a hung run yourself.
- Ask for coverage as CSV (`/api/runs/<run>/coverage.csv`) when comparing it with `docs/device-map.md`; `unmapped` rows are addresses in no window of the map.
- After changing the bench, run its tests (`bench/tests/`), including the M1 probe test, which needs the project QEMU build.
