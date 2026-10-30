# bench

A web front end for one QEMU session of the board model: a live console, start/pause/reset/stop, the `-d` log, a coverage list of what the guest touched that the model lacks, and read-only monitor views. In the spirit of a board farm, for one emulated board.

**Stock QEMU interfaces only:** QMP, a socket chardev for the console, and `-d`/`-D`. Nothing in the fork knows the bench exists, so it never blocks the fork's shape.

## Run

```bash
uv sync                          # once: .venv/ from pyproject.toml + uv.lock
uv run bench/server.py           # http://127.0.0.1:8090
uv run bench/server.py --port 8091   # a second bench next to the first
```

Pick a profile, press **Start**. Click the console to type; the line above it says where keys go in each state. The console takes every key, Tab included: **Ctrl+]** (as in telnet) hands focus back to the page, to the side panel's tabs, which the arrow keys walk.

The header holds the profile, the run controls and the readout, the one status line: an LED (green running, amber paused, red failed, dim idle), the session state, then PASS or FAIL once a profile with markers is decided (marker progress while it runs), the exit status and the run time. A FAIL names what was missing just below the header. The status bar at the bottom carries the run directory, machine and pid, and **System / Light / Dark**, which sets the theme, terminal included; the choice is kept per browser. The bar between the console and the side panel shares the width (drag it, or focus it and use the arrow keys; double-click for the default); the split is kept per browser too. The full QEMU command line sits in a collapsed, copyable block at the top of the Log tab. The Log, and a run's files in **Runs**, have a search box: Enter and Shift+Enter walk the matches, which are highlighted over the text without changing it.

| Profile | Needs |
|---|---|
| `rzv2l-smarc-m1-probe` | the project QEMU in `build/qemu/` and `aarch64-linux-gnu-gcc` |
| `virt-echo` | stock `qemu-system-aarch64`, `make` and `aarch64-linux-gnu-gcc`; the bench's self-test |

A profile is a small TOML file in [`profiles/`](profiles/): QEMU binary, arguments, an optional prepare step, semihosting on or off, the log mask, and optional expectations. The bench adds the QMP, console and log options itself. `BENCH_QEMU` replaces the project build (a `qemu` value with a `/`, such as `build/qemu/qemu-system-aarch64`); a bare name like `qemu-system-aarch64` stays the stock QEMU on `PATH`.

Each run keeps its command line, console, stderr, QEMU log and `run.json` (profile, times, exit code, verdict, origin) in `build/bench/<time>-<profile>/`. The **Runs** tab lists them, newest first, with their duration, and opens each one's files. Runs started by the bench's own tests (`BENCH_RUN_ORIGIN=test`, set by `bench/tests`) carry a *test* tag and can be hidden. **Only FAIL or lost** narrows the list to the runs that need a look; each row has a verdict stripe. A run picked here is shown as *past run* in Map and Devices, so it cannot pass for the live session.

## Console settings

Like a serial terminal's map options, per profile, and in the console's **Settings** menu for the current session:

| Profile key | Menu | Default | Effect |
|---|---|---|---|
| `[console] lf_to_crlf` | Show lone LF as CRLF | `false` | the terminal draws a bare `\n` as a new line at column 0 |
| `[console] enter` | Enter sends | `"cr"` | what the Enter key sends: `"cr"`, `"lf"` or `"crlf"` |

The defaults are raw, so a Linux shell is untouched. The M1 probe sets `lf_to_crlf = true`: semihosting text ends lines with a bare `\n`. The map is display only: the transcript, `console.log`, the API and the verdict always hold the guest's bytes. A menu change is kept per profile in this browser; **Profile defaults** in the menu goes back to the TOML.

## What emulation shows that silicon can't

Read-only views, from stock QEMU monitor commands the bench runs itself at start (before the guest runs), kept with the run as `mtree.txt` and `qtree.txt`:

- **Map:** `info mtree -f` (the `memory` address space) against the windows of `docs/device-map.md` §1. Each window is *modelled*, *RAM*, *UNIMP* (an `unimplemented-device`, known by its `name` property in `info qtree`), *covered* (only a larger region lies across it, such as virt's PCIe window; nothing in the build fits the window) or *missing*, marked *part* when the regions that fit cover only part of it. Each window also shows the live region names, the coverage hits from the `-d` log (absolute addresses, and `unimp` offsets placed through the device's base), and the milestone that needs it, with the full plan on hover. Regions that fit in no window are listed below the table. Hits the Map cannot place are listed above it, never dropped: an address in no window, or a device's own unimplemented-access message, which logs a function name and an offset but no address (SYSC's `rzg2l_sysc_read+0x0`). The tab names the run it shows; picking a run in **Runs** shows that run's map, until **Show the current session**. Filters: in this build, missing, hit. Above the table, an address strip draws every window as one equal segment in address order (not to scale: DDR alone would fill it), coloured by its status, with a tick where the guest hit it; clicking a segment finds its row. `GET /api/runs/<run>/map`.
- **Devices:** `info qtree` as a tree you can filter by type, name or property, with a match count, expand/collapse all, and properties in two columns. `GET /api/runs/<run>/devices`.
- **Readiness:** next to the profile picker, before Start. *ready*; *builds on Start* (guest files missing, but the prepare step makes them); *missing* (no executable QEMU, or files nothing builds). The tooltip lists each file. `GET /api/profiles` returns it as `assets`.

Not built yet, because nothing in the model needs them:

| View | Needs |
|---|---|
| LCD panel (QMP `screendump`) | a display model (DU/DSI, M4) |
| Board LEDs | the GPIO model (PFC, M3b) |
| Snapshots (`savevm`/`loadvm`) | a writable block device; direct mode has none |
| Swap a kernel or DTB without editing the profile | M3 Linux bring-up, if it needs it |

## Verdict

| Field | Meaning |
|---|---|
| `expect = ["…"]` | exact strings that must all appear on the console: serial and semihosting output. QEMU's stderr and the `-d` log never count |
| `expect_exit = N` | optional: QEMU must exit with status `N`. A run ended by the bench (Stop, a failed start) fails, because QMP `quit` also exits 0 |

The session shows **RUNNING** until the verdict is decided. With `expect_exit` set, **PASS** needs every marker and that exit status. Without it, the verdict turns PASS as soon as the last marker appears, even if the guest keeps running; a run that ends first is **FAIL**. Only console output since the last Start or reset counts: a QMP `RESET` event (the Reset button or a guest-initiated reset) forgets every marker seen before it, and the terminal draws a reset line there (display only). The reasons then say *missing since the last reset*. A profile with neither field has no verdict. `GET /api/session` returns `verdict` (`"pass"`, `"fail"`, `"running"` or `null`), `verdict_reasons` and `expect_missing`.

## Coverage export

`GET /api/runs/<run>/coverage.csv` (the **Download CSV** links) has the columns `name, base, size, kind, access, count`:

- An address inside a window of `docs/device-map.md` §1 is counted in one row per window, kind and access; `name`, `base` and `size` are the window's. When windows overlap, the smallest wins.
- An address in no window is its own row: `name` is `unmapped`, `base` is the address, `size` is the access size.
- `unimp` lines give a name and an offset, not an address. An `unimplemented-device`'s offset is placed through its base from the run's `info qtree`. Any other (a device's own message, often a function name) is an `unplaced:<prefix>+<offset>` row with `base` and `size` blank.
- Free-text lines (`other`) are summed into one row.

The map's tables are prose. Rows whose bases and sizes do not pair are listed in `map_warnings` of `GET /api/runs/<run>/coverage`; never edit the map to suit the parser.

## Debugging with gdb

**Start with gdbstub** adds `-gdb tcp:127.0.0.1:<port>` on a free loopback port (`-s` would listen on every interface, on a fixed port) and starts paused. The port is shown under the header and returned as `gdb_port`. Connect with `gdb-multiarch -ex "target remote 127.0.0.1:<port>"`; `continue` in gdb resumes the guest. The option adds no monitor commands.

## API (for scripts and agents)

| Call | Does |
|---|---|
| `GET /api/profiles` | list profiles |
| `POST /api/session` `{"profile", "paused", "gdb"}` | start (one session at a time) |
| `GET /api/session` | state, pid, exit code, verdict, gdb port, run directory |
| `POST /api/session/{pause,resume,reset,stop}` | QMP `stop` / `cont` / `system_reset` / `quit` |
| `GET` / `POST /api/session/console` | transcript / send `{"data": "..."}` |
| `GET /api/session/log` | log lines and the coverage list |
| `POST /api/session/monitor` `{"cmd"}` | read-only `info …` commands only |
| `GET /api/runs` | every run in `build/bench/`, newest first |
| `GET /api/runs/<run>` | one run's `run.json`, or the live status |
| `GET /api/runs/<run>/{console,log,stderr,cmdline,mtree,qtree}` | that file as text |
| `GET /api/runs/<run>/map`, `…/devices` | the Map and Devices views (JSON) |
| `GET /api/runs/<run>/coverage`, `…/coverage.csv` | its coverage list (JSON, or CSV as above) |
| `WS /ws` | live stream: console, log, status, QMP events |

## Test

```bash
uv run playwright install chromium        # once
uv run pytest bench/tests
```

The test drives the UI on stock QEMU `virt` with a small bare-metal echo program (`tests/virt-echo/`): console in and out, coverage, monitor allow-list, pause, reset, exit status, verdict, the Runs tab, the CSV download and the gdbstub. `test_verdict.py` and `test_device_map.py` check the verdict rules and the window grouping without QEMU; `test_tokens.py` checks WCAG AA contrast for every colour-token text pair in both themes. The readout LED and verdict, the splitter, the Map strip, search, the Runs filter and Devices are tested in the page with its live stream closed, also without QEMU. With `BENCH_QEMU` set (or `build/qemu` built), the M1 probe also runs through the bench and must reach PASS.

## Limits

- No local echo or local line editing in the console: every guest so far echoes its own input (or reads none). Added when a guest needs it.

- One session, no authentication: it binds to `127.0.0.1` and refuses requests whose `Host` is not a loopback name or whose `Origin` is another site (a web page in your browser cannot drive it). Don't expose it.
- The coverage list counts every `-d` log line of the run: known forms are grouped by address, anything else is listed verbatim as `other`.
- Console bytes include what the guest echoes back from typed input: typing a marker string can satisfy it. Never type a profile's marker into the run you are checking.
- A reset clears the markers when QMP reports it; output still in flight at that instant (a few bytes printed just before the reset) can still count.
- A run whose `run.json` never reached `exited` (the bench was killed) is listed as `lost`, with no verdict.
- The device-map parser reads sizes from the Size column and per-base `(N MiB)` notes only: a size in other parenthesised text (Display DSI's `0x20000`) is not used, and multi-block rows carry the whole row name.
- Run files and logs are read whole: fine for probes, slow for a long Linux `-d` log.
- `run.sh` stays the source of truth for a probe's verdict (timeout, missing `RESULT:`). The bench verdict is for looking and for scripts: it has no timeout, so a hung guest stays RUNNING until stopped.
- No display panel yet: the board has no display model before M4.
- Profiles for G0 Linux land with M3, when its Image and initramfs are built.
