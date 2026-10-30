#!/usr/bin/env bash
# Build the SD card image for the storage acceptance run: 64 MiB (a
# power of two, as QEMU's SD card model requires up to 2 GiB), an MS-DOS
# partition table with one Linux partition from sector 2048, and an
# ext4 file system holding one known file. No root rights: the file
# system is made with mkfs.ext4 -d in a separate file and copied in.
# Output: ../out/sd/sd.img (prints its partition table).
# Host tools: sfdisk (util-linux), mkfs.ext4 (e2fsprogs).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../out/sd"
SIZE=$((64 * 1024 * 1024))
START=2048

mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/root"
echo "rzv2l-smarc SD card image (tests/guests/sd/build-image.sh)" \
    > "$work/root/README"

rm -f "$OUT/sd.img"
truncate -s "$SIZE" "$OUT/sd.img"
printf 'label: dos\nstart=%d, type=83\n' "$START" | sfdisk -q "$OUT/sd.img"
truncate -s $((SIZE - START * 512)) "$work/p1.img"
mkfs.ext4 -q -F -L rzv2l-sd -d "$work/root" "$work/p1.img"
dd if="$work/p1.img" of="$OUT/sd.img" bs=512 seek="$START" conv=notrunc \
    status=none
sfdisk -l "$OUT/sd.img"
