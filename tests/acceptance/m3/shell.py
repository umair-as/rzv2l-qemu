#!/usr/bin/env python3
"""Boot a kernel to the BusyBox shell on ttySC0 and talk to it (M3, M4).

Usage: shell.py OUTDIR [--tier g0|g1] [--watchdog] [extra QEMU args...]

Boots the stock kernel and device tree of the tier (G0: mainline and
DTB-U; G1: the Renesas vendor kernel and its DTB-V) with the G0 initramfs
on rzv2l-smarc in direct mode, with SCIF0 on a socket. Checks, on the
serial line:
  - the sh-sci console takes over (the "legacy console [ttySC0] enabled"
    line) and /init reports both CPUs online (0-1)
  - a per-run command gets its response: the shell computes a value the
    command line does not contain, tagged with a random marker
  - the clock controller, the pin controller and SCIF0 are bound to their
    drivers (rzg2l-cpg, pinctrl-rzg2l, sh-sci), and SCIF0's runtime PM
    status is "active": its CPG power domain attached
  - guest time advances: `sleep 10` moves /proc/uptime by 10 s or more, and
    guest time / host time is 0.99-1.03, timed from the arrival of each
    uptime line. QEMU truncates the 24 MHz counter period to 41 ns, so the
    expected value is about 1.016 (target/arm/cpu.c gt_cntfrq_period_ns;
    device map section 4, gap 18)
With --watchdog, on /dev/watchdog (WDT0) with BusyBox `watchdog`:
  - pinged every second with a 3 s timeout, the board does not reset in
    8 s; stopped with the daemon (magic close), it does not reset in 8 s
  - started and then not pinged, it resets the board within 20 s (3 s,
    then the boot back to the console), and after the new boot
    CPG_WDTOVF_RST reads 1: WDT0 caused the reset
Writes OUTDIR/serial.log (the whole serial line) and OUTDIR/qemu.log (the
-d log). Exit 0 only if every check passes. QEMU binary: $QEMU.
"""
import os
import re
import secrets
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "guests", "out")
INITRD = os.path.join(OUT, "g0", "initramfs.cpio.gz")
CPG_WDTOVF_RST = 0x11010B10
BOOT_TIMEOUT = 180  # s; the stubbed SD probes alone take about 17 s


class Serial:
    """The SCIF0 socket; every byte read is kept and logged."""

    def __init__(self, path, log):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for _ in range(100):
            try:
                self.sock.connect(path)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("no serial socket at " + path)
        self.sock.settimeout(0.5)
        self.buf = ""
        self.log = log

    def send(self, line):
        self.sock.sendall((line + "\n").encode())

    def wait(self, pattern, timeout, start=0):
        """Wait for a regex in the text read since offset start."""
        end = time.monotonic() + timeout
        rx = re.compile(pattern, re.M)
        while True:
            m = rx.search(self.buf, start)
            if m:
                return m
            if time.monotonic() > end:
                return None
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                return None
            text = data.decode("utf-8", "replace")
            self.buf += text
            self.log.write(text)
            self.log.flush()


def check_watchdog(s, mark, check):
    """The WDT0 checks of --watchdog (docstring above)."""
    boot = re.compile(r"Booting Linux on physical CPU")
    booted = len(boot.findall(s.buf))

    pos = len(s.buf)
    s.send("watchdog -T 3 -t 1 /dev/watchdog; sleep 8; echo %s-$((3+4))"
           % mark)
    ok = s.wait(re.escape(mark) + r"-7\b", 30, pos) is not None
    check(ok and len(boot.findall(s.buf)) == booted,
          "WDT0 pinged every 1 s (timeout 3 s): no reset in 8 s")

    pos = len(s.buf)
    s.send("killall watchdog; sleep 8; echo %s-$((4+4))" % mark)
    ok = s.wait(re.escape(mark) + r"-8\b", 30, pos) is not None
    check(ok and len(boot.findall(s.buf)) == booted,
          "WDT0 stopped by the daemon (magic close): no reset in 8 s")

    pos = len(s.buf)
    t0 = time.monotonic()
    s.send("watchdog -T 3 -t 1000 /dev/watchdog")
    # 3 s, then the boot back to the console: a 60 s default timeout
    # left in place (the timeout change did not apply) fails here
    m = s.wait(boot.pattern, 20, pos)
    if not check(m is not None, "WDT0 not pinged (timeout 3 s): the board "
                 "resets within 20 s (new boot after %.1f s)"
                 % (time.monotonic() - t0)):
        return
    pos = m.end()
    if not check(s.wait(r"G0-INIT: ready, cpus online (\S+)\r?\n",
                        BOOT_TIMEOUT, pos) is not None,
                 "the shell comes back after the reset"):
        return
    pos = len(s.buf)
    s.send("devmem 0x%08X; echo %s-$((5+4))" % (CPG_WDTOVF_RST, mark))
    s.wait(re.escape(mark) + r"-9\b", 30, pos)
    v = re.search(r"^0x([0-9A-Fa-f]{8})\r?$", s.buf[pos:], re.M)
    check(v is not None and int(v.group(1), 16) == 1,
          "CPG_WDTOVF_RST after the reset: %s (WDT0 = 0x00000001)"
          % (v.group(0).strip() if v else "none"))


def main():
    out = sys.argv[1]
    extra = sys.argv[2:]
    tier = "g0"
    if extra[:1] == ["--tier"]:
        tier, extra = extra[1], extra[2:]
    watchdog = extra[:1] == ["--watchdog"]
    if watchdog:
        extra = extra[1:]
    KERNEL = os.path.join(OUT, tier, "linux", "arch", "arm64", "boot",
                          "Image")
    DTB_U = os.path.join(OUT, tier, "r9a07g054l2-smarc.dtb")
    qemu = os.environ["QEMU"]
    os.makedirs(out, exist_ok=True)
    sock = os.path.join(out, "serial.sock")
    for f in (sock, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    for f in (KERNEL, DTB_U, INITRD):
        if not os.path.exists(f):
            print("FAIL missing %s: run tests/guests/g0/build-*.sh" % f)
            return 1

    cmd = [qemu, "-M", "rzv2l-smarc", "-kernel", KERNEL, "-dtb", DTB_U,
           "-initrd", INITRD, "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           # A cable on ETH0, so the stock bootargs' ip=on does not wait
           # 120 s for one (QEMU user networking)
           "-nic", "user,id=net0",
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")] + extra
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    failures = 0

    def check(ok, what):
        nonlocal failures
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            failures += 1
        return ok

    with open(os.path.join(out, "serial.log"), "w") as log:
        try:
            s = Serial(sock, log)
            check(s.wait(r"legacy console \[ttySC0\] enabled", BOOT_TIMEOUT)
                  is not None, "sh-sci takes over the console (ttySC0)")
            m = s.wait(r"G0-INIT: ready, cpus online (\S+)\r?\n", BOOT_TIMEOUT)
            if not check(m is not None, "/init runs from the initramfs"):
                return 1
            check(m.group(1) == "0-1",
                  "both CPUs online: /sys/devices/system/cpu/online = %s"
                  % m.group(1))

            # The command line has $((6*7)); only a working shell prints 42
            mark = "M3-" + secrets.token_hex(4)
            pos = len(s.buf)
            s.send("echo %s-$((6*7))" % mark)
            check(s.wait(re.escape(mark) + r"-42\b", 30, pos) is not None,
                  "the shell answers a per-run command (%s)" % mark)

            # Each driver is bound; the shell computes the tag (42)
            pos = len(s.buf)
            s.send("for d in rzg2l-cpg/11010000.clock-controller "
                   "pinctrl-rzg2l/11030000.pinctrl sh-sci/1004b800.serial; "
                   "do [ -e /sys/bus/platform/drivers/$d ] && "
                   "echo BOUND-$((40+2)) $d; done; echo PM-$((40+2)) "
                   "$(cat /sys/devices/platform/soc/1004b800.serial/"
                   "power/runtime_status); echo %s-$((2+2))" % mark)
            s.wait(re.escape(mark) + r"-4\b", 30, pos)
            bound = re.findall(r"^BOUND-42 (\S+)\r?$", s.buf[pos:], re.M)
            for d in ("rzg2l-cpg/11010000.clock-controller",
                      "pinctrl-rzg2l/11030000.pinctrl",
                      "sh-sci/1004b800.serial"):
                check(d in bound, "driver bound: %s" % d)
            pm = re.search(r"^PM-42 (\S+)\r?$", s.buf[pos:], re.M)
            check(pm is not None and pm.group(1) == "active",
                  "SCIF0 runtime PM status: %s (power domain attached)"
                  % (pm.group(1) if pm else "none"))

            # Rate from the arrival of each uptime line, so the command
            # overhead cancels out
            ups = []
            for cmd in ("cat /proc/uptime", "sleep 10; cat /proc/uptime"):
                pos = len(s.buf)
                s.send(cmd)
                m = s.wait(r"^(\d+\.\d+) \d+\.\d+\r?\n", 60, pos)
                ups.append((float(m.group(1)), time.monotonic())
                           if m else None)
            if check(None not in ups,
                     "two /proc/uptime readings around sleep 10"):
                guest = ups[1][0] - ups[0][0]
                host = ups[1][1] - ups[0][1]
                check(guest >= 10.0,
                      "guest time advances: uptime +%.2f s over sleep 10"
                      % guest)
                check(0.99 <= guest / host <= 1.03,
                      "guest time / host time = %.4f over sleep 10 "
                      "(0.99-1.03; gap 18 predicts about 1.016)"
                      % (guest / host))
            if watchdog:
                check_watchdog(s, mark, check)
        finally:
            proc.kill()
            proc.wait()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
