#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""rzv2l bench: a web front end for one QEMU board session.

It drives QEMU through stock interfaces only: QMP, a socket chardev for the
console (serial and, optionally, semihosting), and the -d/-D log. Nothing in
the fork knows the bench exists.

    python3 bench/server.py                 # http://127.0.0.1:8090
    python3 bench/server.py --port 9000
"""

import argparse
import asyncio
import codecs
import collections
import csv
import ctypes
import io
import json
import os
import re
import shutil
import signal
import socket
import tempfile
import time
import tomllib
from pathlib import Path

from aiohttp import WSMsgType, web

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROFILES = HERE / "profiles"
STATIC = HERE / "static"
RUNS = ROOT / "build" / "bench"
DEVICE_MAP = ROOT / "docs" / "device-map.md"
RUN_ID = re.compile(r"^(?P<stamp>\d{8}-\d{6}-\d{3})-(?P<profile>[\w.-]+)$")

# Read-only HMP commands the monitor panel may run (no writes to host files,
# no state changes; those have their own buttons).
MONITOR_ALLOW = re.compile(r"^info (mtree( -f)?|qtree|roms|registers|pic|irq|"
                           r"status|cpus|chardev|version|qom-tree)$")
CONSOLE_KEEP = 256 * 1024   # bytes of console transcript kept for replay
LOG_KEEP = 5000             # lines of the -d log kept in memory

# Every -d line lands in exactly one coverage row: the forms QEMU's memory core
# and unimplemented-device code print are parsed, anything else (guest_errors,
# other LOG_UNIMP text) is counted verbatim as "other". Nothing is dropped.
# Sources: qemu system/memory.c (rejected/unaligned/invalid size),
# system/physmem.c (non-RAM device), hw/misc/unimp.c, per-device
# "unimplemented read/write at offset" messages.
LOG_FORMS = [
    ("invalid_mem", re.compile(
        r"Invalid (?P<access>read|write) at addr 0x(?P<addr>[0-9A-Fa-f]+), "
        r"size (?P<size>\d+), region '[^']*', reason: (?P<reason>.+)$")),
    ("invalid_mem", re.compile(
        r"Invalid access to non-RAM device at addr 0x(?P<addr>[0-9A-Fa-f]+), "
        r"size (?P<size>\d+), region '(?P<reason>[^']*)'")),
    ("unimp", re.compile(
        r"^(?P<dev>[\w.-]+): unimplemented device (?P<access>read|write)\s+"
        r"\(size (?P<size>\d+), offset 0x(?P<off>[0-9A-Fa-f]+)")),
    ("unimp", re.compile(
        r"^(?P<dev>\w+): unimplemented (?P<access>read|write) at offset "
        r"0x(?P<off>[0-9A-Fa-f]+)")),
]


def classify(line):
    """Coverage row key (kind, access, where, size, detail) for one log line."""
    for kind, rx in LOG_FORMS:
        if m := rx.search(line):
            g = m.groupdict()
            if "addr" in g:
                where = f"0x{int(g['addr'], 16):08x}"
            else:
                where = f"{g['dev']}+0x{int(g['off'], 16):x}"
            return (kind, g.get("access") or "access", where,
                    g.get("size") or "", g.get("reason") or "")
    return ("other", "", line.strip(), "", "")


def count_log(path):
    """Coverage counter of a -d log file on disk (a finished or past run)."""
    cov = collections.Counter()
    if path.exists():
        with path.open("r", errors="replace") as f:
            for line in f.read().split("\n"):
                cov[classify(line)] += 1
    return cov


def coverage_rows(cov):
    return [{"kind": k, "access": a, "where": w, "size": s, "detail": d,
             "count": n}
            for (k, a, w, s, d), n in cov.most_common()]


# -- device-map windows ------------------------------------------------------
#
# The coverage export groups addresses by the windows of docs/device-map.md
# section 1. The tables are prose, so the parser reads a bounded set of forms
# and reports every row it cannot pair cleanly instead of guessing silently.

_HEX = r"0x[0-9A-Fa-f]+"
_SIZE = re.compile(rf"`({_HEX})`|(\d+) ([KMG])iB")
_UNIT = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}
_BASE = re.compile(rf"`(?P<a>{_HEX})(?:(?P<op>[-+])(?P<b>{_HEX}))?`"
                   rf"(?:\s+to\s+`(?P<to>{_HEX})`)?(?:\s*\{{(?P<sz>[^}}]+)\}})?")


def _strip_parens(text):
    while True:
        out = re.sub(r"\([^()]*\)", "", text)
        if out == text:
            return out
        text = out


def _sizes(text):
    return [int(h, 16) if h else int(n) * _UNIT[u]
            for h, n, u in _SIZE.findall(text)]


def parse_device_map(text):
    """(windows, warnings) from the section 1 tables of docs/device-map.md.

    A window is {"name", "base", "size"}. Forms read in the Base cell:
    `0xA`, `0xA-0xB` (inclusive range), `0xA+0xB` (offset), `0xA` to `0xB`,
    a per-base "(N MiB)", and "`0xA` + n×`0xS`" with n taken from the block
    name. Other parenthesised text is ignored. Sizes: hex or "N KiB/MiB/GiB",
    paired by position, or one size for every base.
    """
    start = text.find("\n## 1.")
    end = text.find("\n## 2.", start)
    windows, warnings = [], []
    for line in text[start:end].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("| ") or len(cells) < 3 or cells[0] == "Block":
            continue
        raw_name, base_cell, size_cell = cells[:3]
        if "`0x" not in base_cell:
            continue                                 # "—", "per Table 5.1"
        name = " ".join(_strip_parens(raw_name).replace("`", "").split())
        name = name.replace(" ,", ",")
        cell = re.sub(r"\((\d+ [KMG]iB)\)", r"{\1}", base_cell)
        stride = re.search(rf"\+\s*n×`({_HEX})`", cell)
        cell = _strip_parens(cell[:stride.start()] if stride else cell)
        bases = []                                   # [base, size or None]
        for m in _BASE.finditer(cell):
            a = int(m["a"], 16)
            b = int(m["b"], 16) if m["b"] else None
            if m["op"] == "+":
                a, b = a + b, None
            size = (b - a + 1) if b is not None else None
            if m["to"]:
                size = int(m["to"], 16) - a + 1
            if m["sz"]:
                size = _sizes(m["sz"])[0]
            bases.append([a, size])
        if stride and bases:
            step = int(stride[1], 16)
            first = bases[0][0]
            idx = [int(n) for n in re.findall(r"[A-Za-z]+(\d+)", name)]
            bases = [[first + i * step, None] for i in idx] or bases
        sizes = _sizes(_strip_parens(size_cell))
        open_ = [b for b in bases if b[1] is None]
        if len(sizes) == len(open_):
            for b, size in zip(open_, sizes):
                b[1] = size
        elif sizes and open_:
            if len(sizes) > 1:
                warnings.append(f"{name}: {len(open_)} bases, {len(sizes)} "
                                f"sizes; using {sizes[0]:#x} for each")
            for b in open_:
                b[1] = sizes[0]
        elif open_:
            warnings.append(f"{name}: no size; base(s) skipped")
        names = [n.strip() for n in name.split(",")]
        for i, (base, size) in enumerate(bases):
            if size:
                windows.append({"name": names[i] if len(names) == len(bases)
                                else name, "base": base, "size": size})
    return windows, warnings


def load_device_map(path=DEVICE_MAP):
    try:
        return parse_device_map(path.read_text())
    except OSError as e:
        return [], [f"{path.name}: {e.strerror}"]


def find_window(windows, addr):
    """The smallest device-map window that contains addr, or None."""
    hits = [w for w in windows if w["base"] <= addr < w["base"] + w["size"]]
    return min(hits, key=lambda w: w["size"]) if hits else None


CSV_FIELDS = ["name", "base", "size", "kind", "access", "count"]


def coverage_csv(cov, windows):
    """CSV of a coverage counter, addresses grouped by device-map window.

    One row per (window, kind, access) with the window's base and size; an
    address in no window is its own "unmapped" row (base = the address,
    size = the access size). unimp rows carry a device offset, not an
    address: name = the device, base and size blank. Free-text lines are
    summed into one "other" row.
    """
    rows = collections.Counter()
    for (kind, access, where, size, _detail), n in cov.items():
        if kind == "other":
            key = ("other", "", "", kind, "")
        elif where.startswith("0x"):
            addr = int(where, 16)
            w = find_window(windows, addr)
            key = ((w["name"], f"0x{w['base']:08x}", f"0x{w['size']:x}",
                    kind, access) if w else
                   ("unmapped", where, size, kind, access))
        else:
            key = (where.split("+")[0], "", "", kind, access)
        rows[key] += n
    out = io.StringIO()
    wr = csv.writer(out, lineterminator="\n")
    wr.writerow(CSV_FIELDS)
    for key, n in sorted(rows.items(), key=lambda kv: (-kv[1], kv[0])):
        wr.writerow([*key, n])
    return out.getvalue()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _die_with_parent():
    """Child side of fork: QEMU gets SIGKILL if the bench process dies."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl(1, signal.SIGKILL)          # PR_SET_PDEATHSIG


def load_profiles():
    profiles = {}
    for path in sorted(PROFILES.glob("*.toml")):
        with path.open("rb") as f:
            p = tomllib.load(f)
        for key in ("name", "qemu", "args"):
            if key not in p:
                raise SystemExit(f"{path}: missing '{key}'")
        p.setdefault("description", "")
        p.setdefault("prepare", [])
        p.setdefault("semihosting", False)
        p.setdefault("log", "unimp,guest_errors,invalid_mem")
        p.setdefault("expect", [])
        p.setdefault("expect_exit", None)
        if not (isinstance(p["expect"], list)
                and all(isinstance(m, str) and m for m in p["expect"])):
            raise SystemExit(f"{path}: 'expect' must be a list of non-empty strings")
        if p["expect_exit"] is not None and type(p["expect_exit"]) is not int:
            raise SystemExit(f"{path}: 'expect_exit' must be an integer")
        profiles[path.stem] = p
    return profiles


def resolve_qemu(spec):
    """A profile's QEMU. BENCH_QEMU replaces the project build (a path in the
    profile); a bare name (stock QEMU, the self-test) is looked up on PATH."""
    if "/" in spec:
        return os.environ.get("BENCH_QEMU") or str(ROOT / spec)
    return shutil.which(spec) or spec


class QMP:
    """Minimal async QMP client: commands with ids, events to a callback."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.reader = self.writer = None
        self.pending = {}
        self.next_id = 0
        self.task = None

    async def connect(self, path, alive, timeout=10.0):
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.reader, self.writer = await asyncio.open_unix_connection(path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if not alive():
                    raise RuntimeError("QEMU exited before QMP came up "
                                       "(see the console for its message)")
                if time.monotonic() > deadline:
                    raise
                await asyncio.sleep(0.05)
        await self.reader.readline()                      # greeting
        self.task = asyncio.create_task(self._read())
        await self.cmd("qmp_capabilities")

    async def _read(self):
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                msg = json.loads(line)
                if "event" in msg:
                    await self.on_event(msg)
                elif msg.get("id") in self.pending:
                    fut = self.pending.pop(msg["id"])
                    if not fut.done():          # a timed-out caller is gone
                        fut.set_result(msg)
        finally:
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("QMP closed"))
            self.pending.clear()

    async def cmd(self, execute, arguments=None, timeout=10.0):
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.next_id] = fut
        req = {"execute": execute, "id": self.next_id}
        if arguments:
            req["arguments"] = arguments
        self.writer.write(json.dumps(req).encode() + b"\n")
        await self.writer.drain()
        try:
            msg = await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(req["id"], None)
        if "error" in msg:
            raise RuntimeError(msg["error"].get("desc", "QMP error"))
        return msg.get("return")

    def close(self):
        if self.writer:
            self.writer.close()
        if self.task:
            self.task.cancel()


class Session:
    """One QEMU process with its QMP, console and log."""

    def __init__(self, bench, profile_id, profile, gdb=False):
        self.bench = bench
        self.profile_id = profile_id
        self.profile = profile
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() // 10**6 % 1000:03d}"
        self.run_dir = RUNS / f"{stamp}-{profile_id}"
        self.run_dir.mkdir(parents=True)
        # Unix socket paths are limited to ~108 bytes: keep them short
        self.sock_dir = Path(tempfile.mkdtemp(prefix="bench-"))
        self.log_path = self.run_dir / "qemu.log"
        self.state = "starting"
        self.exit_code = None
        self.error = None
        self.started = time.time()
        self.argv = []
        self.proc = None
        self.qmp = QMP(self._on_qmp_event)
        self.con_writer = None
        self.semi_writer = None     # kept: a dropped writer closes the socket on GC
        self.console = bytearray()
        self.log_lines = collections.deque(maxlen=LOG_KEEP)
        self.log_total = 0
        self.cov = collections.Counter()   # all lines, not just the kept ones
        self.tail_task = None
        self.tasks = []
        self.con_tasks = []
        self.found = set()          # expect markers seen on the console
        self.stopped = False        # ended by the bench (Stop, failed start)
        self.ended = None
        self.gdb_port = free_port() if gdb else None

    # -- lifecycle ---------------------------------------------------------

    def build_argv(self):
        p = self.profile
        qmp = self.sock_dir / "qmp.sock"
        con = self.sock_dir / "con.sock"
        argv = [resolve_qemu(p["qemu"]), *p["args"],
                "-display", "none", "-nodefaults", "-S",
                "-qmp", f"unix:{qmp},server=on,wait=off",
                "-chardev", f"socket,id=con,path={con},server=on,wait=off",
                "-serial", "chardev:con"]
        if p["semihosting"]:
            # A chardev takes one frontend: semihosting gets its own socket,
            # merged into the console stream (output only).
            semi = self.sock_dir / "semi.sock"
            argv += ["-chardev", f"socket,id=semi,path={semi},server=on,wait=off",
                     "-semihosting-config", "enable=on,target=native,chardev=semi"]
        if p["log"]:
            argv += ["-d", p["log"], "-D", str(self.log_path)]
        if self.gdb_port:
            # -s would listen on every interface at a fixed port; -S is above
            argv += ["-gdb", f"tcp:127.0.0.1:{self.gdb_port}"]
        return argv

    async def start(self, paused):
        try:
            await self._prepare()
            self.argv = self.build_argv()
            (self.run_dir / "cmdline.txt").write_text(" ".join(self.argv) + "\n")
            self.write_meta()
            await self._emit("stderr", "$ " + " ".join(self.argv) + "\n")
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, cwd=ROOT, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                start_new_session=True, preexec_fn=_die_with_parent)
            self.tasks.append(asyncio.create_task(self._pump_stderr()))
            self.tasks.append(asyncio.create_task(self._watch_exit()))
            await self.qmp.connect(str(self.sock_dir / "qmp.sock"),
                                   lambda: self.proc.returncode is None)
            reader, self.con_writer = await asyncio.open_unix_connection(
                str(self.sock_dir / "con.sock"))
            self.con_tasks.append(asyncio.create_task(self._pump_console(reader)))
            if self.profile["semihosting"]:
                semi, self.semi_writer = await asyncio.open_unix_connection(
                    str(self.sock_dir / "semi.sock"))
                self.con_tasks.append(asyncio.create_task(self._pump_console(semi)))
            self.tasks += self.con_tasks
            self.tail_task = asyncio.create_task(self._tail_log())
            self.tasks.append(self.tail_task)
            if paused or self.gdb_port:     # with gdb, the debugger resumes
                await self._set_state("paused")
            else:
                await self.qmp.cmd("cont")
                await self._set_state("running")
        except Exception as e:  # noqa: BLE001 - reported to the UI
            self.error = str(e) or type(e).__name__
            await self._emit("stderr", f"bench: start failed: {self.error}\n")
            self.stopped = True
            await self.kill()
            self.ended = time.time()
            await self._set_state("exited")
            self.write_meta()
            if not self.proc:       # no exit watcher will clean up
                shutil.rmtree(self.sock_dir, ignore_errors=True)

    async def _prepare(self):
        cmd = self.profile["prepare"]
        if not cmd:
            return
        await self._emit("stderr", "$ " + " ".join(cmd) + "\n")
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=ROOT, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), 600)
        if out:
            await self._emit("stderr", out.decode(errors="replace"))
        if proc.returncode:
            raise RuntimeError(f"prepare step exited {proc.returncode}")

    async def stop(self):
        if self.state == "exited":
            return
        self.stopped = True
        try:
            await self.qmp.cmd("quit", timeout=3)
        except Exception:  # noqa: BLE001 - fall back to a kill
            pass
        try:
            await asyncio.wait_for(self.proc.wait(), 5)
        except (asyncio.TimeoutError, AttributeError):
            await self.kill()

    async def kill(self):
        if self.proc and self.proc.returncode is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)   # by PID, never pkill
            except ProcessLookupError:
                pass
            await self.proc.wait()

    async def _watch_exit(self):
        rc = await self.proc.wait()
        self.exit_code = rc
        # The verdict needs every console byte: let the pumps reach EOF
        if self.con_tasks:
            await asyncio.wait(self.con_tasks, timeout=2)
        else:
            await asyncio.sleep(0.2)
        self.qmp.close()
        # ... and the -d log its last read, so "exited" means complete
        if self.tail_task:
            try:
                await asyncio.wait_for(asyncio.shield(self.tail_task), 5)
            except asyncio.TimeoutError:
                pass
        self.ended = time.time()
        await self._set_state("exited")
        for t in self.tasks:
            if t is not asyncio.current_task() and not t.done():
                t.cancel()
        self.write_meta()
        shutil.rmtree(self.sock_dir, ignore_errors=True)

    # -- streams -----------------------------------------------------------

    async def _reported(self, name, coro):
        """Run a stream task; if it dies, say so instead of going quiet."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - reported to the UI
            await self._emit("stderr", f"bench: {name} stopped: {e!r}\n")

    async def _pump_stderr(self):
        await self._reported("stderr pump", self._pump_stderr_inner())

    async def _pump_stderr_inner(self):
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        with (self.run_dir / "stderr.log").open("ab") as f:
            while line := await self.proc.stdout.readline():
                f.write(line)
                f.flush()
                await self._emit("stderr", dec.decode(line))

    async def _pump_console(self, reader):
        await self._reported("console pump", self._pump_console_inner(reader))

    async def _pump_console_inner(self, reader):
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        markers = [m.encode() for m in self.profile["expect"]]
        keep = max((len(m) for m in markers), default=1) - 1
        tail = b""                  # a marker may straddle two reads
        with (self.run_dir / "console.log").open("ab") as f:
            while data := await reader.read(4096):
                f.write(data)
                f.flush()
                if markers and len(self.found) < len(markers):
                    window = tail + data
                    before = len(self.found)
                    self.found.update(m.decode() for m in markers if m in window)
                    tail = window[-keep:] if keep else b""
                    if len(self.found) != before:
                        await self.bench.broadcast(
                            {"t": "status", "d": self.status()})
                self.console += data
                if len(self.console) > CONSOLE_KEEP:
                    del self.console[:len(self.console) - CONSOLE_KEEP]
                await self._emit("con", dec.decode(data))

    async def _tail_log(self):
        await self._reported("log tail", self._tail_log_inner())

    async def _tail_log_inner(self):
        pos = 0
        partial = ""
        while True:
            # QEMU gone: read once more, then stop
            exited = self.exit_code is not None or self.state == "exited"
            if self.log_path.exists():
                with self.log_path.open("r", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                lines = (partial + chunk).split("\n")
                partial = lines.pop()           # keep an unfinished line
                if exited and partial:
                    lines.append(partial)
                    partial = ""
                for line in lines:
                    self.log_lines.append(line)
                    self.log_total += 1
                    self.cov[classify(line)] += 1
                    await self._emit("log", line)
            if exited:
                return
            await asyncio.sleep(0.3)

    async def write_console(self, text):
        if self.con_writer and self.state != "exited":
            self.con_writer.write(text.encode())
            await self.con_writer.drain()

    # -- QMP ---------------------------------------------------------------

    async def _on_qmp_event(self, msg):
        await self.bench.broadcast({"t": "event", "d": msg})
        name = msg["event"]
        if name == "STOP":
            await self._set_state("paused")
        elif name == "RESUME":
            await self._set_state("running")

    async def monitor(self, cmd):
        return await self.qmp.cmd("human-monitor-command",
                                  {"command-line": cmd})

    # -- views -------------------------------------------------------------

    def coverage(self):
        """Every -d log line of the run, grouped (see LOG_FORMS)."""
        return coverage_rows(self.cov)

    def verdict(self):
        """(verdict, reasons) from the profile's expect / expect_exit.

        None without expectations. "running" until decided; with no
        expect_exit, "pass" as soon as every marker has appeared.
        """
        expect, want = self.profile["expect"], self.profile["expect_exit"]
        if not expect and want is None:
            return None, []
        missing = [m for m in expect if m not in self.found]
        if self.error:
            return "fail", [f"start failed: {self.error}"]
        if self.state != "exited":
            if want is None and not missing:
                return "pass", []
            return "running", []
        reasons = [f"missing on the console: {m!r}" for m in missing]
        if want is not None:
            if self.stopped:
                reasons.append("stopped by the bench before the guest exited")
            elif self.exit_code != want:
                reasons.append(f"exit {self.exit_code}, expected {want}")
        return ("fail" if reasons else "pass"), reasons

    def status(self):
        verdict, reasons = self.verdict()
        return {"state": self.state, "profile": self.profile_id,
                "name": self.profile["name"],
                "pid": self.proc.pid if self.proc else None,
                "exit_code": self.exit_code, "error": self.error,
                "verdict": verdict, "verdict_reasons": reasons,
                "expect": self.profile["expect"],
                "expect_exit": self.profile["expect_exit"],
                "expect_missing": [m for m in self.profile["expect"]
                                   if m not in self.found],
                "gdb_port": self.gdb_port,
                "uptime": round(time.time() - self.started, 1),
                "run": self.run_dir.name,
                "run_dir": str(self.run_dir.relative_to(ROOT)),
                "cmdline": " ".join(self.argv)}

    def write_meta(self):
        """run.json: what the Runs tab lists once the bench forgets the run."""
        meta = {k: v for k, v in self.status().items()
                if k not in ("pid", "uptime")}
        meta.update(started=self.started, ended=self.ended)
        (self.run_dir / "run.json").write_text(json.dumps(meta, indent=1) + "\n")

    async def _set_state(self, state):
        if self.state != state:
            self.state = state
            await self.bench.broadcast({"t": "status", "d": self.status()})

    async def _emit(self, kind, data):
        await self.bench.broadcast({"t": kind, "d": data})


class Bench:
    def __init__(self):
        self.profiles = load_profiles()
        self.windows, self.map_warnings = load_device_map()
        self.session = None
        self.clients = set()

    async def broadcast(self, msg):
        text = json.dumps(msg)
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except ConnectionError:
                self.clients.discard(ws)

    def live(self):
        return self.session and self.session.state != "exited"

    def run_dir(self, run_id):
        """A run directory by its name; None unless it is one, under RUNS."""
        if not RUN_ID.match(run_id or ""):
            return None
        path = RUNS / run_id
        return path if path.is_dir() and path.parent == RUNS else None

    def run_info(self, path):
        s = self.session
        if s and s.run_dir == path:
            meta = s.status()
            meta.update(started=s.started, ended=s.ended)
        else:
            try:
                meta = json.loads((path / "run.json").read_text())
            except (OSError, ValueError):
                meta = {}           # a run from before run.json: name only
        m = RUN_ID.match(path.name)
        meta.setdefault("profile", m["profile"])
        meta.setdefault("state", "exited")
        for key in ("exit_code", "verdict", "started", "ended", "name"):
            meta.setdefault(key, None)
        meta["run"] = path.name
        meta["files"] = [f for f in RUN_FILES
                         if (path / RUN_FILES[f]).exists()]
        return meta

    def runs(self):
        dirs = [p for p in RUNS.glob("*") if p.is_dir() and RUN_ID.match(p.name)]
        return [self.run_info(p) for p in sorted(dirs, key=lambda p: p.name,
                                                  reverse=True)]


RUN_FILES = {"console": "console.log", "log": "qemu.log",
             "stderr": "stderr.log", "cmdline": "cmdline.txt"}


def json_error(status, msg):
    return web.json_response({"error": msg}, status=status)


def same_origin_guard(port):
    hosts = {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")}

    @web.middleware
    async def guard(req, handler):
        if req.host not in hosts:
            return json_error(403, f"unexpected Host {req.host!r}")
        origin = req.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in hosts}:
            return json_error(403, f"cross-origin request from {origin!r}")
        if req.method == "POST" and req.can_read_body \
                and req.content_type != "application/json":
            return json_error(415, "POST bodies must be application/json")
        return await handler(req)
    return guard


def make_app(port=8090):
    bench = Bench()
    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_):
        return web.FileResponse(STATIC / "index.html")

    @routes.get("/api/profiles")
    async def profiles(_):
        return web.json_response([
            {"id": k, "name": p["name"], "description": p["description"]}
            for k, p in bench.profiles.items()])

    @routes.get("/api/session")
    async def session_status(_):
        if not bench.session:
            return web.json_response({"state": "none"})
        return web.json_response(bench.session.status())

    @routes.post("/api/session")
    async def session_start(req):
        body = await req.json()
        pid = body.get("profile")
        if pid not in bench.profiles:
            return json_error(400, f"unknown profile {pid!r}")
        if bench.live():
            return json_error(409, "a session is running; stop it first")
        bench.session = Session(bench, pid, bench.profiles[pid],
                                gdb=bool(body.get("gdb")))
        await bench.session.start(bool(body.get("paused")))
        status = bench.session.status()
        return web.json_response(status, status=500 if status["error"] else 200)

    def need_live(handler):
        async def wrapped(req):
            if not bench.live():
                return json_error(409, "no running session")
            try:
                return await handler(req)
            except (RuntimeError, ConnectionError, asyncio.TimeoutError) as e:
                return json_error(500, str(e))
        return wrapped

    @routes.post("/api/session/stop")
    async def session_stop(_):
        if bench.session:
            await bench.session.stop()
        return web.json_response(bench.session.status() if bench.session
                                 else {"state": "none"})

    @routes.post("/api/session/{action:reset|pause|resume}")
    @need_live
    async def session_action(req):
        qmp_cmd = {"reset": "system_reset", "pause": "stop",
                   "resume": "cont"}[req.match_info["action"]]
        await bench.session.qmp.cmd(qmp_cmd)
        return web.json_response(bench.session.status())

    @routes.post("/api/session/monitor")
    @need_live
    async def session_monitor(req):
        cmd = ((await req.json()).get("cmd") or "").strip()
        if not MONITOR_ALLOW.match(cmd):
            return json_error(403, f"not an allowed read-only command: {cmd!r}")
        return web.json_response({"cmd": cmd,
                                  "output": await bench.session.monitor(cmd)})

    @routes.get("/api/session/console")
    async def console_get(_):
        s = bench.session
        return web.json_response(
            {"text": s.console.decode(errors="replace") if s else ""})

    @routes.post("/api/session/console")
    @need_live
    async def console_post(req):
        await bench.session.write_console((await req.json()).get("data", ""))
        return web.json_response({"ok": True})

    @routes.get("/api/session/log")
    async def log_get(_):
        s = bench.session
        if not s:
            return web.json_response({"lines": [], "coverage": []})
        return web.json_response({"lines": list(s.log_lines),
                                  "lines_total": s.log_total,
                                  "coverage": s.coverage()})

    @routes.get("/api/runs")
    async def runs_list(_):
        return web.json_response(bench.runs())

    def need_run(handler):
        async def wrapped(req):
            path = bench.run_dir(req.match_info["run"])
            if not path:
                return json_error(404, "no such run")
            return await handler(req, path)
        return wrapped

    @routes.get("/api/runs/{run}")
    @need_run
    async def run_get(_, path):
        return web.json_response(bench.run_info(path))

    @routes.get("/api/runs/{run}/coverage.csv")
    @need_run
    async def run_coverage_csv(_, path):
        s = bench.session
        cov = s.cov if s and s.run_dir == path else count_log(path / "qemu.log")
        return web.Response(
            text=coverage_csv(cov, bench.windows), content_type="text/csv",
            headers={"Content-Disposition":
                     f'attachment; filename="{path.name}-coverage.csv"'})

    @routes.get("/api/runs/{run}/coverage")
    @need_run
    async def run_coverage(_, path):
        s = bench.session
        cov = s.cov if s and s.run_dir == path else count_log(path / "qemu.log")
        return web.json_response({"coverage": coverage_rows(cov),
                                  "map_warnings": bench.map_warnings})

    @routes.get("/api/runs/{run}/{file:console|log|stderr|cmdline}")
    @need_run
    async def run_file(req, path):
        f = path / RUN_FILES[req.match_info["file"]]
        if not f.exists():
            return json_error(404, f"this run has no {f.name}")
        return web.Response(text=f.read_text(errors="replace"),
                            content_type="text/plain")

    @routes.get("/ws")
    async def ws_handler(req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        bench.clients.add(ws)
        s = bench.session
        await ws.send_str(json.dumps({"t": "hello", "d": {
            "status": s.status() if s else {"state": "none"},
            "console": s.console.decode(errors="replace") if s else "",
            "log": list(s.log_lines) if s else []}}))
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("t") == "key" and bench.live():
                    await bench.session.write_console(data.get("d", ""))
        finally:
            bench.clients.discard(ws)
        return ws

    async def on_shutdown(_):
        if bench.session:
            await bench.session.stop()
        for ws in list(bench.clients):
            await ws.close()

    app = web.Application(middlewares=[same_origin_guard(port)])
    app.add_routes(routes)
    app.router.add_static("/static/", STATIC)
    app.on_shutdown.append(on_shutdown)
    app["bench"] = bench
    return app


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; the bench has no auth)")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    web.run_app(make_app(args.port), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
