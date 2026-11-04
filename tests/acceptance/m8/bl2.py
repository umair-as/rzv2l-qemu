#!/usr/bin/env python3
"""M8 acceptance for rzv2l-smarc: the board's TF-A BL2 from the QSPI flash
(docs/units/M8-bl2-staging/spec.md, M8-ddr-stub/spec.md).

Usage: bl2.py OUTDIR

Boot mode 3 (1.8 V serial flash), no -bios and no -kernel: the machine
stands in for the boot ROM and loads BL2 from the flash image
tests/guests/out/spi/spi.img (tests/guests/fw/build-spi-image.sh) into
on-chip RAM. Checks:
  boot:   BL2 prints its two banner lines on SCIF0 (TF-A f59ed5a31, the
          project's build), then, through its DDR set-up and the FIP read
          from the flash, its board, SYS_LSI_MODE (the machine's default
          straps), SYS_LSI_DEVID and SYS_LSI_PRR lines and "Booting BL31";
          QEMU is stopped there (what BL31 and the rest do is the next
          unit's check). SCIF0 and the -d unimp,guest_errors,invalid_mem
          log share one stream, in QEMU's order: up to that line the log
          has no DDR controller or PHY line, and every line is in
          expected/log-allow.txt
  errors: no flash drive, a flash without the loader signature, a loader
          size of 0 or above 0x1D000: QEMU stops at once, naming the
          cause; a size of exactly 0x1D000 boots; an image shorter than
          the flash stops QEMU at the flash model's size check
Writes OUTDIR/boot/console.log and OUTDIR/errors/*.txt. Exit 0
only if every check passes. QEMU binary: $QEMU.
"""
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, "..", "..", "guests", "out", "spi", "spi.img")
ALLOW = os.path.join(HERE, "expected", "log-allow.txt")
BANNER = [r"NOTICE:  BL2: v2\.10\.5\(release\):2\.10\.5/rz_1\.1\.0",
          r"NOTICE:  BL2: Built : f59ed5a31"]
BL2 = BANNER + [r"NOTICE:  BL2: RZ/V2L\r?\n",
                r"NOTICE:  BL2: SYS_LSI_MODE: 0x10003\r?\n",
                r"NOTICE:  BL2: SYS_LSI_DEVID: 0x18447447\r?\n",
                r"NOTICE:  BL2: SYS_LSI_PRR: 0x0\r?\n",
                r"NOTICE:  BL2: Booting BL31\r?\n"]
DDR = re.compile(r"(?:0x114[01][0-9a-f]{4}|renesas-rzv2l-ddr)")
SERIAL = re.compile(r"^(?:(?:NOTICE|ERROR|WARNING|INFO|VERBOSE):  |"
                    r"qemu-system-aarch64: warning: nic renesas-gbeth\.[01] "
                    r"has no peer$)")

failures = 0


def check(ok, what):
    global failures
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures += 1
    return ok


def qemu(args, out, seconds):
    """Run QEMU for at most seconds; return (exit code or None, stderr)"""
    cmd = [os.environ["QEMU"], "-M", "rzv2l-smarc,boot-mode=3",
           "-display", "none", "-nodefaults"] + args
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE, text=True)
    try:
        _, err = p.communicate(timeout=seconds)
        return p.returncode, err
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
        return None, err


def until(args, out, pattern, seconds):
    """Run QEMU with SCIF0 and the -d log on one stream, in the order QEMU
    wrote them, until a line matches pattern; save the stream to out and
    return its lines up to that one (all lines if never seen) and whether
    it was seen"""
    cmd = [os.environ["QEMU"], "-M", "rzv2l-smarc,boot-mode=3",
           "-display", "none", "-nodefaults", "-serial", "stdio"] + args
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    data = b""
    seen = None
    deadline = time.monotonic() + seconds
    while seen is None and time.monotonic() < deadline:
        r, _, _ = select.select([p.stdout], [], [], 0.1)
        if not r:
            continue
        chunk = os.read(p.stdout.fileno(), 65536)
        if not chunk:
            break
        data += chunk
        lines = data.decode(errors="replace").split("\n")
        seen = next((i for i, l in enumerate(lines[:-1])
                     if re.search(pattern, l + "\n")), None)
    p.kill()
    p.wait()
    with open(out, "wb") as f:
        f.write(data)
    lines = [l.rstrip("\r") for l in data.decode(errors="replace").split("\n")]
    return (lines if seen is None else lines[:seen + 1]), seen is not None


def boot(out):
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "spi.img")
    shutil.copyfile(IMAGE, img)
    stream = os.path.join(out, "console.log")
    lines, _ = until(["-drive", "if=mtd,format=raw,file=" + img,
                      "-d", "unimp,guest_errors,invalid_mem"],
                     stream, BL2[-1], 60)
    text = "\n".join(lines) + "\n"
    pos = 0
    for line in BL2:
        m = re.compile(line).search(text, pos)
        check(m is not None, "boot: in order on SCIF0: %s"
              % line.replace("\\r?\\n", "").replace("\\", ""))
        pos = m.end() if m else pos
    # The firmware's own lines and QEMU's start-up warnings are not the log
    lines = [l for l in lines if l and not SERIAL.search(l)]
    ddr = [l for l in lines if DDR.search(l)]
    check(not ddr, "boot: up to that line, no DDR controller or PHY log line%s"
          % ("" if not ddr else ": " + "; ".join(ddr[:5])))
    allow = [re.compile(r) for r in open(ALLOW).read().splitlines()
             if r and not r.startswith("#")]
    bad = sorted({l for l in lines if not any(a.search(l) for a in allow)})
    check(not bad, "boot: up to that line, only listed log lines%s"
          % ("" if not bad else ": " + "; ".join(bad[:5])))


def errors(out):
    os.makedirs(out, exist_ok=True)
    data = open(IMAGE, "rb").read()

    def image(name, content):
        path = os.path.join(out, name + ".img")
        with open(path, "wb") as f:
            f.write(content)
        return path

    def size_block(size):
        return struct.pack("<I", size) + data[4:]

    cases = [
        ("no flash drive", [], r"boots from the QSPI flash: give it with "
         r"-drive if=mtd"),
        ("no loader signature",
         ["-drive", "if=mtd,format=raw,file=" +
          image("nosig", data[:0x1fe] + b"\xff\xff" + data[0x200:])],
         r"no loader on the QSPI flash \(signature ff ff at 0x1fe"),
        ("loader size 0",
         ["-drive", "if=mtd,format=raw,file=" + image("size0", size_block(0))],
         r"loader size 0x0 is not 1 to 0x1d000 bytes"),
        ("loader size above 0x1D000",
         ["-drive", "if=mtd,format=raw,file=" +
          image("big", size_block(0x1d004))],
         r"loader size 0x1d004 is not 1 to 0x1d000 bytes"),
    ]
    for what, args, msg in cases:
        rc, err = qemu(args, out, 10)
        open(os.path.join(out, re.sub(r"\W+", "-", what) + ".txt"),
             "w").write(err)
        check(rc not in (None, 0) and re.search(msg, err) is not None,
              "errors: %s: QEMU stops (exit %s) with \"%s\""
              % (what, rc, msg.replace("\\", "")))
    # A loader of exactly 0x1D000 bytes (BL2 and the 0xFF after it) fits
    rc, err = qemu(["-serial", "file:" + os.path.join(out, "max.serial"),
                    "-drive", "if=mtd,format=raw,file=" +
                    image("max", size_block(0x1d000))], out, 10)
    text = open(os.path.join(out, "max.serial"), errors="replace").read()
    check(rc is None and re.search(BANNER[0], text) is not None,
          "errors: a loader size of exactly 0x1D000 is accepted: BL2 starts")
    # An image shorter than its loader. m25p80 refuses a drive smaller
    # than the part, so the stand-in's own check cannot be reached through
    # the flash model: QEMU must still stop and say why.
    rc, err = qemu(["-drive", "if=mtd,format=raw,file=" +
                    image("short", data[:0x200 + 0x100])], out, 10)
    open(os.path.join(out, "short.txt"), "w").write(err)
    check(rc not in (None, 0) and err.strip() != "",
          "errors: an image shorter than its loader: QEMU stops (exit %s): "
          "%s" % (rc, err.strip().splitlines()[-1] if err.strip() else ""))


def main():
    out = sys.argv[1]
    if not os.path.exists(IMAGE):
        print("FAIL missing %s (tests/guests/fw/build-spi-image.sh)" % IMAGE)
        return 1
    boot(os.path.join(out, "boot"))
    errors(os.path.join(out, "errors"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
