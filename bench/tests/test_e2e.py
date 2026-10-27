# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end test of the bench through its web UI, on stock QEMU virt.

    python3 -m pytest bench/tests/test_e2e.py

Needs: qemu-system-aarch64, an aarch64-linux-gnu toolchain, aiohttp, and
Playwright with Chromium (python3 -m playwright install chromium).
"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOT = ROOT / "build" / "bench" / "e2e.png"


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

        # Keys typed into the terminal reach the guest UART and echo back
        page.get_by_test_id("console").click()
        page.keyboard.type("hi")
        expect(console).to_contain_text("hi")

        # A read of a hole shows up in the coverage list
        page.keyboard.type("u")
        expect(console).to_contain_text("read hole")
        page.get_by_test_id("tab-coverage").click()
        row = page.get_by_test_id("coverage-row").first
        expect(row).to_contain_text("0x0c000000")
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
        browser.close()


def test_start_failure_is_reported(server):
    """A profile whose QEMU binary is missing fails visibly, not silently."""
    req = urllib.request.Request(
        server + "/api/session", method="POST",
        data=b'{"profile": "rzv2l-smarc-m1-probe"}',
        headers={"content-type": "application/json"})
    qemu = ROOT / "build" / "qemu" / "qemu-system-aarch64"
    if qemu.exists():
        pytest.skip("the project QEMU is built here; nothing to fail")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=120)
    assert err.value.code == 500
