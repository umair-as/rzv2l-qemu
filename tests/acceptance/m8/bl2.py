#!/usr/bin/env python3
"""M8 acceptance for rzv2l-smarc: the board's TF-A BL2 from the QSPI flash
(docs/units/M8-bl2-staging/spec.md).

Usage: bl2.py OUTDIR

Boot mode 3 (1.8 V serial flash), no -bios and no -kernel: the machine
stands in for the boot ROM and loads BL2 from the flash image
tests/guests/out/spi/spi.img (tests/guests/fw/build-spi-image.sh) into
on-chip RAM. Checks:
  boot:   BL2 prints its two banner lines on SCIF0 (TF-A f59ed5a31, the
          project's build); it gets through its clock, pin and security
          set-up and stops at its first access to the DDR PHY or memory
          controller (0x11400000, 0x11410000), the next unit's work; every
          other line of the -d unimp,guest_errors,invalid_mem log is in
          expected/log-allow.txt
  errors: no flash drive, a flash without the loader signature, a loader
          size of 0 or above 0x1D000, an image shorter than its loader:
          QEMU stops at once, naming the cause
Writes OUTDIR/boot/{serial.log,qemu.log} and OUTDIR/errors/*.txt. Exit 0
only if every check passes. QEMU binary: $QEMU.
"""
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = os.path.join(HERE, "..", "..", "guests", "out", "spi", "spi.img")
ALLOW = os.path.join(HERE, "expected", "log-allow.txt")
BANNER = [r"NOTICE:  BL2: v2\.10\.5\(release\):2\.10\.5/rz_1\.1\.0",
          r"NOTICE:  BL2: Built : f59ed5a31"]
DDR = re.compile(r"(?:Invalid (?:read|write) at addr 0x114[01][0-9a-f]{4}|"
                 r"ddr-memc: unimplemented device (?:read|write))")

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


def boot(out):
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "spi.img")
    shutil.copyfile(IMAGE, img)
    serial = os.path.join(out, "serial.log")
    log = os.path.join(out, "qemu.log")
    for f in (serial, log):
        if os.path.exists(f):
            os.unlink(f)
    rc, _ = qemu(["-serial", "file:" + serial,
                  "-drive", "if=mtd,format=raw,file=" + img,
                  "-d", "unimp,guest_errors,invalid_mem", "-D", log], out, 15)
    text = open(serial, errors="replace").read()
    pos = 0
    for i, line in enumerate(BANNER):
        m = re.compile(line).search(text, pos)
        check(m is not None, "boot: BL2 banner line %d on SCIF0" % (i + 1))
        pos = m.end() if m else pos
    check(rc is None, "boot: QEMU keeps running (BL2 waits at the DDR "
          "set-up, it does not exit)")
    lines = open(log, errors="replace").read().splitlines()
    first = next((i for i, l in enumerate(lines) if DDR.search(l)), None)
    check(first is not None,
          "boot: BL2 stops at its first DDR access (%s)"
          % (lines[first] if first is not None else "none"))
    allow = [re.compile(r) for r in open(ALLOW).read().splitlines()
             if r and not r.startswith("#")]
    before = lines[:first] if first is not None else lines
    bad = sorted({l for l in before if not any(a.search(l) for a in allow)})
    check(not bad, "boot: before it, only listed log lines%s"
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
