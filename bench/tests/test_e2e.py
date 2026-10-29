# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end test of the bench through its web UI, on stock QEMU virt.

    python3 -m pytest bench/tests/test_e2e.py

Needs: qemu-system-aarch64, an aarch64-linux-gnu toolchain, aiohttp, and
Playwright with Chromium (python3 -m playwright install chromium).
"""

import csv
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as server_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHOT = ROOT / "build" / "bench" / "e2e.png"
# The project QEMU: BENCH_QEMU (the server uses it for every profile) or the
# build in this tree
PROJECT_QEMU = Path(os.environ.get("BENCH_QEMU")
                    or ROOT / "build" / "qemu" / "qemu-system-aarch64")
JSON_H = {"content-type": "application/json"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "bench/server.py", "--port", str(port)],
                            cwd=ROOT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/api/profiles", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(10)


def test_echo_session(server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(server)

        console = page.get_by_test_id("console-text")
        status = page.get_by_test_id("status")

        page.get_by_test_id("profile-select").select_option("virt-echo")
        page.get_by_test_id("btn-start").click()
        expect(status).to_have_attribute("data-state", "running", timeout=60_000)
        expect(console).to_contain_text("echo ready")
        # Markers seen so far, but expect_exit = 0 still pending
        verdict = page.get_by_test_id("verdict")
        expect(verdict).to_have_attribute("data-verdict", "running")

        # Keys typed into the terminal reach the guest UART and echo back
        page.get_by_test_id("console").click()
        page.keyboard.type("hi")
        expect(console).to_contain_text("hi")

        # A read of a hole shows up in the coverage list
        page.keyboard.type("u")
        expect(console).to_contain_text("read hole")
        page.get_by_test_id("tab-coverage").click()
        # (QEMU 11 also logs PL011 guest_errors for this program: other rows)
        row = page.get_by_test_id("coverage-row").filter(has_text="0x0c000000")
        expect(row).to_contain_text("invalid_mem")
        expect(row).to_contain_text("read")

        # Monitor: allowed read-only command works, anything else is refused
        page.get_by_test_id("tab-monitor").click()
        page.get_by_test_id("monitor-qtree").click()
        expect(page.get_by_test_id("monitor-output")).to_contain_text("pl011")
        page.get_by_test_id("monitor-input").fill("quit")
        page.get_by_test_id("monitor-run").click()
        expect(page.get_by_test_id("monitor-output")).to_contain_text("not an allowed")
        expect(status).to_have_attribute("data-state", "running")

        # Pause and resume over QMP
        page.get_by_test_id("btn-pause").click()
        expect(status).to_have_attribute("data-state", "paused")
        page.get_by_test_id("btn-pause").click()
        expect(status).to_have_attribute("data-state", "running")

        # Reset reloads the program: the banner appears a second time
        page.get_by_test_id("btn-reset").click()
        expect(console).to_contain_text("ready", timeout=10_000)
        page.wait_for_function(
            "document.querySelector('[data-testid=console-text]')"
            ".textContent.split('echo ready').length === 3")

        page.get_by_test_id("tab-log").click()
        SHOT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOT))

        # 'q' exits through semihosting with status 0
        page.get_by_test_id("console").click()
        page.keyboard.type("q")
        expect(status).to_have_attribute("data-state", "exited")
        expect(page.get_by_test_id("exit-code")).to_have_attribute("data-code", "0")
        expect(console).to_contain_text("bye")
        expect(verdict).to_have_attribute("data-verdict", "pass")
        expect(verdict).to_have_text("PASS")
        run = get_json(server, "/api/session")["run"]

        # The run is listed in the Runs tab and its files can be opened
        page.get_by_test_id("tab-runs").click()
        row = page.locator(f'[data-testid=run-row][data-run="{run}"]')
        expect(row).to_contain_text("virt-echo")
        expect(row.locator("td").nth(2)).to_have_text("0")
        expect(row.locator("td").nth(3)).to_have_text("PASS")
        row.click()
        out = page.get_by_test_id("run-output")
        expect(out).to_contain_text("echo ready")
        expect(out).to_contain_text("bye")
        page.get_by_test_id("run-log").click()
        expect(out).to_have_attribute("data-file", "log")
        expect(out).to_contain_text("Invalid read at addr 0xC000000")

        # Coverage CSV: the virt hole is in no device-map window
        with page.expect_download() as dl:
            page.get_by_test_id("run-coverage-csv").click()
        rows = list(csv.reader(io.StringIO(Path(dl.value.path()).read_text())))
        assert rows[0] == ["name", "base", "size", "kind", "access", "count"]
        assert ["unmapped", "0x0c000000", "4", "invalid_mem", "read", "1"] in rows
        browser.close()


def get_json(url, path):
    with urllib.request.urlopen(url + path, timeout=10) as r:
        return json.load(r)


def wait_state(url, want, tries=200):
    for _ in range(tries):
        st = get_json(url, "/api/session")
        if st["state"] == want:
            return st
        time.sleep(0.1)
    raise AssertionError(f"state {st['state']!r}, wanted {want!r}")


def test_stop_before_exit_fails(server):
    """A run the bench stopped never met expect_exit: FAIL, with the reason."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    assert post(server, "/api/session", b'{"profile": "virt-echo"}', JSON_H) == 200
    for _ in range(100):
        if "echo ready" in get_json(server, "/api/session/console")["text"]:
            break
        time.sleep(0.1)
    st = get_json(server, "/api/session")
    assert st["verdict"] == "running" and st["expect_missing"] == ["bye"]
    post(server, "/api/session/stop", b"{}", JSON_H)
    st = wait_state(server, "exited")
    assert st["verdict"] == "fail"
    assert "missing on the console: 'bye'" in st["verdict_reasons"]
    assert "stopped by the bench before the guest exited" in st["verdict_reasons"]
    meta = get_json(server, f"/api/runs/{st['run']}")
    assert meta["verdict"] == "fail" and meta["profile"] == "virt-echo"


def test_gdbstub_option(server):
    """Start with gdbstub: paused, a loopback port in the UI, a stub that answers."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(server)
        page.get_by_test_id("profile-select").select_option("virt-echo")
        page.get_by_test_id("gdb-option").check()
        page.get_by_test_id("btn-start").click()
        status = page.get_by_test_id("status")
        expect(status).to_have_attribute("data-state", "paused", timeout=60_000)
        info = page.get_by_test_id("gdb-info")
        expect(info).to_be_visible()
        port = int(info.get_attribute("data-port"))
        expect(info).to_contain_text(f"127.0.0.1:{port}")
        assert f"-gdb tcp:127.0.0.1:{port}" in get_json(server, "/api/session")["cmdline"]

        # GDB remote protocol: '?' asks why the target stopped
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"+$?#3f")
            reply = b""
            while not re.search(rb"\$[TS][0-9a-fA-F]{2}", reply):
                chunk = s.recv(4096)
                assert chunk, f"stub closed; got {reply!r}"
                reply += chunk
        expect(status).to_have_attribute("data-state", "paused")
        page.get_by_test_id("btn-stop").click()
        expect(status).to_have_attribute("data-state", "exited")
        expect(info).to_be_hidden()
        browser.close()


def test_run_paths_are_confined(server):
    # Encoded dots reach the handler as a run id of "..": build/ exists
    for bad in ("%2E%2E", "%2E", "nope"):
        for tail in ("", "/cmdline"):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(f"{server}/api/runs/{bad}{tail}", timeout=5)
            assert err.value.code == 404, bad + tail
            assert get_err(err.value) == "no such run", bad + tail


def get_err(e):
    return json.loads(e.read() or b"{}").get("error")


def test_start_failure_is_reported(server):
    """A profile whose QEMU binary is missing fails visibly, not silently."""
    req = urllib.request.Request(
        server + "/api/session", method="POST",
        data=b'{"profile": "rzv2l-smarc-m1-probe"}',
        headers={"content-type": "application/json"})
    if PROJECT_QEMU.exists():
        pytest.skip("the project QEMU is available; nothing to fail")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=120)
    assert err.value.code == 500


def post(url, path, body, headers=None):
    req = urllib.request.Request(url + path, data=body, method="POST",
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_cross_site_requests_are_refused(server):
    # A foreign page can send these without a CORS preflight; all must fail.
    json_h = {"content-type": "application/json"}
    assert post(server, "/api/session/stop", b"{}",
                {**json_h, "Origin": "http://evil.example"}) == 403
    assert post(server, "/api/session/stop", b"{}",
                {"content-type": "text/plain"}) == 415
    assert post(server, "/api/session/stop", b"{}",
                {**json_h, "Host": "rebound.example:80"}) == 403
    assert post(server, "/api/session/stop", b"{}", json_h) == 200


@pytest.mark.skipif(not PROJECT_QEMU.exists(),
                    reason="needs the project QEMU (BENCH_QEMU or build/qemu)")
def test_m1_probe_through_the_bench(server):
    # Semihosting output and the -d log of a sub-second run must all arrive.
    json_h = JSON_H
    post(server, "/api/session/stop", b"{}", json_h)
    assert post(server, "/api/session", b'{"profile": "rzv2l-smarc-m1-probe"}',
                {"content-type": "application/json"}) == 200
    for _ in range(100):
        st = json.load(urllib.request.urlopen(server + "/api/session"))
        if st["state"] == "exited":
            break
        time.sleep(0.1)
    assert st["exit_code"] == 0
    con = json.load(urllib.request.urlopen(server + "/api/session/console"))
    assert "RESULT: PASS" in con["text"]
    log = json.load(urllib.request.urlopen(server + "/api/session/log"))
    on_disk = (ROOT / st["run_dir"] / "qemu.log").read_text().splitlines()
    assert on_disk and log["lines_total"] == len(on_disk)
    assert sum(r["count"] for r in log["coverage"]) == len(on_disk)
    # A past run's coverage is re-read from disk: same rows as the live one
    disk = server_mod.coverage_rows(
        server_mod.count_log(ROOT / st["run_dir"] / "qemu.log"))
    assert sorted(map(str, disk)) == sorted(map(str, log["coverage"]))
    # The verdict comes from the probe's console line and its exit status
    assert st["verdict"] == "pass", st["verdict_reasons"]
    meta = json.loads((ROOT / st["run_dir"] / "run.json").read_text())
    assert meta["verdict"] == "pass" and meta["exit_code"] == 0
