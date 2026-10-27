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
import collections
import json
import os
import re
import shutil
import signal
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

# Read-only HMP commands the monitor panel may run (no writes to host files,
# no state changes; those have their own buttons).
MONITOR_ALLOW = re.compile(r"^info (mtree( -f)?|qtree|roms|registers|pic|irq|"
                           r"status|cpus|chardev|version|qom-tree)$")
CONSOLE_KEEP = 256 * 1024   # bytes of console transcript kept for replay
LOG_KEEP = 5000             # lines of the -d log kept in memory

INVALID = re.compile(r"Invalid (read|write) at addr 0x([0-9A-Fa-f]+), size (\d+)")
UNIMP = re.compile(r"^(\w+): unimplemented (read|write) at offset 0x([0-9A-Fa-f]+)")


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
        profiles[path.stem] = p
    return profiles


def resolve_qemu(spec):
    env = os.environ.get("BENCH_QEMU")
    if env:
        return env
    if "/" in spec:
        return str(ROOT / spec)
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
        while True:
            line = await self.reader.readline()
            if not line:
                break
            msg = json.loads(line)
            if "event" in msg:
                await self.on_event(msg)
            elif msg.get("id") in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
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
        msg = await asyncio.wait_for(fut, timeout)
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

    def __init__(self, bench, profile_id, profile):
        self.bench = bench
        self.profile_id = profile_id
        self.profile = profile
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = RUNS / f"{stamp}-{profile_id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
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
        self.console = bytearray()
        self.log_lines = collections.deque(maxlen=LOG_KEEP)
        self.tasks = []

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
        return argv

    async def start(self, paused):
        try:
            await self._prepare()
            self.argv = self.build_argv()
            (self.run_dir / "cmdline.txt").write_text(" ".join(self.argv) + "\n")
            await self._emit("stderr", "$ " + " ".join(self.argv) + "\n")
            self.proc = await asyncio.create_subprocess_exec(
                *self.argv, cwd=ROOT, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                start_new_session=True)
            self.tasks.append(asyncio.create_task(self._pump_stderr()))
            self.tasks.append(asyncio.create_task(self._watch_exit()))
            await self.qmp.connect(str(self.sock_dir / "qmp.sock"),
                                   lambda: self.proc.returncode is None)
            reader, self.con_writer = await asyncio.open_unix_connection(
                str(self.sock_dir / "con.sock"))
            self.tasks.append(asyncio.create_task(self._pump_console(reader)))
            if self.profile["semihosting"]:
                semi, _ = await asyncio.open_unix_connection(
                    str(self.sock_dir / "semi.sock"))
                self.tasks.append(asyncio.create_task(self._pump_console(semi)))
            self.tasks.append(asyncio.create_task(self._tail_log()))
            if paused:
                await self._set_state("paused")
            else:
                await self.qmp.cmd("cont")
                await self._set_state("running")
        except Exception as e:  # noqa: BLE001 - reported to the UI
            self.error = str(e) or type(e).__name__
            await self._emit("stderr", f"bench: start failed: {self.error}\n")
            await self.kill()
            await self._set_state("exited")

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
        await asyncio.sleep(0.2)            # let the last console bytes arrive
        self.qmp.close()
        await self._set_state("exited")
        for t in self.tasks:
            if t is not asyncio.current_task() and not t.done():
                t.cancel()
        shutil.rmtree(self.sock_dir, ignore_errors=True)

    # -- streams -----------------------------------------------------------

    async def _pump_stderr(self):
        with (self.run_dir / "stderr.log").open("ab") as f:
            while line := await self.proc.stdout.readline():
                f.write(line)
                f.flush()
                await self._emit("stderr", line.decode(errors="replace"))

    async def _pump_console(self, reader):
        with (self.run_dir / "console.log").open("ab") as f:
            while data := await reader.read(4096):
                f.write(data)
                f.flush()
                self.console += data
                if len(self.console) > CONSOLE_KEEP:
                    del self.console[:len(self.console) - CONSOLE_KEEP]
                await self._emit("con", data.decode(errors="replace"))

    async def _tail_log(self):
        pos = 0
        while True:
            if self.log_path.exists():
                with self.log_path.open("r", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    self.log_lines.append(line)
                    await self._emit("log", line)
            if self.state == "exited":
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
        """What the guest touched that the model does not provide."""
        rows = collections.Counter()
        for line in self.log_lines:
            if m := INVALID.search(line):
                rows[("invalid_mem", m[1], f"0x{int(m[2], 16):08x}", m[3])] += 1
            elif m := UNIMP.search(line):
                rows[("unimp", m[2], f"{m[1]}+0x{int(m[3], 16):x}", "")] += 1
        return [{"kind": k, "access": a, "where": w, "size": s, "count": n}
                for (k, a, w, s), n in rows.most_common()]

    def status(self):
        return {"state": self.state, "profile": self.profile_id,
                "name": self.profile["name"],
                "pid": self.proc.pid if self.proc else None,
                "exit_code": self.exit_code, "error": self.error,
                "uptime": round(time.time() - self.started, 1),
                "run_dir": str(self.run_dir.relative_to(ROOT)),
                "cmdline": " ".join(self.argv)}

    async def _set_state(self, state):
        if self.state != state:
            self.state = state
            await self.bench.broadcast({"t": "status", "d": self.status()})

    async def _emit(self, kind, data):
        await self.bench.broadcast({"t": kind, "d": data})


class Bench:
    def __init__(self):
        self.profiles = load_profiles()
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


def json_error(status, msg):
    return web.json_response({"error": msg}, status=status)


def make_app():
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
        bench.session = Session(bench, pid, bench.profiles[pid])
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
                                  "coverage": s.coverage()})

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

    app = web.Application()
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
    web.run_app(make_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
