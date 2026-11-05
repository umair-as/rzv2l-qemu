#!/usr/bin/env python3
"""M8 acceptance for rzv2l-smarc: the whole boot chain from the QSPI flash
(docs/units/M8-full-chain/spec.md).

Usage: chain.py OUTDIR

Boot mode 3, no -bios, -kernel, bl32= or bl33=: the machine stands in
for the boot ROM and loads BL2 from a fresh copy of the flash image
tests/guests/out/spi/spi.img; BL2 loads BL31, OP-TEE (BL32) and U-Boot
(BL33) from the firmware package (FIP) at 0x20000 of that image. The SD
card is M7's (a fresh copy, the project's boot configuration). Each run
directory has command.txt and images.sha256 (the images it actually
used). Checks, on the serial line:
  chain:  each run's own command line names no -bios, -kernel, bl32= or
          bl33=; boot 1, in order (each line searched from the end of
          the one before): BL2's banner, SYS_LSI_MODE 0x10003, "Booting
          BL31", the BL31 banner, OP-TEE's banner and its switch to the
          normal world, the U-Boot banner, the environment from mmc 0,
          the kernel read and started; then M7's boot checks (PSCI with
          OP-TEE, the root by PARTUUID, the shell, both CPUs). `reboot`:
          BL31's SYSTEM_RESET, and from the reboot request on the same
          sequence again from BL2's banner, in the same QEMU
  mode 4: boot mode 4 (3.3 V serial flash): BL2 prints SYS_LSI_MODE
          0x10004 and loads the FIP from the flash: BL31 and U-Boot start
  fip:    a flash image whose FIP lacks BL33 (then one lacking BL31):
          BL2 reports the image it cannot load and nothing after it runs
  tee:    M7's Linux and OP-TEE checks (tee.py) on this path, with the
          TEE kernel's card
Writes OUTDIR/<case>/serial.log and qemu.log. Exit 0 only if every check
passes. QEMU binary: $QEMU.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M7 = os.path.join(HERE, "..", "m7")
sys.path.insert(0, M7)
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check, run  # noqa: E402

GUESTS = os.path.join(HERE, "..", "..", "guests")
FLASH = os.path.join(GUESTS, "out", "spi", "spi.img")
FIP = os.path.join(GUESTS, "out", "spi", "fip.bin")
FIPTOOL = os.path.join(GUESTS, "dl", "rzg_tf-a", "tools", "fiptool",
                       "fiptool")
FIP_OFFSET = 0x20000
STAGING = ("-bios", "-kernel", "bl32=", "bl33=")


def bl2(mode):
    return [r"NOTICE:  BL2: v2\.10\.5\(release\):2\.10\.5/rz_1\.1\.0",
            r"NOTICE:  BL2: SYS_LSI_MODE: 0x1000%d\r?$" % mode,
            r"NOTICE:  BL2: Booting BL31"]


def chain(mode):
    """The serial lines from BL2 to the kernel's start, in order"""
    return bl2(mode) + [
        r"NOTICE:  BL31: v2\.10\.5",
        r"I/TC: OP-TEE version: 82a5cd3b",
        r"I/TC: Primary CPU switching to normal world boot",
        r"U-Boot 2024\.07-g4eebfbaa4e",
        bootloader.ENV_OK,
        r"%d bytes read" % os.path.getsize(bootloader.KERNEL),
        r"Starting kernel"]


def in_order(s, patterns, start, what, timeout=90):
    """Each pattern searched from the end of the one before"""
    pos = start
    for p in patterns:
        m = s.wait(p, timeout, pos)
        if not check(m is not None, "%s: in order: %s"
                     % (what, p.replace("\\", "").replace("r?$", ""))):
            return False
        pos = m.end()
    return True


def unstaged(out, what):
    cmd = open(os.path.join(out, "command.txt")).read().split()
    bad = [a for a in cmd if any(a == x or x in a for x in STAGING)]
    check(not bad, "%s: the command line stages nothing%s"
          % (what, "" if not bad else ": " + " ".join(bad)))


def case_chain(out):
    proc, s, log = bootloader.start(out, flash=FLASH)
    try:
        unstaged(out, "chain")
        if not in_order(s, chain(3), 0, "chain boot 1"):
            return
        if not bootloader.boot_checks(s, 0, 1):
            return
        pos = len(s.buf)
        s.send("reboot")
        check(s.wait(r"reboot: Restarting system", 60, pos) is not None,
              "chain: the kernel asks the firmware for a system reset")
        if in_order(s, chain(3), pos, "chain boot 2"):
            bootloader.boot_checks(s, pos, 2)
        check(proc.poll() is None, "chain: the same QEMU, the board reset")
    finally:
        bootloader.stop(proc, log)


def case_mode4(out):
    proc, s, log = bootloader.start(out, flash=FLASH, boot_mode=4)
    try:
        unstaged(out, "mode 4")
        in_order(s, bl2(4) + [r"NOTICE:  BL31: v2\.10\.5",
                              r"U-Boot 2024\.07-g4eebfbaa4e"], 0, "mode 4")
    finally:
        bootloader.stop(proc, log)


def without(out, option):
    """A copy of FLASH whose FIP lacks the image fiptool names option"""
    os.makedirs(out, exist_ok=True)
    fip = os.path.join(out, "fip.bin")
    subprocess.run([FIPTOOL, "remove", option, "--out", fip, FIP],
                   check=True, stdout=subprocess.DEVNULL)
    data = bytearray(open(FLASH, "rb").read())
    old = os.path.getsize(FIP)
    new = open(fip, "rb").read()
    data[FIP_OFFSET:FIP_OFFSET + old] = b"\xff" * old
    data[FIP_OFFSET:FIP_OFFSET + len(new)] = new
    img = os.path.join(out, "source.img")
    open(img, "wb").write(data)
    return img


def case_fip(out, option, image_id, absent):
    what = "fip without %s" % option
    proc, s, log = bootloader.start(out, flash=without(out, option))
    try:
        unstaged(out, what)
        m = s.wait(r"ERROR:\s+BL2: Failed to load image id %d \(" % image_id,
                   60)
        check(m is not None, "%s: BL2 cannot load image id %d"
              % (what, image_id))
        if m is not None:
            late = [a for a in absent if s.wait(a, 5, 0)]
            check(not late, "%s: nothing after it runs%s"
                  % (what, "" if not late else ": " + "; ".join(late)))
    finally:
        bootloader.stop(proc, log)


def case_tee(out):
    import tee  # sets the TEE kernel and its card in bootloader
    proc, s, log = bootloader.start(out, flash=FLASH)
    try:
        unstaged(out, "tee")
        if in_order(s, chain(3), 0, "tee") and \
                bootloader.boot_checks(s, 0, 1):
            run(s, "watchdog -T 10 -t 2 /dev/watchdog0")
            tee.tee_checks(s)
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    for f in (FLASH, FIP, FIPTOOL):
        if not os.path.exists(f):
            print("FAIL missing %s (tests/guests/fw/build-spi-image.sh)" % f)
            return 1
    for d in ("chain", "mode4", "fip-bl33", "fip-bl31", "tee"):
        shutil.rmtree(os.path.join(out, d), ignore_errors=True)
    case_chain(os.path.join(out, "chain"))
    case_mode4(os.path.join(out, "mode4"))
    case_fip(os.path.join(out, "fip-bl33"), "--nt-fw", 5,
             [r"NOTICE:  BL2: Booting BL31", r"U-Boot 20"])
    case_fip(os.path.join(out, "fip-bl31"), "--soc-fw", 3,
             [r"NOTICE:  BL2: Booting BL31", r"NOTICE:  BL31"])
    case_tee(os.path.join(out, "tee"))
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
