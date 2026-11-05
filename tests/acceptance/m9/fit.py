#!/usr/bin/env python3
"""M9 acceptance for rzv2l-smarc: signed FIT images on the automatic boot
path of the M9 profile (docs/units/M9-fit/spec.md, DR-0008).

Usage: fit.py OUTDIR

The whole chain from the QSPI flash, boot mode 3, no -bios, -kernel,
bl32= or bl33=: BL2, BL31, OP-TEE, then the M9 U-Boot (FIT signature
checks, two environment copies) from tests/guests/out/spi/spi-m9.img.
The card is a fresh copy of tests/guests/out/sd/sd-m9.img per case;
for a negative case, slot A's /boot/fitImage is replaced with that
negative image (tests/guests/fw/build-fit-m9.sh) and both environment
copies get BOOT_ORDER=A, so that only slot A is tried. Each run
directory has command.txt and images.sha256 (the flash and card it
used) and fit.sha256 (the FIT in slot A).
Checks, on the serial line, each line searched from the end of the one
before:
  accepted: U-Boot 2024.07-m9; the environment from MMC; the attempt
          saved (BOOT_A_LEFT=2) before the FIT loads; the configuration
          verified with the profile key (sha256,rsa2048:m9-dev+ OK);
          the kernel starts, all in the first boot (no reset before);
          / is slot A's partition by PARTUUID; after
          QEMU stops, a valid environment copy on the card holds
          BOOT_A_LEFT=2
  each negative (kernel-changed, dtb-changed, unsigned, other-key,
          fakeroot, kernel-at): three attempts, each saved (2, 1, 0),
          each refused with its reason and followed by a reset, then
          "no slot has an attempt left" with the counters and the
          U-Boot prompt; "Starting kernel" never appears
Exit 0 only if every check passes. QEMU binary: $QEMU.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "m7"))
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check  # noqa: E402

GUESTS = os.path.join(HERE, "..", "..", "guests")
FLASH = os.path.join(GUESTS, "out", "spi", "spi-m9.img")
CARD = os.path.join(GUESTS, "out", "sd", "sd-m9.img")
FITS = os.path.join(GUESTS, "out", "m9", "fit")
ENV = os.path.join(GUESTS, "fw", "u-boot-m9.env")
UENV = os.path.join(GUESTS, "sd", "uboot-env.py")
SLOT_A = (40960, 98304)       # p2: first sector, sectors (build-image-m9.sh)
BANNER = r"U-Boot 2024\.07-m9 "
ENV_OK = r"Loading Environment from MMC\.\.\. Reading from MMC\(0\)\.\.\. OK"
# What U-Boot prints when it refuses each negative FIT. Upstream's two
# crafted FITs fail U-Boot's format check before any signature check
# (boot/image-fit.c:2082-2086 fit_image_load, fit_check_format)
REASON = {
    "kernel-changed": r"Bad Data Hash",
    "dtb-changed": r"Bad Data Hash",
    "unsigned": r"Failed to verify required signature 'key-m9-dev'",
    "other-key": r"Failed to verify required signature 'key-m9-dev'",
    "fakeroot": r"Bad FIT kernel image format! \(err=-22\)",
    "kernel-at": r"Signature checking prevents use of unit addresses \(@\) "
                 r"in nodes",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def card(out, fit, env=()):
    """A copy of CARD with fit in slot A and env (NAME=VALUE) in both
    environment copies; returns its path"""
    os.makedirs(out, exist_ok=True)
    img = os.path.join(out, "source-sd-m9.img")
    shutil.copyfile(CARD, img)
    if fit is not None:
        part = os.path.join(out, "slot-a.img")
        with open(img, "rb") as f:
            f.seek(SLOT_A[0] * 512)
            open(part, "wb").write(f.read(SLOT_A[1] * 512))
        for req in ("rm /boot/fitImage", "write %s /boot/fitImage" % fit):
            subprocess.run(["debugfs", "-w", "-R", req, part], check=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        with open(img, "r+b") as f:
            f.seek(SLOT_A[0] * 512)
            f.write(open(part, "rb").read())
        os.unlink(part)
    if env:
        subprocess.run([sys.executable, "-I", UENV, "m9-write", img, ENV]
                       + list(env), check=True)
    with open(os.path.join(out, "fit.sha256"), "w") as f:
        f.write("%s  %s\n" % (sha256(fit or os.path.join(FITS, "fitImage")),
                              os.path.basename(fit or "fitImage")))
    return img


def start(out, img):
    bootloader.IMAGE = img
    return bootloader.start(out, flash=FLASH)


def in_order(s, patterns, start, what, timeout=120):
    pos = start
    for p in patterns:
        m = s.wait(p, timeout, pos)
        if not check(m is not None, "%s: in order: %s"
                     % (what, p.replace("\\", ""))):
            return None
        pos = m.end()
    return pos


def env_after(out, img):
    copy = os.path.join(out, "slot0-" + os.path.basename(img))
    return subprocess.run([sys.executable, "-I", UENV, "m9-read", copy],
                          capture_output=True, text=True).stdout


def accepted(out):
    img = card(out, None)
    proc, s, log = start(out, img)
    try:
        pos = in_order(s, [BANNER, ENV_OK,
                           r"Writing to redundant MMC\(0\)\.\.\. OK",
                           r"M9: slot A: attempt saved: BOOT_A_LEFT=2 "
                           r"BOOT_B_LEFT=3",
                           r"Using 'conf' configuration",
                           r"Verifying Hash Integrity \.\.\. "
                           r"sha256,rsa2048:m9-dev\+ OK",
                           r"Starting kernel"], 0, "accepted")
        if pos is not None:
            check(s.buf[:pos].count("NOTICE:  BL2: v2") == 1 and
                  "M9: slot A: resetting" not in s.buf[:pos],
                  "accepted: all of it in the first boot, no reset before "
                  "the kernel starts")
            m = firmware.wait_root(s, pos, "accepted")
            check(m is not None and
                  re.search(r"M9 slot A, ", s.buf[pos:]) is not None and
                  m.group(3) == "525a0003-02" and m.group(4) == "sd-m9",
                  "accepted: / is slot A, PARTUUID 525a0003-02")
    finally:
        bootloader.stop(proc, log)
    state = env_after(out, img)
    check(re.search(r"valid flag 2 .*BOOT_A_LEFT=2 ", state) is not None,
          "accepted: the card's newer environment copy holds BOOT_A_LEFT=2"
          " (%s)" % " | ".join(state.splitlines()))


def negative(out, name):
    what = "refused %s" % name
    img = card(out, os.path.join(FITS, "fitImage-" + name),
               ["BOOT_ORDER=A"])
    proc, s, log = start(out, img)
    try:
        pos = 0
        for left in (2, 1, 0):
            pos = in_order(s, [BANNER,
                               r"M9: slot A: attempt saved: BOOT_A_LEFT=%d "
                               % left,
                               REASON[name],
                               r"M9: slot A: bootm returned",
                               r"M9: slot A: resetting"], pos,
                           "%s, attempt %d" % (what, 3 - left))
            if pos is None:
                return
        in_order(s, [BANNER, r"M9: no slot has an attempt left: "
                     r"BOOT_ORDER=A BOOT_A_LEFT=0 BOOT_B_LEFT=3",
                     r"=> "], pos, "%s, after three" % what)
        check("Starting kernel" not in s.buf,
              "%s: the kernel never starts" % what)
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    for f in [FLASH, CARD, ENV, os.path.join(FITS, "fitImage")] + \
            [os.path.join(FITS, "fitImage-" + n) for n in REASON]:
        if not os.path.exists(f):
            print("FAIL missing %s (tests/guests/fw/build-*-m9.sh, "
                  "build-spi-image.sh --m9, sd/build-image-m9.sh)" % f)
            return 1
    shutil.rmtree(out, ignore_errors=True)
    accepted(os.path.join(out, "accepted"))
    for name in REASON:
        negative(os.path.join(out, name), name)
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
