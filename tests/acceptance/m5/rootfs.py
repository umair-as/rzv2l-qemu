#!/usr/bin/env python3
"""M5 root file system acceptance for rzv2l-smarc: user space from the SD card.

Usage: rootfs.py OUTDIR --tier g0|g1

On a fresh copy of tests/guests/out/sd/sd.img (OUTDIR/sd.img), with the
kernel and DTB of the tier, no initramfs, and the command line the
board's U-Boot passes for an SD card root ("rw rootwait earlycon
root=/dev/mmcblk0p2"):
  boot 1: the kernel mounts ext4 from mmcblk0p2 (179:2) and runs
          /sbin/init (BusyBox) from it; / is mmcblk0p2, PID 1 is the
          card's /sbin/init, the card counts boot 1; write a file of
          1 MiB + 7 bytes, print its MD5, `poweroff`: QEMU exits by itself
  host:   the journal needs no recovery (the shutdown remounted the root
          read-only) and e2fsck -fn finds the root file system clean;
          debugfs reads the file (same MD5) and
          the boot count 1 from the image
  boot 2: a new QEMU on the same image: boot 2, the file reads back;
          write a second file, `reboot`: the same QEMU resets the board
          and the kernel boots again from the card: boot 3, both files
          read back; `poweroff`
  host:   clean again; boot count 3; the second file matches
Writes OUTDIR/boot{1,2}/serial.log and qemu.log. Exit 0 only if every
check passes. QEMU binary: $QEMU.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
from shell import Serial, BOOT_TIMEOUT  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "guests", "out")
IMAGE = os.path.join(OUT, "sd", "sd.img")
CMDLINE = "rw rootwait earlycon root=/dev/mmcblk0p2"
READY = r"SD-ROOT: ready, root (\S+), boot (\d+)"
FILE1 = ("/root/one.bin", 1024 * 1024 + 7)
FILE2 = ("/root/two.bin", 4097)

failures = 0


def check(ok, what):
    global failures
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures += 1
    return ok


def boot(tier, out, img):
    kernel = os.path.join(OUT, tier, "linux", "arch", "arm64", "boot",
                          "Image")
    dtb = os.path.join(OUT, tier, "r9a07g054l2-smarc.dtb")
    os.makedirs(out, exist_ok=True)
    sock = os.path.join(out, "serial.sock")
    for f in (sock, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    cmd = [os.environ["QEMU"], "-M", "rzv2l-smarc", "-kernel", kernel,
           "-dtb", dtb, "-append", CMDLINE, "-display", "none",
           "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           "-drive", "if=sd,index=0,format=raw,file=%s" % img,
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    return proc, log, Serial(sock, log)


def ready(s, start=0):
    """Wait for the card's ready line; return (root device, boot count)"""
    m = s.wait(READY, BOOT_TIMEOUT, start)
    return (m.group(1), int(m.group(2))) if m else (None, None)


def send(s, line):
    """Send @line; False once QEMU has closed the console"""
    try:
        s.send(line)
        return True
    except OSError:
        return False


def run(s, command, timeout=120):
    """Run @command; return its output, None on a timeout"""
    mark = "M5-" + secrets.token_hex(4)
    pos = len(s.buf)
    if not send(s, "%s; echo %s-$((6*7))" % (command, mark)):
        return None
    if s.wait(re.escape(mark) + r"-42\b", timeout, pos) is None:
        return None
    return s.buf[pos:]


def md5s(s, paths):
    """MD5 of each path, as the guest computes it"""
    o = run(s, "md5sum " + " ".join(paths)) or ""
    return dict((m.group(2), m.group(1)) for m in re.finditer(
        r"^([0-9a-f]{32})  (\S+)\r?$", o, re.M))


def write(s, path, size):
    run(s, "head -c %d /dev/urandom > %s" % (size, path))
    return md5s(s, [path]).get(path)


def poweroff(s, proc, what):
    """`poweroff` in the guest; QEMU must exit by itself. The console is
    read until then: with the socket unread, the guest's console stalls
    (QEMU writes it a byte at a time) and QEMU does not exit."""
    pos = len(s.buf)
    send(s, "poweroff")
    down = s.wait(r"reboot: Power down", 60, pos) is not None
    s.wait(r"(?!)", 30)  # read to the end of the stream: QEMU closed it
    try:
        proc.wait(5)
        exited = proc.returncode == 0
    except subprocess.TimeoutExpired:
        exited = False
    check(down and exited, "%s: poweroff: the kernel powers down and QEMU "
          "exits (status %s)" % (what, proc.poll()))


def stop(proc, log):
    if proc.poll() is None:
        proc.kill()
    proc.wait()
    log.close()


def root_partition(img, tmp):
    """Copy partition 2 of @img to a file; return its path"""
    table = json.loads(subprocess.run(
        ["sfdisk", "-J", img], capture_output=True, text=True,
        check=True).stdout)["partitiontable"]
    p = table["partitions"][1]
    part = os.path.join(tmp, "p2.img")
    with open(img, "rb") as f, open(part, "wb") as o:
        f.seek(p["start"] * 512)
        o.write(f.read(p["size"] * 512))
    return part


def host_checks(img, want, count, what):
    """e2fsck and debugfs on the image's root partition"""
    with tempfile.TemporaryDirectory() as tmp:
        part = root_partition(img, tmp)
        # A file system still mounted read-write at power-off keeps the
        # journal's needs_recovery flag, which e2fsck -n skips over
        sb = subprocess.run(["dumpe2fs", "-h", part], capture_output=True,
                            text=True).stdout
        feat = re.search(r"^Filesystem features:(.*)$", sb, re.M)
        check(feat is not None and "has_journal" in feat.group(1)
              and "needs_recovery" not in feat.group(1),
              "%s: the journal needs no recovery: the shutdown left the "
              "root file system unmounted or read-only" % what)
        fsck = subprocess.run(["e2fsck", "-fn", part], capture_output=True,
                              text=True)
        check(fsck.returncode == 0, "%s: e2fsck -fn finds the root file "
              "system clean (exit %d)" % (what, fsck.returncode))
        for path, md5 in want.items():
            dst = os.path.join(tmp, "dump")
            if os.path.exists(dst):
                os.unlink(dst)
            subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst),
                            part], capture_output=True)
            got = (hashlib.md5(open(dst, "rb").read()).hexdigest()
                   if os.path.exists(dst) else None)
            check(got is not None and got == md5,
                  "%s: %s in the image matches the guest's MD5"
                  % (what, path))
        o = subprocess.run(["debugfs", "-R", "cat /var/boot-count", part],
                           capture_output=True, text=True).stdout.strip()
        check(o == str(count), "%s: the image counts %d boots: %r"
              % (what, count, o))


def boot_checks(s, what, count):
    """The kernel mounted the card's ext4 as / and ran its /sbin/init"""
    dev, n = ready(s)
    if not check(dev is not None, "%s: the card's init reaches the shell"
                 % what):
        return False
    check("VFS: Mounted root (ext4 filesystem) on device 179:2" in s.buf,
          "%s: the kernel mounts ext4 from mmcblk0p2 (179:2) as /" % what)
    check("Run /sbin/init as init process" in s.buf,
          "%s: the kernel runs /sbin/init, not an initramfs /init" % what)
    check(dev == "/dev/mmcblk0p2" and n == count,
          "%s: / is %s, boot %s from this card" % (what, dev, n))
    o = run(s, "cat /proc/1/comm; readlink /proc/1/exe; cat /proc/cmdline")
    check(o is not None and re.search(r"^init\r?$", o, re.M)
          and re.search(r"^/bin/busybox\r?$", o, re.M)
          and re.search(r"^%s\r?$" % re.escape(CMDLINE), o, re.M),
          "%s: PID 1 is BusyBox init from the card; the command line is "
          "the board's" % what)
    return True


def main():
    out = sys.argv[1]
    tier = sys.argv[3] if sys.argv[2:3] == ["--tier"] else "g0"
    if not os.path.exists(IMAGE):
        print("FAIL missing %s: run tests/guests/sd/build-image.sh" % IMAGE)
        return 1
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "sd.img")
    shutil.copyfile(IMAGE, img)
    want = {}

    # Boot 1: user space from the card; a file; power off
    proc, log, s = boot(tier, os.path.join(out, "boot1"), img)
    try:
        if not boot_checks(s, "boot 1", 1):
            return 1
        want[FILE1[0]] = write(s, *FILE1)
        check(want[FILE1[0]] is not None, "boot 1: %s written (%d bytes)"
              % FILE1)
        poweroff(s, proc, "boot 1")
    finally:
        stop(proc, log)
    host_checks(img, want, 1, "host after boot 1")

    # Boot 2: a new QEMU; the file is there; a second file; reboot
    proc, log, s = boot(tier, os.path.join(out, "boot2"), img)
    try:
        if not boot_checks(s, "boot 2", 2):
            return 1
        check(md5s(s, [FILE1[0]]) == want,
              "boot 2: %s reads back with the same MD5" % FILE1[0])
        want[FILE2[0]] = write(s, *FILE2)
        pos = len(s.buf)
        send(s, "reboot")
        check(s.wait(r"reboot: Restarting system", 60, pos) is not None,
              "boot 2: reboot: the kernel restarts the system")
        dev, n = ready(s, pos)
        check(dev == "/dev/mmcblk0p2" and n == 3 and proc.poll() is None,
              "boot 3 (after the reset, same QEMU): / is %s, boot %s"
              % (dev, n))
        check(md5s(s, list(want)) == want,
              "boot 3: both files read back with the same MD5")
        poweroff(s, proc, "boot 3")
    finally:
        stop(proc, log)
    host_checks(img, want, 3, "host after boot 3")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
