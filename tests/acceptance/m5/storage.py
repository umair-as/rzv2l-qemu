#!/usr/bin/env python3
"""M5 storage acceptance for rzv2l-smarc: an ext4 file system on an SD card.

Usage: storage.py OUTDIR --tier g0|g1

On a fresh copy of tests/guests/out/sd/sd.img (OUTDIR/sd.img), with the
kernel and DTB of the tier and the BusyBox initramfs:
  boot 1: the SD card on SDHI0 is found (no request timeout), SDHI1 has
          no card; mount the ext4 partition, check the image's README,
          write four files whose sizes cross block and request
          boundaries (1, 513, 4097 bytes, 1 MiB + 7), print their MD5,
          sync and unmount; then stop QEMU
  host:   e2fsck -fn finds the file system clean; debugfs reads each
          file from the image and its MD5 matches the guest's
  boot 2: a new QEMU on the same image: the files read back with the
          same MD5
Clean unmount only: nothing here is a claim about power loss.
Writes OUTDIR/boot{1,2}/serial.log and qemu.log. Exit 0 only if every
check passes. QEMU binary: $QEMU.
"""
import hashlib
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
INITRD = os.path.join(OUT, "g0", "initramfs.cpio.gz")
IMAGE = os.path.join(OUT, "sd", "sd.img")
PART_START = 2048 * 512
FILES = [("one.bin", 1), ("b513.bin", 513), ("p4097.bin", 4097),
         ("big.bin", 1024 * 1024 + 7)]

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
           "-dtb", dtb, "-initrd", INITRD, "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           "-drive", "if=sd,index=0,format=raw,file=%s" % img,
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    s = Serial(sock, log)
    ready = s.wait(r"G0-INIT: ready", BOOT_TIMEOUT) is not None
    return proc, log, s, ready


def run(s, command, timeout=120):
    """Run @command; return its output, None on a timeout"""
    mark = "M5-" + secrets.token_hex(4)
    pos = len(s.buf)
    s.send("%s; echo %s-$((6*7))" % (command, mark))
    if s.wait(re.escape(mark) + r"-42\b", timeout, pos) is None:
        return None
    return s.buf[pos:]


def stop(proc, log):
    proc.kill()
    proc.wait()
    log.close()


def main():
    out = sys.argv[1]
    tier = sys.argv[3] if sys.argv[2:3] == ["--tier"] else "g0"
    if not os.path.exists(IMAGE):
        print("FAIL missing %s: run tests/guests/sd/build-image.sh" % IMAGE)
        return 1
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "sd.img")
    shutil.copyfile(IMAGE, img)
    mount = "mkdir -p /mnt; P=$(ls /dev/mmcblk*p1); mount $P /mnt"

    # Boot 1: find the card, write the files
    proc, log, s, ready = boot(tier, os.path.join(out, "boot1"), img)
    want = {}
    try:
        if not check(ready, "boot 1: /init runs"):
            return 1
        check(re.search(r"mmc\d: new (high speed )?SD(HC)? card", s.buf)
              is not None, "boot 1: the SD card on SDHI0 is found")
        check("timeout waiting for hardware interrupt" not in s.buf,
              "boot 1: no SD request timeout")
        o = run(s, "ls /sys/class/mmc_host | wc -l; "
                "ls /sys/bus/mmc/devices | wc -l")
        n = re.findall(r"^(\d+)\r?$", o or "", re.M)
        check(n[:2] == ["2", "1"],
              "boot 1: two SD hosts, one card (SDHI1 empty): %s" % n[:2])
        o = run(s, mount + " && cat /mnt/README")
        check(o is not None and "build-image.sh" in o,
              "boot 1: ext4 mounted, the image's README reads back")
        for name, size in FILES:
            run(s, "head -c %d /dev/urandom > /mnt/%s" % (size, name))
        o = run(s, "cd /mnt && md5sum %s; cd /; sync; umount /mnt && "
                "echo UMOUNT-$((40+2))" % " ".join(f for f, _ in FILES), 300)
        for m in re.finditer(r"^([0-9a-f]{32})  (\S+)\r?$", o or "", re.M):
            want[m.group(2)] = m.group(1)
        check(len(want) == len(FILES) and "UMOUNT-42" in (o or ""),
              "boot 1: %d files written, synced, unmounted" % len(want))
    finally:
        stop(proc, log)

    # Host: the image itself, read by e2fsprogs
    with tempfile.TemporaryDirectory() as tmp:
        part = os.path.join(tmp, "p1.img")
        with open(img, "rb") as f, open(part, "wb") as p:
            f.seek(PART_START)
            shutil.copyfileobj(f, p)
        fsck = subprocess.run(["e2fsck", "-fn", part], capture_output=True,
                              text=True)
        check(fsck.returncode == 0, "host: e2fsck -fn finds the file system "
              "clean (exit %d)" % fsck.returncode)
        for name, size in FILES:
            dst = os.path.join(tmp, name)
            subprocess.run(["debugfs", "-R", "dump /%s %s" % (name, dst),
                            part], capture_output=True)
            got = (hashlib.md5(open(dst, "rb").read()).hexdigest()
                   if os.path.exists(dst) else None)
            check(got is not None and got == want.get(name),
                  "host: %s (%d bytes) in the image matches the guest's MD5"
                  % (name, size))

    # Boot 2: a new QEMU on the same image
    proc, log, s, ready = boot(tier, os.path.join(out, "boot2"), img)
    try:
        if not check(ready, "boot 2: /init runs"):
            return 1
        o = run(s, mount + " && cd /mnt && md5sum %s; cd /; umount /mnt"
                % " ".join(f for f, _ in FILES), 300)
        got = dict((m.group(2), m.group(1)) for m in re.finditer(
            r"^([0-9a-f]{32})  (\S+)\r?$", o or "", re.M))
        for name, _ in FILES:
            check(got.get(name) is not None and got.get(name) == want.get(name),
                  "boot 2: %s reads back with the same MD5" % name)
    finally:
        stop(proc, log)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
