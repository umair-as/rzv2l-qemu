# bench

A web front end for one QEMU session of the board model: a live console, start/pause/reset/stop, the `-d` log, a coverage list of what the guest touched that the model lacks, and read-only monitor views. In the spirit of a board farm, for one emulated board.

**Stock QEMU interfaces only:** QMP, a socket chardev for the console, and `-d`/`-D`. Nothing in the fork knows the bench exists, so it never blocks the fork's shape.

## Run

```bash
uv sync                          # once: .venv/ from pyproject.toml + uv.lock
uv run bench/server.py           # http://127.0.0.1:8090
```

Pick a profile, press **Start**. Click the console to type.

| Profile | Needs |
|---|---|
| `rzv2l-smarc-m1-probe` | the project QEMU in `build/qemu/` and `aarch64-linux-gnu-gcc` |
| `virt-echo` | stock `qemu-system-aarch64`, `make` and `aarch64-linux-gnu-gcc`; the bench's self-test |

A profile is a small TOML file in [`profiles/`](profiles/): QEMU binary, arguments, an optional prepare step, semihosting on or off, and the log mask. The bench adds the QMP, console and log options itself. Set `BENCH_QEMU` to override the binary.

Each run keeps its command line, console, stderr and QEMU log in `build/bench/<time>-<profile>/`.

## API (for scripts and agents)

| Call | Does |
|---|---|
| `GET /api/profiles` | list profiles |
| `POST /api/session` `{"profile", "paused"}` | start (one session at a time) |
| `GET /api/session` | state, pid, exit code, run directory |
| `POST /api/session/{pause,resume,reset,stop}` | QMP `stop` / `cont` / `system_reset` / `quit` |
| `GET` / `POST /api/session/console` | transcript / send `{"data": "..."}` |
| `GET /api/session/log` | log lines and the coverage list |
| `POST /api/session/monitor` `{"cmd"}` | read-only `info …` commands only |
| `WS /ws` | live stream: console, log, status, QMP events |

## Test

```bash
uv run playwright install chromium        # once
uv run pytest bench/tests
```

The test drives the UI on stock QEMU `virt` with a small bare-metal echo program (`tests/virt-echo/`): console in and out, coverage, monitor allow-list, pause, reset and exit status.

## Limits

- One session, no authentication: it binds to `127.0.0.1` and refuses requests whose `Host` is not a loopback name or whose `Origin` is another site (a web page in your browser cannot drive it). Don't expose it.
- The coverage list counts every `-d` log line of the run: known forms are grouped by address, anything else is listed verbatim as `other`.
- `run.sh` stays the source of truth for a probe's verdict (timeout, missing `RESULT:`); the bench shows the run and QEMU's exit status.
- No display panel yet: the board has no display model before M4.
- Profiles for G0 Linux land with M3, when its Image and initramfs are built.
