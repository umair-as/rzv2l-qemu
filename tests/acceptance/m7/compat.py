#!/usr/bin/env python3
"""M7 compatibility check for rzv2l-smarc: the vendor's unchanged boot.

Usage: compat.py OUTDIR

The chain of bootloader.py (BL31, OP-TEE, U-Boot, the Renesas kernel G1
from the card), with the card's U-Boot environment block cleared: U-Boot
finds no saved environment and runs the vendor's default command, as a
board with no saved environment does. That command resets the
environment, loads the kernel from mmc 0:2 (no card in mmc 1) and passes
root=/dev/mmcblk0p2 rootwait. The vendor device tree has no mmc aliases,
so Linux names the card mmcblk0 or mmcblk1 in probe order
(docs/device-map.md, gap 22): a boot whose card is mmcblk1 waits for its
root for ever (Linux stops WDT0's clock, so nothing resets it).

Two cold boots, each in its own QEMU. Each boot is reported: PASS when
the card's init reaches the shell on /dev/mmcblk0p2, FAIL when the boot
lost its root (named) or did not get there. Both are counted; a later
boot never replaces an earlier one. The last line is the verdict:
  VENDOR-DEFAULT COMPATIBILITY: PASS (2 of 2 boots found their root)
  VENDOR-DEFAULT COMPATIBILITY: FAIL (n of 2 boots lost their root ...)
This verdict is separate from the M7 acceptance (run.sh), whose U-Boot
runs use the project's boot configuration (DR-0007). Writes
OUTDIR/boot<n>/serial.log and qemu.log. Exit 0 only if both boots pass.
QEMU binary: $QEMU.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check  # noqa: E402
from shell import BOOT_TIMEOUT  # noqa: E402

BOOTS = 2
DEFAULT_ENV = r"bad CRC, using default environment"
LOST = r"Waiting for root device /dev/mmcblk0p2"


def boot(out, n):
    """One cold boot; return "ok", "lost" or "fail" """
    what = "vendor boot %d" % n
    proc, s, log = bootloader.start(out, env="vendor")
    try:
        if not check(s.wait(DEFAULT_ENV, 60) is not None,
                     "%s: U-Boot finds no saved environment and uses its "
                     "default" % what):
            return "fail"
        size = os.path.getsize(bootloader.KERNEL)
        if not check(s.wait(r"%d bytes read" % size, 90) is not None and
                     s.wait(r"Starting kernel", 30) is not None,
                     "%s: U-Boot's default command reads boot/Image from "
                     "mmc 0:2 and starts it" % what):
            return "fail"
        m = s.wait(firmware.READY + "|" + LOST, BOOT_TIMEOUT)
        if m is not None and m.group(0).startswith("Waiting"):
            # Lost only if the card is named mmcblk1; a late card may
            # still come
            named = s.wait(r"mmcblk(\d): mmc\d+:\S+ QEMU!", 30)
            if named is not None and named.group(1) == "1":
                check(False, "%s: the card's init reaches the shell (lost "
                      "its root: the card is mmcblk1, the vendor command "
                      "line says root=/dev/mmcblk0p2; device map gap 22)"
                      % what)
                return "lost"
            m = s.wait(firmware.READY, BOOT_TIMEOUT)
        if not check(m is not None and m.group(1) == "/dev/mmcblk0p2",
                     "%s: the card's init reaches the shell on "
                     "/dev/mmcblk0p2" % what):
            return "fail"
        return "ok"
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    results = [boot(os.path.join(out, "boot%d" % n), n)
               for n in range(1, BOOTS + 1)]
    ok, lost = results.count("ok"), results.count("lost")
    print()
    if ok == BOOTS:
        print("VENDOR-DEFAULT COMPATIBILITY: PASS (%d of %d boots found "
              "their root)" % (ok, BOOTS))
        return 0
    print("VENDOR-DEFAULT COMPATIBILITY: FAIL (%d of %d boots lost their "
          "root to the SD name race, %d failed otherwise; device map "
          "gap 22)" % (lost, BOOTS, BOOTS - ok - lost))
    return 1


if __name__ == "__main__":
    sys.exit(main())
