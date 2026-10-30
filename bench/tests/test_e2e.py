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
                            cwd=ROOT, env={**os.environ, "BENCH_RUN_ORIGIN": "test"})
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
        expect(page.get_by_test_id("console-hint")).to_contain_text("waiting for 'read hole'")

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

        page.wait_for_function(ROWS_JS + ".some((r) => r.includes('reset: the verdict counts from here'))")
        expect(console).not_to_contain_text("reset:")          # display only
        # Markers count from the last reset: print 'read hole' again
        page.get_by_test_id("console").click()
        page.keyboard.type("u")
        page.wait_for_function(
            "document.querySelector('[data-testid=console-text]')"
            ".textContent.split('read hole').length === 3")

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
        # Another profile picked: the readout says it shows the last run
        page.get_by_test_id("profile-select").select_option("rzv2l-smarc-m1-probe")
        expect(page.get_by_test_id("last-run")).to_be_visible()
        expect(page.get_by_test_id("last-run")).to_have_text("last run: virt-echo")
        page.get_by_test_id("profile-select").select_option("virt-echo")
        expect(page.get_by_test_id("last-run")).to_be_hidden()

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
        assert ["unmapped", "0x0c000000", "4", "invalid_mem", "read", "2"] in rows  # u twice
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
    assert st["verdict"] == "running"
    assert st["expect_missing"] == ["read hole", "bye"]
    post(server, "/api/session/stop", b"{}", JSON_H)
    st = get_json(server, "/api/session")       # Stop returns once recorded
    assert st["state"] == "exited"
    assert st["verdict"] == "fail"
    assert "missing on the console: 'bye'" in st["verdict_reasons"]
    assert "stopped by the bench before the guest exited" in st["verdict_reasons"]
    meta = get_json(server, f"/api/runs/{st['run']}")
    assert meta["verdict"] == "fail" and meta["profile"] == "virt-echo"


def test_marker_before_reset_does_not_count(server):
    """'read hole' appears before a Reset and not after: never PASS."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    assert post(server, "/api/session", b'{"profile": "virt-echo"}', JSON_H) == 200

    def console():
        return get_json(server, "/api/session/console")["text"]

    def wait_for(pred):
        for _ in range(100):
            if pred():
                return
            time.sleep(0.1)
        raise AssertionError(f"timed out; console {console()!r}")

    wait_for(lambda: "echo ready" in console())
    post(server, "/api/session/console", b'{"data": "u"}', JSON_H)
    wait_for(lambda: "read hole" in console())
    assert get_json(server, "/api/session")["expect_missing"] == ["bye"]

    post(server, "/api/session/reset", b"{}", JSON_H)
    wait_for(lambda: console().count("echo ready") == 2)
    st = get_json(server, "/api/session")
    assert st["verdict"] == "running"
    assert st["expect_missing"] == ["read hole", "bye"]

    # Every marker has now appeared in the run, but not since the reset
    post(server, "/api/session/console", b'{"data": "q"}', JSON_H)
    st = wait_state(server, "exited")
    assert st["exit_code"] == 0 and "bye" in console()
    assert st["verdict"] == "fail"
    assert st["verdict_reasons"] == ["missing since the last reset: 'read hole'"]


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


# ---- UX: theme toggle and console settings -----------------------------------

ROWS_JS = """[...document.querySelectorAll('#term .xterm-rows > div')]
    .map((r) => r.textContent.trimEnd()).filter((r) => r)"""

LIGHT_BG, DARK_BG = "rgb(241, 238, 230)", "rgb(11, 18, 16)"         # --bg
LIGHT_TERM, DARK_TERM = "rgb(248, 245, 238)", "rgb(7, 12, 10)"       # --term-bg


def colours(page):
    return page.evaluate("""() => [
        getComputedStyle(document.body).backgroundColor,
        getComputedStyle(document.querySelector('#term .xterm-viewport')).backgroundColor]""")


def test_theme_toggle(server):
    """System / Light / Dark: remembered per browser; the terminal follows."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(color_scheme="light")
        page = ctx.new_page()
        page.goto(server)
        expect(page.get_by_test_id("theme-system")).to_have_attribute("aria-checked", "true")
        assert colours(page) == [LIGHT_BG, LIGHT_TERM]

        page.get_by_test_id("theme-dark").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert colours(page) == [DARK_BG, DARK_TERM]
        page.reload()                                   # remembered
        expect(page.get_by_test_id("theme-dark")).to_have_attribute("aria-checked", "true")
        assert colours(page) == [DARK_BG, DARK_TERM]

        # System follows the OS scheme, live, terminal included
        page.get_by_test_id("theme-system").click()
        assert colours(page) == [LIGHT_BG, LIGHT_TERM]
        page.emulate_media(color_scheme="dark")
        page.wait_for_function(
            "getComputedStyle(document.querySelector('#term .xterm-viewport'))"
            f".backgroundColor === '{DARK_TERM}'")
        assert colours(page) == [DARK_BG, DARK_TERM]
        page.reload()
        expect(page.get_by_test_id("theme-system")).to_have_attribute("aria-checked", "true")
        ctx.close()

        # Without usable storage the page still works and the toggle applies
        ctx = browser.new_context(color_scheme="light")
        ctx.add_init_script("""Object.defineProperty(window, 'localStorage',
            { get() { throw new DOMException('denied', 'SecurityError'); } });""")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(server)
        expect(page.get_by_test_id("profile-select")).to_contain_text("virt")
        page.get_by_test_id("theme-dark").click()
        assert colours(page) == [DARK_BG, DARK_TERM]
        assert errors == []
        browser.close()


@pytest.mark.skipif(not PROJECT_QEMU.exists(),
                    reason="needs the project QEMU (BENCH_QEMU or build/qemu)")
def test_profile_display_map_draws_lf_as_crlf(server):
    """The M1 probe prints through semihosting with bare LF. Its profile maps
    LF to CRLF for display: lines start at column 0, the transcript stays raw."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(server)
        page.get_by_test_id("profile-select").select_option("rzv2l-smarc-m1-probe")
        expect(page.get_by_test_id("console-lf-crlf")).to_be_checked()
        page.get_by_test_id("btn-start").click()
        expect(page.get_by_test_id("status")).to_have_attribute(
            "data-state", "exited", timeout=60_000)
        expect(page.get_by_test_id("console-text")).to_contain_text("RESULT: PASS")
        page.wait_for_function(ROWS_JS + ".some((r) => r.includes('RESULT: PASS'))")
        rows = page.evaluate(ROWS_JS)
        shown = page.get_by_test_id("console-text").text_content()
        browser.close()
    # The page's transcript keeps the bare LF as well: only the drawing maps it
    assert re.search(r"(?<!\r)\n", shown), "page transcript must stay raw"
    assert any(r.startswith("RESULT: PASS") for r in rows), rows
    assert all(r == r.lstrip() for r in rows), rows           # no staircase
    text = get_json(server, "/api/session/console")["text"]
    assert re.search(r"(?<!\r)\n", text), "transcript must keep the bare LF"


def echo_page(pw, server):
    """virt-echo running in a fresh page; returns (browser, page)."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 860})
    page.goto(server)
    page.get_by_test_id("profile-select").select_option("virt-echo")
    page.get_by_test_id("btn-start").click()
    expect(page.get_by_test_id("console-text")).to_contain_text(
        "echo ready", timeout=60_000)
    return browser, page


def wait_rows_end(page, text):
    page.wait_for_function(ROWS_JS + f".slice(-1)[0]?.endsWith({text!r})")
    return page.evaluate(ROWS_JS)


def test_display_map_toggle(server):
    """Raw by default (a bare LF steps right); the menu maps it for display."""
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        expect(page.get_by_test_id("console-lf-crlf")).not_to_be_checked()
        post(server, "/api/session/console", b'{"data": "1\\n2"}', JSON_H)
        wait_rows_end(page, "2")
        page.get_by_test_id("console-settings").locator("summary").click()
        page.get_by_test_id("console-lf-crlf").check()
        post(server, "/api/session/console", b'{"data": "\\r3\\n4"}', JSON_H)
        rows = wait_rows_end(page, "4")
        page.get_by_test_id("btn-stop").click()
        browser.close()
    assert rows[-4:] == ["1", " 2", "3", "4"], rows
    text = get_json(server, "/api/session/console")["text"]
    assert text.endswith("1\n2\r\n3\n4"), repr(text[-20:])  # raw bytes


@pytest.mark.parametrize("choice,sent", [("cr", "a\r\n"), ("lf", "a\n"),
                                         ("crlf", "a\r\n\n")])
def test_enter_sends(server, choice, sent):
    """Enter sends CR, LF or CRLF; virt-echo answers CR with CRLF and echoes
    LF as is, so the raw transcript shows what went out."""
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        expect(page.get_by_test_id("console-enter")).to_have_value("cr")
        page.get_by_test_id("console-settings").locator("summary").click()
        page.get_by_test_id("console-enter").select_option(choice)
        page.get_by_test_id("console").click()
        page.keyboard.type("a")
        page.keyboard.press("Enter")
        page.keyboard.type("z")
        expect(page.get_by_test_id("console-text")).to_contain_text("z")
        page.get_by_test_id("btn-stop").click()
        browser.close()
    text = get_json(server, "/api/session/console")["text"]
    assert text.endswith(sent + "z"), repr(text[-12:])


def test_serial_output_stays_byte_exact(server):
    """virt-echo echoes a raw LF byte as a bare \\n on the PL011: it must arrive as is."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    assert post(server, "/api/session", b'{"profile": "virt-echo"}', JSON_H) == 200
    for _ in range(100):
        if "echo ready" in get_json(server, "/api/session/console")["text"]:
            break
        time.sleep(0.1)
    post(server, "/api/session/console", b'{"data": "a\\nb"}', JSON_H)
    for _ in range(50):
        text = get_json(server, "/api/session/console")["text"]
        if text.endswith("b"):
            break
        time.sleep(0.1)
    post(server, "/api/session/stop", b"{}", JSON_H)
    assert text.endswith("echo ready\r\na\nb"), repr(text[-40:])


def test_shutdown_records_the_running_session():
    """Stopping the bench while a session runs still finishes its run.json."""
    port = free_port()
    proc = subprocess.Popen([sys.executable, "bench/server.py", "--port", str(port)],
                            cwd=ROOT, env={**os.environ, "BENCH_RUN_ORIGIN": "test"})
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "/api/profiles", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        assert post(url, "/api/session", b'{"profile": "virt-echo"}', JSON_H) == 200
        run_dir = ROOT / get_json(url, "/api/session")["run_dir"]
    finally:
        proc.terminate()                    # SIGTERM: aiohttp's graceful shutdown
        proc.wait(20)
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["state"] == "exited", meta["state"]


def test_echo_terminal_keys(server):
    """Typing in the terminal: Enter starts a new line at column 0 and
    Backspace erases, as on a serial console with a line discipline."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.goto(server)
        page.get_by_test_id("profile-select").select_option("virt-echo")
        page.get_by_test_id("btn-start").click()
        console = page.get_by_test_id("console-text")
        expect(console).to_contain_text("echo ready", timeout=60_000)
        page.get_by_test_id("console").click()
        page.keyboard.type("abx")
        page.keyboard.press("Backspace")
        page.keyboard.press("Enter")
        page.keyboard.type("de")
        page.keyboard.press("Enter")
        page.keyboard.type("f")
        rows_js = """() => [...document.querySelectorAll('#term .xterm-rows > div')]
            .map((r) => r.textContent.trimEnd()).filter((r) => r)"""
        # xterm draws on the next frames: wait until the last key is on screen
        page.wait_for_function(f"({rows_js})().slice(-1)[0]?.endsWith('f')")
        rows = page.evaluate(rows_js)
        page.get_by_test_id("btn-stop").click()
        browser.close()
    printed = [r for r in rows if r]
    assert printed[-3:] == ["ab", "de", "f"], printed


# ---- introspection: Map, Devices, readiness ------------------------------------

def test_map_lists_unlisted_regions_and_assets(server):
    """virt is not the RZ/V2L, and the Map says so: its PCIe window lies over
    the RZ/V2L peripheral addresses, its 128 MiB of RAM covers part of the
    DDR window, and its own devices (pl011...) are in no device-map window."""
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        expect(page.get_by_test_id("assets")).to_have_attribute("data-status", "ready")
        expect(page.get_by_test_id("machine")).to_have_text("virt")
        page.get_by_test_id("tab-map").click()
        scif0 = page.locator('[data-testid=map-row][data-base="0x1004b800"]')
        expect(scif0).to_contain_text("gpex_mmio_window")
        expect(scif0).to_have_attribute("data-status", "covered")
        expect(page.get_by_test_id("map-extra-row").filter(
            has_text="gpex_mmio_window").first).to_be_visible()
        ddr = page.locator('[data-testid=map-row][data-base="0x40000000"]')
        expect(ddr).to_have_attribute("data-status", "ram")
        expect(ddr.locator(".st")).to_have_attribute("data-partial", "true")
        expect(page.get_by_test_id("map-extra-row").filter(has_text="pl011")).to_have_count(1)
        page.get_by_test_id("map-filter-live").click()
        expect(page.get_by_test_id("map-extra")).to_be_hidden()   # filters hide extras
        page.get_by_test_id("btn-stop").click()
        browser.close()


@pytest.mark.skipif(not PROJECT_QEMU.exists(),
                    reason="needs the project QEMU (BENCH_QEMU or build/qemu)")
def test_map_and_devices_on_rzv2l(server):
    """The M1 probe: SYSC modelled; its deliberate read of 0x10000000 is the
    one hit, on a missing window; the device tree shows SYSC's DEVID."""
    post(server, "/api/session/stop", b"{}", JSON_H)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 860})
        page.goto(server)
        page.get_by_test_id("profile-select").select_option("rzv2l-smarc-m1-probe")
        page.get_by_test_id("btn-start").click()
        expect(page.get_by_test_id("status")).to_have_attribute(
            "data-state", "exited", timeout=60_000)
        page.get_by_test_id("tab-map").click()
        sysc = page.locator('[data-testid=map-row][data-base="0x11020000"]')
        expect(sysc).to_have_attribute("data-status", "modelled")
        expect(sysc).to_contain_text("renesas-rzg2l-sysc")
        page.get_by_test_id("map-filter-hits").click()
        hit = page.get_by_test_id("map-row")
        expect(hit).to_have_count(1)
        expect(hit).to_have_attribute("data-base", "0x10000000")
        expect(hit).to_have_attribute("data-status", "missing")
        expect(hit).to_have_attribute("data-hits", "1")
        expect(page.get_by_test_id("map-unplaced-row")).to_contain_text("rzg2l_sysc_read+0x0")

        page.get_by_test_id("tab-devices").click()
        page.get_by_test_id("devices-filter").fill("lsi-devid")
        nodes = page.get_by_test_id("device-node")
        expect(nodes).to_have_count(1)
        expect(nodes).to_contain_text("renesas-rzg2l-sysc")
        expect(nodes).to_contain_text("0x18447447")
        page.get_by_test_id("devices-filter").fill("no-such-thing")
        expect(page.get_by_test_id("devices-empty")).to_contain_text("Nothing matches")
        browser.close()


def test_page_is_revalidated(server):
    """The page and its scripts carry no-cache: a changed bench is never
    hidden behind a browser's stored copy."""
    for path in ("/", "/static/app.js", "/static/style.css"):
        with urllib.request.urlopen(server + path, timeout=5) as r:
            assert r.headers.get("Cache-Control") == "no-cache", path


def test_console_hint_says_where_keys_go(server):
    """Above the terminal: what happens to typing in each state."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        post(server, "/api/session/stop", b"{}", JSON_H)
        page.goto(server)
        hint = page.get_by_test_id("console-hint")
        page.get_by_test_id("profile-select").select_option("virt-echo")
        page.get_by_test_id("btn-start-paused").click()
        expect(hint).to_have_attribute("data-state", "paused", timeout=60_000)
        expect(hint).to_contain_text("on Resume")
        page.get_by_test_id("btn-pause").click()             # Resume
        expect(hint).to_have_attribute("data-state", "running")
        expect(hint).to_contain_text("click to type")
        page.get_by_test_id("btn-stop").click()
        expect(hint).to_have_attribute("data-state", "exited")
        expect(hint).to_contain_text("keys go nowhere")
        page.get_by_test_id("console").click()
        page.keyboard.type("x")                              # typed into nothing
        expect(hint).to_have_class(re.compile(r"\bnudge\b"))
        browser.close()



def test_keyboard_leaves_the_terminal_and_walks_the_tabs(server):
    """Ctrl+] hands focus from the terminal to the tab row; arrows move along it."""
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        page.get_by_test_id("console").click()
        page.keyboard.press("Tab")                        # goes to the guest
        page.keyboard.press("Control+BracketRight")
        focused = lambda: page.evaluate(
            "document.activeElement.getAttribute('data-testid')")
        assert focused() == "tab-log"
        page.keyboard.press("ArrowRight")
        assert focused() == "tab-coverage"
        expect(page.get_by_test_id("tab-coverage")).to_have_attribute("aria-selected", "true")
        page.keyboard.press("End")
        assert focused() == "tab-runs"
        page.get_by_test_id("btn-stop").click()
        browser.close()


def test_console_settings_are_kept_per_profile(server):
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        page.get_by_test_id("console-settings").locator("summary").click()
        page.get_by_test_id("console-enter").select_option("lf")
        page.get_by_test_id("btn-stop").click()
        page.reload()
        page.get_by_test_id("profile-select").select_option("virt-echo")
        expect(page.get_by_test_id("console-enter")).to_have_value("lf")
        page.get_by_test_id("console-settings").locator("summary").click()
        page.get_by_test_id("console-reset").click()
        expect(page.get_by_test_id("console-enter")).to_have_value("cr")
        browser.close()


def test_ended_run_shows_no_cursor(server):
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        cursor = page.locator("#term .xterm-cursor")
        page.get_by_test_id("console").click()
        expect(cursor).to_have_count(1)
        page.get_by_test_id("btn-stop").click()
        expect(page.get_by_test_id("status")).to_have_attribute("data-state", "exited")
        expect(cursor).to_have_count(0)
        browser.close()


@pytest.mark.skipif(not PROJECT_QEMU.exists(),
                    reason="needs the project QEMU (BENCH_QEMU or build/qemu)")
def test_map_follows_the_picked_run(server):
    """Map and Devices name their run; picking a run in Runs shows that run's
    map, and "current session" brings the session's back."""
    with sync_playwright() as pw:
        browser, page = echo_page(pw, server)
        echo_run = get_json(server, "/api/session")["run"]
        page.get_by_test_id("btn-stop").click()
        expect(page.get_by_test_id("status")).to_have_attribute("data-state", "exited")
        page.get_by_test_id("profile-select").select_option("rzv2l-smarc-m1-probe")
        page.get_by_test_id("btn-start").click()
        expect(page.get_by_test_id("status")).to_have_attribute(
            "data-state", "exited", timeout=60_000)
        m1_run = get_json(server, "/api/session")["run"]
        scif0 = page.locator('[data-testid=map-row][data-base="0x1004b800"]')

        page.get_by_test_id("tab-map").click()
        expect(page.get_by_test_id("map-run")).to_contain_text(f"This session: {m1_run}")
        expect(scif0).to_have_attribute("data-status", "modelled")

        page.get_by_test_id("tab-runs").click()
        page.locator(f'[data-testid=run-row][data-run="{echo_run}"]').click()
        page.get_by_test_id("tab-map").click()
        expect(page.get_by_test_id("map-run")).to_contain_text(f"Picked run: {echo_run}")
        expect(scif0).to_have_attribute("data-status", "covered")
        page.get_by_test_id("map-current").click()
        expect(page.get_by_test_id("map-run")).to_contain_text(f"This session: {m1_run}")
        expect(scif0).to_have_attribute("data-status", "modelled")
        browser.close()


# ---- the header readout, driven without QEMU ---------------------------------

def offline_page(browser, server, scheme="dark"):
    """The page with its live stream closed: setStatus() and the render
    functions are then the only things that change it."""
    page = browser.new_context(color_scheme=scheme, viewport={"width": 1440, "height": 900}).new_page()
    page.goto(server)
    expect(page.get_by_test_id("profile-select")).to_contain_text("virt")
    page.wait_for_function("ws && ws.readyState === WebSocket.OPEN")
    page.evaluate("ws.onclose = null; ws.onmessage = null; ws.close()")
    return page


def rgb(hex_):
    return "rgb({}, {}, {})".format(*(int(hex_[i:i + 2], 16) for i in (1, 3, 5)))


LED_CASES = [  # (status, LED token, verdict text)
    ({"state": "none"}, "led-off", ""),
    ({"state": "starting"}, "info", ""),
    ({"state": "running", "verdict": "running", "expect": ["a"], "expect_missing": ["a"]}, "ok", ""),
    ({"state": "paused"}, "warn", ""),
    ({"state": "exited", "exit_code": 0, "started": 1, "ended": 3.5}, "muted", ""),
    ({"state": "exited", "exit_code": 0, "verdict": "pass", "started": 1, "ended": 3.5}, "ok", "PASS"),
    ({"state": "exited", "exit_code": 1, "verdict": "fail", "verdict_reasons": ["exit 1"],
      "started": 1, "ended": 3.5}, "danger", "FAIL"),
]


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_readout_led_and_verdict(server, scheme):
    """The LED takes its state colour from the tokens; PASS/FAIL is the
    biggest text in the header, with the exit status and the run time."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = offline_page(browser, server, scheme)
        led = page.locator("#readout .led")
        verdict = page.get_by_test_id("verdict")
        for status, token, text in LED_CASES:
            page.evaluate("(s) => setStatus(s)", status)
            want = rgb(page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('--{token}').trim()"))
            expect(led).to_have_css("background-color", want)
            if text:
                expect(verdict).to_be_visible()
                expect(verdict).to_have_text(text)
                size = float(verdict.evaluate("(e) => getComputedStyle(e).fontSize")[:-2])
                assert size >= 18, status
                expect(page.get_by_test_id("exit-code")).to_have_text(f"exit {status['exit_code']}")
                expect(page.get_by_test_id("duration")).to_have_text("2.5 s")
            else:
                expect(verdict).to_be_hidden()
        browser.close()
