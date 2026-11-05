#!/usr/bin/env python3
"""Read and write the vendor U-Boot's saved environment on an SD card image.

Usage:
  uboot-env.py write IMAGE ENVFILE [ENVFILE ...] [NAME=VALUE ...]
  uboot-env.py clear IMAGE
  uboot-env.py partuuid IMAGE N
  uboot-env.py m9-write IMAGE ENVFILE [ENVFILE ...] [NAME=VALUE ...]
  uboot-env.py m9-read IMAGE
  uboot-env.py m9-damage IMAGE COPY

The vendor U-Boot (renesas-u-boot-cip 4eebfbaa4e, smarc-rzv2l_defconfig)
keeps its environment on mmc 0, the module slot, as raw bytes outside
any partition: CONFIG_ENV_IS_IN_MMC, CONFIG_SYS_MMC_ENV_DEV=0,
CONFIG_ENV_OFFSET=0x1F0000, CONFIG_ENV_SIZE=0x20000, one copy (no
CONFIG_SYS_REDUNDAND_ENVIRONMENT). The block is a little-endian CRC-32
of the data area, then NAME=VALUE strings, each ended by a NUL, an
empty string at the end, zero padding. When the CRC does not match,
U-Boot uses its built-in default environment. This is what U-Boot's
`saveenv` would write; nothing in U-Boot changes.

write: the environment from each ENVFILE in turn (one NAME=VALUE per
       line; blank lines and lines starting with # are skipped; a later
       file replaces or adds), then each NAME=VALUE argument. In values, @PARTUUID-N@
       becomes this image's own PARTUUID of partition N.
clear: zero the block, so U-Boot falls back to its default environment
       (the vendor's unchanged boot).
write refuses an environment whose boot command sets a bootargs that the
vendor's in-place append of " wdt_overflow=N" at booti (strcat,
arch/arm/lib/bootm.c:208) would carry past the end of its heap
allocation (strdup of the value, lib/hashtable.c; dlmalloc chunks of
16 bytes with an 8-byte header, common/dlmalloc.c request2size).
m9-*: the M9 profile's U-Boot (docs/decisions/DR-0008; its effective
       configuration ../out/m9/u-boot.config) keeps two copies, at
       0x1F0000 and CONFIG_ENV_OFFSET_REDUND 0x210000, 128 KiB each. A
       copy is a CRC-32 of its data, a flag byte, then the data
       (include/env_internal.h env_t); U-Boot uses the valid copy with
       the higher flag (env/common.c env_import_redund). m9-write writes
       both copies, flags 1 and 0; m9-read prints, per copy, whether its
       CRC holds, its flag and the variables named BOOT_* and M9_*;
       m9-damage COPY (1 or 2) changes one byte of that copy's data, so
       its CRC fails. Partition 1 must start at or above 0x400000.
partuuid: print the Linux PARTUUID of partition N of an MS-DOS
       partition table: the disk identifier (MBR bytes 440-443,
       little-endian) as 8 hex digits, a dash, N as 2 hex digits
       (Linux block/partitions/msdos.c).
"""
import os
import re
import struct
import sys
import zlib

ENV_OFFSET = 0x1F0000
ENV_SIZE = 0x20000
UBOOT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "out", "fw", "u-boot.config")


def die(msg):
    sys.exit("uboot-env.py: " + msg)


def check_config():
    """The block's place must match the effective U-Boot configuration"""
    if not os.path.exists(UBOOT_CONFIG):
        return
    cfg = open(UBOOT_CONFIG).read()
    want = {"CONFIG_ENV_IS_IN_MMC": "y", "CONFIG_SYS_MMC_ENV_DEV": 0,
            "CONFIG_ENV_OFFSET": ENV_OFFSET, "CONFIG_ENV_SIZE": ENV_SIZE}
    for name, value in want.items():
        m = re.search(r"^%s=(\S+)$" % name, cfg, re.M)
        got = None if m is None else m.group(1)
        if got is not None and value != "y":
            got = int(got, 0)
        if got != value:
            die("%s is not %s in %s" % (name, value, UBOOT_CONFIG))
    if re.search(r"^CONFIG_SYS_REDUNDAND_ENVIRONMENT=y$", cfg, re.M):
        die("the U-Boot build keeps two environment copies")


def disk_id(image):
    with open(image, "rb") as f:
        mbr = f.read(512)
    if len(mbr) < 512 or mbr[510:512] != b"\x55\xaa":
        die("%s has no MS-DOS partition table" % image)
    return struct.unpack_from("<I", mbr, 440)[0]


def partuuid(image, n):
    return "%08x-%02x" % (disk_id(image), n)


APPEND = len(" wdt_overflow=0")


def check_bootargs(env):
    """The vendor's append must fit bootargs' allocation"""
    for value in env.values():
        for m in re.finditer(r'setenv bootargs "([^"]*)"', value):
            args = re.sub(r"\$\{(\w+)\}", lambda v: env.get(v.group(1), ""),
                          m.group(1))
            usable = ((len(args) + 1 + 8 + 15) & ~15) - 8
            if usable < len(args) + APPEND + 1:
                die("bootargs of %d characters: the vendor's append of %d "
                    "overruns its %d-byte allocation; pad it with spaces"
                    % (len(args), APPEND, usable))


def check_free(image):
    """No partition may overlap the environment block"""
    with open(image, "rb") as f:
        mbr = f.read(512)
    for i in range(4):
        _, _, _, _, ptype, _, _, _, start, count = struct.unpack_from(
            "<BBBBBBBBII", mbr, 446 + 16 * i)
        if ptype and start * 512 < ENV_OFFSET + ENV_SIZE and \
                (start + count) * 512 > ENV_OFFSET:
            die("partition %d overlaps U-Boot's environment block" % (i + 1))


def write(image, envfiles, overrides):
    check_config()
    check_free(image)
    env = {}
    for envfile in envfiles:
        for line in open(envfile):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if not sep:
                die("%s: not NAME=VALUE: %s" % (envfile, line))
            env[name] = value
    for arg in overrides:
        name, sep, value = arg.partition("=")
        if not sep:
            die("not NAME=VALUE: %s" % arg)
        env[name] = value
    for name in env:
        env[name] = re.sub(r"@PARTUUID-(\d+)@",
                           lambda m: partuuid(image, int(m.group(1))),
                           env[name])
    check_bootargs(env)
    data = b"".join(("%s=%s" % kv).encode() + b"\0"
                    for kv in sorted(env.items())) + b"\0"
    if len(data) > ENV_SIZE - 4:
        die("environment too large")
    data = data.ljust(ENV_SIZE - 4, b"\0")
    block = struct.pack("<I", zlib.crc32(data)) + data
    with open(image, "r+b") as f:
        f.seek(ENV_OFFSET)
        f.write(block)


M9_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "out", "m9", "u-boot.config")
M9_COPIES = (0x1F0000, 0x210000)
M9_P1_MIN = 0x400000


def m9_check(image):
    """The copies' places must match the M9 build, and lie below p1"""
    cfg = open(M9_CONFIG).read()
    want = {"CONFIG_ENV_IS_IN_MMC": "y", "CONFIG_SYS_MMC_ENV_DEV": "0",
            "CONFIG_SYS_REDUNDAND_ENVIRONMENT": "y",
            "CONFIG_ENV_OFFSET": hex(M9_COPIES[0]),
            "CONFIG_ENV_OFFSET_REDUND": hex(M9_COPIES[1]),
            "CONFIG_ENV_SIZE": hex(ENV_SIZE)}
    for name, value in want.items():
        m = re.search(r"^%s=(\S+)$" % name, cfg, re.M)
        got = None if m is None else m.group(1)
        if got is None or (got != value and
                           (value == "y" or int(got, 0) != int(value, 0))):
            die("%s is not %s in %s" % (name, value, M9_CONFIG))
    if M9_COPIES[0] + ENV_SIZE > M9_COPIES[1] or \
            M9_COPIES[1] + ENV_SIZE > M9_P1_MIN:
        die("the environment copies overlap each other or partition 1")
    with open(image, "rb") as f:
        mbr = f.read(512)
    for i in range(4):
        ptype, start = struct.unpack_from("<B3xI", mbr, 446 + 16 * i + 4)
        if ptype and start * 512 < M9_P1_MIN:
            die("partition %d starts below 0x%x" % (i + 1, M9_P1_MIN))


def m9_write(image, envfiles, overrides):
    m9_check(image)
    env = {}
    for envfile in envfiles:
        for line in open(envfile):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if not sep:
                die("%s: not NAME=VALUE: %s" % (envfile, line))
            env[name] = value
    for arg in overrides:
        name, _, value = arg.partition("=")
        env[name] = value
    data = b"".join(("%s=%s" % kv).encode() + b"\0"
                    for kv in sorted(env.items())) + b"\0"
    if len(data) > ENV_SIZE - 5:
        die("environment too large")
    data = data.ljust(ENV_SIZE - 5, b"\0")
    with open(image, "r+b") as f:
        for off, flag in zip(M9_COPIES, (1, 0)):
            f.seek(off)
            f.write(struct.pack("<IB", zlib.crc32(data), flag) + data)


def m9_read(image):
    with open(image, "rb") as f:
        for n, off in enumerate(M9_COPIES, 1):
            f.seek(off)
            block = f.read(ENV_SIZE)
            crc, flag = struct.unpack_from("<IB", block)
            data = block[5:]
            ok = zlib.crc32(data) == crc
            names = [v.decode(errors="replace") for v in data.split(b"\0")
                     if v.startswith((b"BOOT_", b"M9_"))] if ok else []
            print("copy %d: %s flag %d %s" % (n, "valid" if ok else "invalid",
                                              flag, " ".join(names)))


def m9_damage(image, copy):
    with open(image, "r+b") as f:
        f.seek(M9_COPIES[copy - 1] + 5)
        b = f.read(1)
        f.seek(M9_COPIES[copy - 1] + 5)
        f.write(bytes([b[0] ^ 0xFF]))


def clear(image):
    check_free(image)
    with open(image, "r+b") as f:
        f.seek(ENV_OFFSET)
        f.write(b"\0" * ENV_SIZE)


def main(argv):
    if len(argv) >= 3 and argv[0] == "write":
        files = [a for a in argv[2:] if "=" not in a]
        write(argv[1], files, [a for a in argv[2:] if "=" in a])
    elif len(argv) == 2 and argv[0] == "clear":
        clear(argv[1])
    elif len(argv) >= 3 and argv[0] == "m9-write":
        files = [a for a in argv[2:] if "=" not in a]
        m9_write(argv[1], files, [a for a in argv[2:] if "=" in a])
    elif len(argv) == 2 and argv[0] == "m9-read":
        m9_read(argv[1])
    elif len(argv) == 3 and argv[0] == "m9-damage" and argv[2] in "12":
        m9_damage(argv[1], int(argv[2]))
    elif len(argv) == 3 and argv[0] == "partuuid":
        print(partuuid(argv[1], int(argv[2])))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
