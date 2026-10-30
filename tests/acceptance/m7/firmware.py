#!/usr/bin/env python3
"""M7 acceptance for rzv2l-smarc: the board's TF-A BL31 as the PSCI firmware.

Usage: firmware.py OUTDIR

Firmware mode: -bios tests/guests/out/fw/bl31.bin (TF-A f59ed5a31, the
board's BSP flags), the Renesas kernel (G1) and its DTB as BL33, the
root file system on a fresh copy of the SD card image (no initramfs),
the board's SD-root command line. QEMU stages BL2's hand-off; BL31 runs
at EL3 and answers the kernel's PSCI calls. Checks, on the serial line:
  boot 1: the BL31 banner; the kernel finds PSCI 1.1 and SMC Calling
          Convention 1.4 in the firmware, as on the board (QEMU's own
          PSCI reports SMCCC 1.0); the card's init reaches the shell;
          CPU1 boots through BL31's CPU_ON (the SoC's reset vector,
          reset and P-Channel registers): both CPUs online
  hotplug: CPU1 offline (BL31 CPU_OFF) and online again (CPU_ON from the
          off state), twice; the kernel sees CPU1 die and come back
  reset:  `reboot`: BL31's SYSTEM_RESET resets the board through WDT0;
          in the same QEMU, the BL31 banner again, then boot 2 from the
          card with both CPUs online
Writes OUTDIR/serial.log and qemu.log. Exit 0 only if every check
passes. QEMU binary: $QEMU.
"""
import os
import re
import secrets
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
from shell import Serial, BOOT_TIMEOUT  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "guests", "out")
BL31 = os.path.join(OUT, "fw", "bl31.bin")
KERNEL = os.path.join(OUT, "g1", "linux", "arch", "arm64", "boot", "Image")
DTB = os.path.join(OUT, "g1", "r9a07g054l2-smarc.dtb")
IMAGE = os.path.join(OUT, "sd", "sd.img")
CMDLINE = "rw rootwait earlycon root=/dev/mmcblk0p2"
BANNER = r"NOTICE:  BL31: v2\.10\.5"
READY = r"SD-ROOT: ready, root (\S+), boot (\d+)"
ONLINE = "/sys/devices/system/cpu/online"
CPU1 = "/sys/devices/system/cpu/cpu1/online"

failures = 0


def check(ok, what):
    global failures
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures += 1
    return ok


def run(s, command, timeout=60):
    """Run @command; return its output, None on a timeout"""
    mark = "M7-" + secrets.token_hex(4)
    pos = len(s.buf)
    try:
        s.send("%s; echo %s-$((6*7))" % (command, mark))
    except OSError:
        return None
    if s.wait(re.escape(mark) + r"-42\b", timeout, pos) is None:
        return None
    return s.buf[pos:]


def online(s):
    o = run(s, "cat " + ONLINE) or ""
    m = re.search(r"^([0-9,-]+)\r?$", o, re.M)
    return m.group(1) if m else None


def boot_checks(s, start, n):
    """The BL31 banner, PSCI from BL31, the card's init, both CPUs"""
    what = "boot %d" % n
    check(s.wait(BANNER, 30, start) is not None,
          "%s: the BL31 banner on SCIF0" % what)
    m = s.wait(READY, BOOT_TIMEOUT, start)
    if not check(m is not None, "%s: the card's init reaches the shell"
                 % what):
        return False
    log = s.buf[start:]
    check("psci: PSCIv1.1 detected in firmware" in log and
          "psci: SMC Calling Convention v1.4" in log,
          "%s: the kernel finds PSCI 1.1 and SMCCC 1.4 (BL31, not QEMU's "
          "PSCI)" % what)
    check(m.group(1) == "/dev/mmcblk0p2" and int(m.group(2)) == n,
          "%s: / is %s, boot %s from the card" % (what, m.group(1),
                                                  m.group(2)))
    check("CPU1: Booted secondary processor 0x0000000100" in log and
          online(s) == "0-1",
          "%s: CPU1 booted through BL31's CPU_ON; CPUs online 0-1" % what)
    return True


def main():
    out = sys.argv[1]
    for f in (BL31, KERNEL, DTB, IMAGE):
        if not os.path.exists(f):
            print("FAIL missing %s (tests/guests/*/build-*.sh)" % f)
            return 1
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "sd.img")
    shutil.copyfile(IMAGE, img)
    sock = os.path.join(out, "serial.sock")
    for f in (sock, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    cmd = [os.environ["QEMU"], "-M", "rzv2l-smarc", "-bios", BL31,
           "-kernel", KERNEL, "-dtb", DTB, "-append", CMDLINE,
           "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           "-drive", "if=sd,index=0,format=raw,file=%s" % img,
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    s = Serial(sock, log)
    try:
        if not boot_checks(s, 0, 1):
            return 1

        for i in (1, 2):
            pos = len(s.buf)
            run(s, "echo 0 > " + CPU1)
            check(online(s) == "0" and
                  s.wait(r"psci: CPU1 killed", 10, pos) is not None,
                  "hotplug %d: CPU1 offline (BL31 CPU_OFF): CPUs online 0"
                  % i)
            pos = len(s.buf)
            run(s, "echo 1 > " + CPU1)
            check(online(s) == "0-1" and
                  s.wait(r"CPU1: Booted secondary processor 0x0000000100",
                         10, pos) is not None,
                  "hotplug %d: CPU1 online again (BL31 CPU_ON): CPUs online "
                  "0-1" % i)

        pos = len(s.buf)
        s.send("reboot")
        check(s.wait(r"reboot: Restarting system", 60, pos) is not None,
              "reset: the kernel asks the firmware for a system reset")
        boot_checks(s, pos, 2)
        check(proc.poll() is None, "reset: the same QEMU, the board reset")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        log.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
