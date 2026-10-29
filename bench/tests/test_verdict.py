# SPDX-License-Identifier: GPL-2.0-or-later
"""Verdict rules: markers come from the console stream only, may straddle
reads, and combine with expect_exit as documented in bench/README.md."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class FakeBench:
    async def broadcast(self, msg):
        pass


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(server, "RUNS", tmp_path / "build" / "bench")

    made = []

    def make(expect, expect_exit=None):
        made.append(None)                       # run dirs need unique names
        profile = {"name": "t", "qemu": "q", "args": [], "prepare": [],
                   "semihosting": False, "log": "", "expect": expect,
                   "expect_exit": expect_exit, "description": ""}
        return server.Session(FakeBench(), f"t{len(made)}", profile)
    return make


def feed(*chunks):
    r = asyncio.StreamReader()
    for c in chunks:
        r.feed_data(c)
    r.feed_eof()
    return r


async def trickle(reader, chunks):
    """Feed one chunk per read, as a socket would deliver them."""
    for c in chunks:
        await asyncio.sleep(0.01)
        reader.feed_data(c)
    reader.feed_eof()


def test_marker_split_across_reads(session):
    s = session(["RESULT: PASS"])

    async def run():
        r = asyncio.StreamReader()
        t = asyncio.create_task(trickle(r, [b"xx RESULT", b": PA", b"SS\n"]))
        await s._pump_console_inner(r)
        await t
    asyncio.run(run())
    assert s.found == {"RESULT: PASS"}


def test_stderr_is_not_the_console(session):
    s = session(["RESULT: PASS"])

    class Proc:
        stdout = None
    s.proc = Proc()

    async def run():
        s.proc.stdout = feed(b"RESULT: PASS\n")
        await s._pump_stderr_inner()
    asyncio.run(run())
    assert s.found == set()


def test_verdict_rules(session):
    s = session(["hello"])                      # no expect_exit
    s.state = "running"
    assert s.verdict() == ("running", [])
    s.found.add("hello")
    assert s.verdict() == ("pass", [])          # pass while still running

    s = session(["hello"], 0)
    s.state = "running"
    s.found.add("hello")
    assert s.verdict() == ("running", [])       # exit still pending
    s.state, s.exit_code = "exited", 0
    assert s.verdict() == ("pass", [])
    s.exit_code = 1
    assert s.verdict() == ("fail", ["exit 1, expected 0"])
    s.exit_code, s.stopped = 0, True
    assert s.verdict()[0] == "fail"             # QMP quit exits 0 too

    s = session(["hello"])
    s.state = "exited"
    assert s.verdict() == ("fail", ["missing on the console: 'hello'"])

    assert session([]).verdict() == (None, [])  # no expectations, no verdict


def test_past_run_log_has_no_phantom_line(tmp_path):
    log = tmp_path / "qemu.log"
    log.write_text("Invalid read at addr 0x10000000, size 4, region '(null)', "
                   "reason: rejected\n"
                   "rzg2l_sysc_read: unimplemented read at offset 0x0\n")
    cov = server.count_log(log)
    assert sum(cov.values()) == 2
    assert not any(k[0] == "other" for k in cov)


def test_unfinished_run_is_listed_as_lost(tmp_path, monkeypatch):
    """run.json left at "starting" by a bench that died: not shown as live."""
    monkeypatch.setattr(server, "RUNS", tmp_path)
    run = tmp_path / "20261029-000000-000-virt-echo"
    run.mkdir()
    (run / "run.json").write_text('{"state": "starting", "verdict": "running"}')

    class NoSession:
        session = None
    info = server.Bench.run_info(NoSession(), run)
    assert info["state"] == "lost" and info["verdict"] is None


def test_reset_restarts_the_verdict(session):
    """A marker seen before a QMP RESET is forgotten; no expect_exit here,
    so it would otherwise stay PASS while the guest runs on."""
    s = session(["hello"])
    s.state = "running"

    async def run():
        r = asyncio.StreamReader()
        pump = asyncio.create_task(s._pump_console_inner(r))
        r.feed_data(b"hel")
        await asyncio.sleep(0.01)
        r.feed_data(b"lo\n")
        await asyncio.sleep(0.01)
        assert s.verdict() == ("pass", [])
        await s._on_qmp_event({"event": "RESET"})
        assert s.verdict() == ("running", [])
        r.feed_data(b"hel")               # half a marker before the reset ...
        await asyncio.sleep(0.01)
        await s._on_qmp_event({"event": "RESET"})
        r.feed_data(b"lo\n")              # ... never joins one after it
        r.feed_eof()
        await pump
    asyncio.run(run())
    assert s.verdict() == ("running", [])
    s.state = "exited"
    assert s.verdict()[0] == "fail"


def test_crlf_only_for_lone_newlines():
    assert server.crlf(b"a\nb\n") == (b"a\r\nb\r\n", False)
    assert server.crlf(b"a\r\nb") == (b"a\r\nb", False)
    assert server.crlf(b"x\r") == (b"x\r", True)
    assert server.crlf(b"\ny", after_cr=True) == (b"\ny", False)   # \r|\n split
    assert server.crlf(b"\ny") == (b"\r\ny", False)


def test_semihosting_stream_only_is_normalised(session):
    async def run(s, semihosting):
        r = asyncio.StreamReader()
        t = asyncio.create_task(trickle(r, [b"one\ntwo\r", b"\nthree\n"]))
        await s._pump_console_inner(r, semihosting)
        await t
    serial, semi = session([]), session([])
    asyncio.run(run(serial, False))
    asyncio.run(run(semi, True))
    assert bytes(serial.console) == b"one\ntwo\r\nthree\n"      # byte-exact
    assert bytes(semi.console) == b"one\r\ntwo\r\nthree\r\n"
