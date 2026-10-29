# bench

A web front end for one QEMU session of the board model: a live console, start/pause/reset/stop, the `-d` log, a coverage list of what the guest touched that the model lacks, and read-only monitor views. In the spirit of a board farm, for one emulated board.

**Stock QEMU interfaces only:** QMP, a socket chardev for the console, and `-d`/`-D`. Nothing in the fork knows the bench exists, so it never blocks the fork's shape.

## Run

```bash
uv sync                          # once: .venv/ from pyproject.toml + uv.lock
uv run bench/server.py           # http://127.0.0.1:8090
uv run bench/server.py --port 8091   # a second bench next to the first
```

Pick a profile, press **Start**. Click the console to type.

| Profile | Needs |
|---|---|
| `rzv2l-smarc-m1-probe` | the project QEMU in `build/qemu/` and `aarch64-linux-gnu-gcc` |
| `virt-echo` | stock `qemu-system-aarch64`, `make` and `aarch64-linux-gnu-gcc`; the bench's self-test |

A profile is a small TOML file in [`profiles/`](profiles/): QEMU binary, arguments, an optional prepare step, semihosting on or off, the log mask, and optional expectations. The bench adds the QMP, console and log options itself. `BENCH_QEMU` replaces the project build (a `qemu` value with a `/`, such as `build/qemu/qemu-system-aarch64`); a bare name like `qemu-system-aarch64` stays the stock QEMU on `PATH`.

Each run keeps its command line, console, stderr, QEMU log and `run.json` (profile, times, exit code, verdict) in `build/bench/<time>-<profile>/`. The **Runs** tab lists them, newest first, and opens each one's files.

## Verdict

| Field | Meaning |
|---|---|
| `expect = ["…"]` | exact strings that must all appear on the console: serial and semihosting output. QEMU's stderr and the `-d` log never count |
| `expect_exit = N` | optional: QEMU must exit with status `N`. A run ended by the bench (Stop, a failed start) fails, because QMP `quit` also exits 0 |

The session shows **RUNNING** until the verdict is decided. With `expect_exit` set, **PASS** needs every marker and that exit status. Without it, the verdict turns PASS as soon as the last marker appears, even if the guest keeps running; a run that ends first is **FAIL**. A profile with neither field has no verdict. `GET /api/session` returns `verdict` (`"pass"`, `"fail"`, `"running"` or `null`), `verdict_reasons` and `expect_missing`.

## Coverage export

`GET /api/runs/<run>/coverage.csv` (the **Download CSV** links) has the columns `name, base, size, kind, access, count`:

- An address inside a window of `docs/device-map.md` §1 is counted in one row per window, kind and access; `name`, `base` and `size` are the window's. When windows overlap, the smallest wins.
- An address in no window is its own row: `name` is `unmapped`, `base` is the address, `size` is the access size.
- `unimp` lines give a device and an offset, not an address: `name` is the device, `base` and `size` are blank.
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
| `GET /api/runs/<run>/{console,log,stderr,cmdline}` | that file as text |
| `GET /api/runs/<run>/coverage`, `…/coverage.csv` | its coverage list (JSON, or CSV as above) |
| `WS /ws` | live stream: console, log, status, QMP events |

## Test

```bash
uv run playwright install chromium        # once
uv run pytest bench/tests
```

The test drives the UI on stock QEMU `virt` with a small bare-metal echo program (`tests/virt-echo/`): console in and out, coverage, monitor allow-list, pause, reset, exit status, verdict, the Runs tab, the CSV download and the gdbstub. `test_verdict.py` and `test_device_map.py` check the verdict rules and the window grouping without QEMU. With `BENCH_QEMU` set (or `build/qemu` built), the M1 probe also runs through the bench and must reach PASS.

## Limits

- One session, no authentication: it binds to `127.0.0.1` and refuses requests whose `Host` is not a loopback name or whose `Origin` is another site (a web page in your browser cannot drive it). Don't expose it.
- The coverage list counts every `-d` log line of the run: known forms are grouped by address, anything else is listed verbatim as `other`.
- The verdict is cumulative over the run: a marker seen before a Reset still counts, and console bytes include what the guest echoes back from typed input. Prefer markers the guest prints itself, and `expect_exit` where the guest can exit.
- A run whose `run.json` never reached `exited` (the bench was killed) is listed as `lost`, with no verdict.
- The device-map parser reads sizes from the Size column and per-base `(N MiB)` notes only: a size in other parenthesised text (Display DSI's `0x20000`) is not used, and multi-block rows carry the whole row name.
- Run files and logs are read whole: fine for probes, slow for a long Linux `-d` log.
- `run.sh` stays the source of truth for a probe's verdict (timeout, missing `RESULT:`). The bench verdict is for looking and for scripts: it has no timeout, so a hung guest stays RUNNING until stopped.
- No display panel yet: the board has no display model before M4.
- Profiles for G0 Linux land with M3, when its Image and initramfs are built.
