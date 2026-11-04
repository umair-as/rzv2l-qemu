#!/usr/bin/env python3
"""M7 acceptance for rzv2l-smarc: the module's QSPI flash under U-Boot
and Linux (docs/units/M7-rpc-spinor/spec.md).

Usage: flash.py OUTDIR

The boot chain of bootloader.py (BL31, OP-TEE, the vendor U-Boot, the
Renesas kernel from the SD card), with -drive if=mtd holding a 64 MiB
flash image of random bytes made for the run (OUTDIR/flash.img).
Checks, on the serial line:
  U-Boot:  at start, spi-nor detects mt25qu512a, 64 MiB, as the board's
           U-Boot does (EVK-L15), and no JEDEC or SPI slave error; at
           the prompt, `sf probe` again and `sf read` of two regions
           whose crc32 matches the image. U-Boot's board_init rewrites
           the flash's non-volatile configuration register on every
           boot: QEMU's flash trace shows it reads FFFFh (the factory
           value) and writes FFEFh (bit 4 cleared, the others kept)
  Linux:   the flash's sysfs JEDEC ID, part name and SFDP are the
           board's (EVK-L16); /proc/mtd lists bl2, fip and user as on
           the board; mtdblock reads of bl2, fip and user match the
           image; 64 KiB written to user at 1 MiB read back after the
           page cache is dropped
  reboot:  `reboot` restarts the chain in the same QEMU; the written
           block reads back
  restart: a new QEMU with the same image; the written block reads
           back, and the image file holds it
OUTDIR/uboot (U-Boot run, with the flash trace), OUTDIR/linux (Linux
and reboot) and OUTDIR/restart each hold serial.log and qemu.log. Exit
0 only if every check passes. QEMU binary: $QEMU.
"""
import hashlib
import os
import re
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check, run  # noqa: E402
from shell import Serial  # noqa: E402

SIZE = 64 * 1024 * 1024
DETECTED = (r"SF: Detected mt25qu512a with page size 256 Bytes, erase size "
            r"4 KiB, total 64 MiB")
SPI = "/sys/bus/spi/devices/spi1.0/spi-nor"
EXPECTED = os.path.join(HERE, "expected")
# Partitions of the vendor device tree, as /proc/mtd shows them
MTD = ['mtd0: 0001d000 00001000 "bl2"',
       'mtd1: 01fe3000 00001000 "fip"',
       'mtd2: 02000000 00001000 "user"']
USER = 0x2000000
WRITE_AT = 0x100000     # in user
WRITE_LEN = 0x10000


def start(out, flash, trace=None):
    """QEMU with a fresh copy of the SD card and the flash image"""
    os.makedirs(out, exist_ok=True)
    drives = bootloader.card_copy(out, bootloader.IMAGE, 0)
    sock = os.path.join(out, "serial.sock")
    for f in (sock, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    cmd = [os.environ["QEMU"],
           "-M", "rzv2l-smarc,bl32=%s,bl33=%s" % (bootloader.BL32,
                                                   bootloader.BL33),
           "-bios", bootloader.BL31, "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           "-drive", "if=mtd,index=0,format=raw,file=" + flash,
           ] + drives + [
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    for t in trace or ():
        cmd += ["-trace", t]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    return proc, Serial(sock, log), log


def region(flash, off, n):
    with open(flash, "rb") as f:
        f.seek(off)
        return f.read(n)


def md5(s, dev, skip, count):
    """md5 of count 4 KiB blocks of dev from block skip, or None"""
    out = run(s, "dd if=%s bs=4096 skip=%d count=%d 2>/dev/null | md5sum"
              % (dev, skip, count), 120)
    m = re.search(r"^([0-9a-f]{32})  -", out or "", re.M)
    return m.group(1) if m else None


def uboot(out, flash):
    """U-Boot: detection, sf probe/read, the NVCR rewrite"""
    proc, s, log = start(out, flash, ["m25p80_command_decoded",
                                      "m25p80_transfer",
                                      "m25p80_read_data"])
    try:
        stop = s.wait(r"Hit any key to stop autoboot", 60)
        check(s.wait(DETECTED, 1) is not None,
              "U-Boot: spi-nor detects mt25qu512a, 64 MiB")
        head = s.buf
        check("unrecognized JEDEC" not in head and
              "Failed to set up SPI slave" not in head,
              "U-Boot: no JEDEC ID or SPI slave error")
        if not check(stop is not None, "U-Boot: the autoboot countdown"):
            return
        s.send("")
        if not check(s.wait(r"=> $", 10, stop.end()) is not None,
                     "U-Boot: the prompt"):
            return
        pos = len(s.buf)
        s.send("sf probe")
        check(s.wait(DETECTED, 10, pos) is not None,
              "U-Boot: sf probe detects mt25qu512a, 64 MiB")
        for off, n in ((0, 0x1000), (USER, WRITE_LEN)):
            pos = len(s.buf)
            s.send("sf read 0x48000000 0x%x 0x%x; crc32 0x48000000 0x%x"
                   % (off, n, n))
            m = s.wait(r"==> ([0-9a-f]{8})", 30, pos)
            want = "%08x" % zlib.crc32(region(flash, off, n))
            check(m is not None and m.group(1) == want,
                  "U-Boot: sf read of 0x%x bytes at 0x%x: crc32 %s (image "
                  "%s)" % (n, off, m.group(1) if m else "none", want))
    finally:
        bootloader.stop(proc, log)

    # From QEMU's flash trace: the 2 bytes RDNVCR (B5h) returns, and the
    # 2 bytes sent after WRNVCR (B1h); a command byte's transfer line comes
    # before its decode line, so the lines after the decode are its data
    nvcr_read = nvcr_write = None
    cmd, sent, got = None, [], []
    with open(os.path.join(out, "qemu.log")) as f:
        for line in f:
            m = re.search(r"m25p80_command_decoded .*new command:0x"
                          r"([0-9a-f]+)", line)
            if m:
                cmd, sent, got = int(m.group(1), 16), [], []
                continue
            m = re.search(r"m25p80_transfer .* tx 0x([0-9a-f]+)", line)
            if m and cmd == 0xb1:
                sent.append(int(m.group(1), 16))
                if len(sent) == 2:
                    nvcr_write = sent[0] | sent[1] << 8
            m = re.search(r"m25p80_read_data .*=0x([0-9a-f]+)", line)
            if m and cmd == 0xb5:
                got.append(int(m.group(1), 16))
                if len(got) == 2:
                    nvcr_read = got[0] | got[1] << 8

    def h(v):
        return "%04Xh" % v if v is not None else "nothing"
    check(nvcr_read == 0xffff and nvcr_write == 0xffef,
          "U-Boot: reads the non-volatile configuration register as %s "
          "and writes %s (the factory FFFFh with bit 4 cleared)"
          % (h(nvcr_read), h(nvcr_write)))


def linux(out, flash):
    """Linux: ID, SFDP, partitions, reads, a write; then a reboot"""
    proc, s, log = start(out, flash)
    written = None
    try:
        if firmware.wait_root(s, 0, "Linux") is None:
            return None
        r = run(s, "cat %s/jedec_id %s/partname %s/manufacturer"
                % (SPI, SPI, SPI)) or ""
        check(re.search(r"^20bb20104400\r?\nmt25qu512a\r?\nst\r?$", r, re.M)
              is not None,
              "Linux: JEDEC ID 20bb20104400, mt25qu512a, st (EVK-L16)")
        r = run(s, "od -An -tx1 -v %s/sfdp" % SPI) or ""
        want = open(os.path.join(EXPECTED, "sfdp.txt")).read().split()
        got = re.findall(r"^((?: [0-9a-f]{2})+)\r?$", r, re.M)
        check(" ".join(got).split() == want,
              "Linux: SFDP, %d bytes, as the board's part (EVK-L16)"
              % len(" ".join(got).split()))
        r = run(s, "cat /proc/mtd") or ""
        check(all(p in r for p in MTD),
              "Linux: /proc/mtd lists bl2, fip and user as on the board")
        for dev, part_off, skip, n in (("mtdblock0", 0, 0, 16),
                                       ("mtdblock1", 0x1d000, 3, 16),
                                       ("mtdblock2", USER, 0, 16)):
            off = part_off + skip * 4096
            want = hashlib.md5(region(flash, off, n * 4096)).hexdigest()
            check(md5(s, "/dev/" + dev, skip, n) == want,
                  "Linux: %s reads %d KiB at 0x%x as the image"
                  % (dev, n * 4, off))
        r = run(s, "dd if=/dev/urandom of=/tmp/w bs=4096 count=%d "
                "2>/dev/null; md5sum /tmp/w" % (WRITE_LEN // 4096)) or ""
        m = re.search(r"^([0-9a-f]{32})  /tmp/w", r, re.M)
        written = m.group(1) if m else None
        run(s, "dd if=/tmp/w of=/dev/mtdblock2 bs=4096 seek=%d conv=fsync "
            "2>/dev/null; sync; echo 3 > /proc/sys/vm/drop_caches"
            % (WRITE_AT // 4096), 120)
        check(written is not None and
              md5(s, "/dev/mtdblock2", WRITE_AT // 4096,
                  WRITE_LEN // 4096) == written,
              "Linux: 64 KiB written to user at 0x%x read back" % WRITE_AT)

        pos = len(s.buf)
        s.send("reboot")
        ok = (s.wait(r"reboot: Restarting system", 60, pos) is not None and
              firmware.wait_root(s, pos, "reboot") is not None)
        check(ok and proc.poll() is None,
              "reboot: the chain restarts in the same QEMU")
        if ok:
            check(md5(s, "/dev/mtdblock2", WRITE_AT // 4096,
                      WRITE_LEN // 4096) == written,
                  "reboot: the written block reads back")
    finally:
        bootloader.stop(proc, log)
    return written


def restart(out, flash, written):
    """A new QEMU on the same image"""
    off = USER + WRITE_AT
    check(hashlib.md5(region(flash, off, WRITE_LEN)).hexdigest() == written,
          "restart: the image file holds the written block")
    proc, s, log = start(out, flash)
    try:
        if firmware.wait_root(s, 0, "restart") is None:
            return
        check(md5(s, "/dev/mtdblock2", WRITE_AT // 4096,
                  WRITE_LEN // 4096) == written,
              "restart: the written block reads back in a new QEMU")
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    flash = os.path.join(out, "flash.img")
    with open(flash, "wb") as f:
        f.write(os.urandom(SIZE))
    uboot(os.path.join(out, "uboot"), flash)
    written = linux(os.path.join(out, "linux"), flash)
    if written:
        restart(os.path.join(out, "restart"), flash, written)
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
