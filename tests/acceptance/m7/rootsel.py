#!/usr/bin/env python3
"""M7 acceptance for rzv2l-smarc: the root is chosen by PARTUUID (DR-0007).

Usage: rootsel.py OUTDIR

The chain of bootloader.py (BL31, OP-TEE, U-Boot with the project's boot
configuration, tests/guests/sd/boot.env). Checks:
  identifiers: the two project cards (sd.img, sd-tee.img) have distinct
          disk identifiers, so distinct PARTUUIDs
  other medium: two cards. The module slot (mmc 0) holds sd-tee.img,
          whose environment keeps the kernel source (mmc 0:2: the TEE
          kernel) and names sd.img's partition 2 as the root; the carrier
          slot (mmc 1) holds sd.img. The kernel comes from one card and
          its root from the other: / is sd.img's partition 2 by PARTUUID,
          whatever names Linux gives the two cards (with two cards and no
          mmc aliases, both names follow the probe order)
  missing root: one card whose environment names a PARTUUID no attached
          card has: the kernel waits rootwait=30 s for it, then stops
          with "VFS: Unable to mount root fs" and the PARTUUID in its
          log, a visible failure rather than a wrong root
Writes OUTDIR/<check>/serial.log and qemu.log. Exit 0 only if every
check passes. QEMU binary: $QEMU.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check, partuuid  # noqa: E402
from shell import BOOT_TIMEOUT  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "guests", "out")
SD = os.path.join(OUT, "sd", "sd.img")
SD_TEE = os.path.join(OUT, "sd", "sd-tee.img")
TEE_KERNEL = os.path.join(OUT, "g1-tee", "linux", "arch", "arm64", "boot",
                          "Image")
MISSING = "525a00ff-02"


def other_medium(out):
    bootloader.IMAGE = SD_TEE
    bootloader.KERNEL = TEE_KERNEL
    bootloader.ROOT = SD
    proc, s, log = bootloader.start(
        out, env=["root_partuuid=" + partuuid(SD)], carrier=SD)
    try:
        if bootloader.boot_checks(s, 0, 1):
            out = firmware.run(s, "for b in /sys/block/mmcblk?; do echo "
                               "name:${b##*/}:$(readlink -f $b | grep -o "
                               "'11c[01]0000'); done") or ""
            names = dict((addr, name) for name, addr in
                         re.findall(r"name:(mmcblk\d):(11c[01]0000)", out))
            print("     this boot: the module card (SDHI0) is %s, the "
                  "carrier card (SDHI1) %s"
                  % (names.get("11c00000", "?"),
                     names.get("11c10000", "?")))
    finally:
        bootloader.stop(proc, log)


def missing_root(out):
    bootloader.IMAGE = SD
    bootloader.KERNEL = firmware.KERNEL
    bootloader.ROOT = None
    proc, s, log = bootloader.start(out, env=["root_partuuid=" + MISSING])
    try:
        m = s.wait(firmware.READY + "|" + firmware.NOROOT, BOOT_TIMEOUT)
        log_text = s.buf
        check(m is not None and m.group(0).startswith("VFS") and
              "Waiting for root device PARTUUID=%s" % MISSING in log_text,
              "missing root: the kernel waits for PARTUUID=%s, then stops "
              "with 'VFS: Unable to mount root fs' (no wrong root)"
              % MISSING)
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    ids = {partuuid(SD), partuuid(SD_TEE)}
    check(len(ids) == 2 and partuuid(SD, 1) != partuuid(SD_TEE, 1),
          "identifiers: sd.img and sd-tee.img have distinct PARTUUIDs (%s)"
          % ", ".join(sorted(ids)))
    other_medium(os.path.join(out, "other-medium"))
    missing_root(os.path.join(out, "missing-root"))
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
