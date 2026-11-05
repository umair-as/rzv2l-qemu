#!/usr/bin/env python3
"""M7 acceptance for rzv2l-smarc: BL31, OP-TEE and U-Boot from the board.

Usage: bootloader.py OUTDIR

Firmware mode with the vendor boot chain after BL2, unmodified (G1):
-bios tests/guests/out/fw/bl31.bin (TF-A f59ed5a31), bl32= OP-TEE
82a5cd3b built with CFG_RZ_SCE=n (tee-raw.bin), bl33= U-Boot 4eebfbaa4e
smarc-rzv2l_defconfig (u-boot.bin); a fresh copy of the SD card image in
the module slot, with the Renesas kernel (G1) and its DTB in /boot of
the root partition. QEMU stands in for BL2 only. U-Boot reads the
project's boot configuration from the card's environment block
(tests/guests/sd/boot.env, DR-0007): ext4load from mmc 0:2, then booti
with root=PARTUUID=<the card's partition 2>. Checks, on the serial
line:
  boot 1: the BL31 banner; OP-TEE's banner and its switch to the normal
          world; the U-Boot banner and 1.9 GiB of DRAM; U-Boot loads the
          project's environment from mmc 0; U-Boot reads the kernel
          from the card and starts it; the kernel finds PSCI 1.1,
          SMCCC 1.4 and BL31's answer with OP-TEE up ("Trusted OS
          migration not required", as on the board); the card's init
          reaches the shell, with / the partition the command line
          names by PARTUUID, whatever name Linux gives the card; CPU1 boots through BL31 and OP-TEE: both
          CPUs online
  hotplug: CPU1 offline and online again, twice, through BL31 and OP-TEE
  watchdog not fed: U-Boot leaves WDT0 running with 60 s; nothing feeds
          it, Linux stops its clock, and the board does not reset for
          75 s, as on the board (EVK-L14)
  watchdog fed: with BusyBox
          `watchdog` feeding /dev/watchdog0, the board does not reset
          for 75 s
  reset:  `reboot`: BL31's SYSTEM_RESET; boot 2 through the whole chain
          in the same QEMU, with both CPUs online
The vendor device tree has no mmc aliases, so Linux names the card
mmcblk0 or mmcblk1 in probe order (docs/device-map.md, gap 22); the
PARTUUID does not depend on it. If the kernel cannot find the PARTUUID,
it stops after rootwait=30 with "VFS: Unable to mount root fs": a FAIL
that names the PARTUUID. The vendor's own default command is
compat.py's.
Writes OUTDIR/serial.log and qemu.log. Exit 0 only if every check
passes. QEMU binary: $QEMU.
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
import firmware  # noqa: E402
from firmware import check, run, online, CPU1  # noqa: E402
from shell import Serial  # noqa: E402

FW = os.path.join(HERE, "..", "..", "guests", "out", "fw")
BL31 = os.path.join(FW, "bl31.bin")
BL32 = os.path.join(FW, "tee-raw.bin")
BL33 = os.path.join(FW, "u-boot.bin")
IMAGE = firmware.IMAGE
KERNEL = firmware.KERNEL
SD = os.path.join(HERE, "..", "..", "guests", "sd")
ENV_OK = r"Loading Environment from MMC\.\.\. Reading from MMC\(0\)\.\.\. OK"


def boot_checks(s, start, n):
    """The firmware banners, U-Boot's load, PSCI with OP-TEE, both CPUs"""
    what = "boot %d" % n
    check(s.wait(r"NOTICE:  BL31: v2\.10\.5", 30, start) is not None,
          "%s: the BL31 banner" % what)
    check(s.wait(r"I/TC: Primary CPU switching to normal world boot", 30,
                 start) is not None,
          "%s: OP-TEE initialises and returns to BL31" % what)
    check(s.wait(r"U-Boot 2024\.07-g4eebfbaa4e[^\n]*\n(.*\n)*?DRAM:  1\.9 "
                 r"GiB", 30, start) is not None,
          "%s: the U-Boot banner and DRAM 1.9 GiB" % what)
    check(s.wait(ENV_OK, 30, start) is not None,
          "%s: U-Boot loads the project's environment from mmc 0" % what)
    size = os.path.getsize(KERNEL)
    check(s.wait(r"%d bytes read" % size, 90, start) is not None and
          s.wait(r"Starting kernel", 30, start) is not None,
          "%s: U-Boot reads boot/Image (%d bytes) from the card and starts "
          "it" % (what, size))
    m = firmware.wait_root(s, start, what)
    if m is None:
        return False
    log = s.buf[start:]
    check("psci: PSCIv1.1 detected in firmware" in log and
          "psci: SMC Calling Convention v1.4" in log and
          "psci: Trusted OS migration not required" in log,
          "%s: PSCI 1.1, SMCCC 1.4 and 'Trusted OS migration not "
          "required' (BL31 with OP-TEE)" % what)
    check("opteed" not in log.lower(), "%s: no OP-TEE dispatcher error"
          % what)
    firmware.root_check(s, m, what, n, ROOT or IMAGE)
    check("CPU1: Booted secondary processor 0x0000000100" in log and
          online(s) == "0-1",
          "%s: CPU1 booted through BL31 and OP-TEE; CPUs online 0-1" % what)
    return True


# The card whose partition 2 is the root, when not IMAGE (rootsel.py)
ROOT = None


def card_copy(out, image, slot, env=None):
    """A fresh copy of image for slot (0 module, 1 carrier); env: None
    keeps its environment block, "vendor" clears it, a list of NAME=VALUE
    rewrites it as build-image.sh does (the vendor default environment,
    boot.env), with those changes"""
    img = os.path.join(out, "slot%d-%s" % (slot, os.path.basename(image)))
    shutil.copyfile(image, img)
    tool = os.path.join(SD, "uboot-env.py")
    if env == "vendor":
        subprocess.run([sys.executable, "-I", tool, "clear", img],
                       check=True)
    elif env is not None:
        subprocess.run([sys.executable, "-I", tool, "write", img,
                        os.path.join(FW, "u-boot-initial-env"),
                        os.path.join(SD, "boot.env")] + env, check=True)
    return ["-drive", "if=sd,index=%d,format=raw,file=%s" % (slot, img)]


def start(out, env=None, carrier=None, flash=None, boot_mode=3):
    """Start QEMU with a fresh copy of IMAGE in the module slot (and of
    carrier in the carrier slot); return (proc, serial, log). The
    firmware: BL31, BL32 and BL33 staged by QEMU (-bios, bl32=, bl33=),
    or, with flash, a fresh copy of that QSPI flash image in boot mode
    boot_mode (3 or 4), from which the machine's boot ROM stand-in loads
    BL2 and BL2 the rest (tests/acceptance/m8/chain.py)"""
    fw = (flash,) if flash else (BL31, BL32, BL33)
    for f in fw + (IMAGE, KERNEL) + ((carrier,) if carrier else ()):
        if not os.path.exists(f):
            print("FAIL missing %s (tests/guests/*/build-*.sh)" % f)
            sys.exit(1)
    if carrier and firmware.partuuid(carrier) == firmware.partuuid(IMAGE):
        # Two cards with one disk identifier: the PARTUUID is ambiguous
        print("FAIL %s and %s share the disk identifier %s"
              % (IMAGE, carrier, firmware.partuuid(IMAGE)[:8]))
        sys.exit(1)
    os.makedirs(out, exist_ok=True)
    drives = card_copy(out, IMAGE, 0, env)
    if carrier:
        drives += card_copy(out, carrier, 1)
    sock = os.path.join(out, "serial.sock")
    for f in (sock, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    if flash:
        img = os.path.join(out, "spi.img")
        shutil.copyfile(flash, img)
        firmware_args = ["-M", "rzv2l-smarc,boot-mode=%d" % boot_mode,
                         "-drive", "if=mtd,format=raw,file=" + img]
    else:
        firmware_args = ["-M", "rzv2l-smarc,bl32=%s,bl33=%s" % (BL32, BL33),
                         "-bios", BL31]
    cmd = [os.environ["QEMU"]] + firmware_args + [
           "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           ] + drives + [
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    # The run's own input, before QEMU writes to it: command and images
    with open(os.path.join(out, "command.txt"), "w") as f:
        f.write(" ".join(cmd) + "\n")
    with open(os.path.join(out, "images.sha256"), "w") as f:
        for a in cmd:
            path = a.split("file=")[-1] if "file=" in a else None
            if path and os.path.isfile(path):
                h = hashlib.sha256()
                with open(path, "rb") as g:
                    for b in iter(lambda: g.read(1 << 20), b""):
                        h.update(b)
                f.write("%s  %s\n" % (h.hexdigest(), os.path.basename(path)))
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    return proc, Serial(sock, log), log


def stop(proc, log):
    if proc.poll() is None:
        proc.kill()
    proc.wait()
    log.close()


def main():
    out = sys.argv[1]
    proc, s, log = start(out)
    try:
        if not boot_checks(s, 0, 1):
            return 1

        for i in (1, 2):
            pos = len(s.buf)
            run(s, "echo 0 > " + CPU1)
            check(online(s) == "0" and
                  s.wait(r"psci: CPU1 killed", 10, pos) is not None,
                  "hotplug %d: CPU1 offline: CPUs online 0" % i)
            pos = len(s.buf)
            run(s, "echo 1 > " + CPU1)
            check(online(s) == "0-1" and
                  s.wait(r"CPU1: Booted secondary processor 0x0000000100",
                         10, pos) is not None,
                  "hotplug %d: CPU1 online again: CPUs online 0-1" % i)

        # No reset since boot 1's firmware banner, for 75 s more
        pos = s.buf.find("NOTICE:  BL31: v2") + 1
        check(s.wait(r"NOTICE:  BL31: v2", 75, pos) is None and
              run(s, "true") is not None,
              "watchdog not fed: no reset in 75 s (Linux stopped WDT0's "
              "clock)")

        pos = len(s.buf)
        run(s, "watchdog -T 10 -t 2 /dev/watchdog0")
        check(s.wait(r"NOTICE:  BL31", 75, pos) is None and
              run(s, "true") is not None,
              "watchdog fed: no reset in 75 s, the shell answers")

        pos = len(s.buf)
        s.send("reboot")
        check(s.wait(r"reboot: Restarting system", 60, pos) is not None,
              "reset: the kernel asks the firmware for a system reset")
        boot_checks(s, pos, 2)
        check(proc.poll() is None, "reset: the same QEMU, the board reset")
    finally:
        stop(proc, log)
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
