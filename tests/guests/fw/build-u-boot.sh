#!/usr/bin/env bash
# Build U-Boot (BL33) for the RZ/V2L SMARC EVK from the Renesas sources,
# at the commit and with the defconfig of the board's BSP build (G1: the
# Renesas vendor stack), unmodified.
# Source: github.com/renesas-rz/renesas-u-boot-cip, 4eebfbaa4e (branch
# v2024.07/rz), smarc-rzv2l_defconfig, cloned once into ../dl.
# SOURCE_DATE_EPOCH is the commit time, so the same sources give the same
# binary.
# Output: ../out/fw/u-boot.bin, u-boot (ELF), u-boot.config (the effective
# .config) and build-u-boot.txt (the make line, the toolchain and the
# SHA-256 of each output).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
URL=https://github.com/renesas-rz/renesas-u-boot-cip
REV=4eebfbaa4e61f8d3fa0e44ae59449213ffee981c
DEFCONFIG=smarc-rzv2l_defconfig
DL="$HERE/../dl"
SRC="$DL/renesas-u-boot-cip"
OUT="$HERE/../out/fw"
B="$DL/u-boot-build"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"

mkdir -p "$DL" "$OUT"
[ -d "$SRC/.git" ] || git clone -q --filter=blob:none "$URL" "$SRC"
git -C "$SRC" checkout -q "$REV"
[ -z "$(git -C "$SRC" status --porcelain)" ] || {
    echo "build-u-boot.sh: $SRC has local changes" >&2; exit 1; }

rm -rf "$B"
export SOURCE_DATE_EPOCH="$(git -C "$SRC" log -1 --format=%ct)"
make -s -C "$SRC" O="$B" CROSS_COMPILE="$CROSS" "$DEFCONFIG"
make -s -C "$SRC" O="$B" CROSS_COMPILE="$CROSS" -j"$(nproc)"
cp "$B/u-boot.bin" "$B/u-boot" "$OUT/"
cp "$B/.config" "$OUT/u-boot.config"
{
    echo "source: $URL $(git -C "$SRC" rev-parse HEAD)"
    echo "make: CROSS_COMPILE=$CROSS $DEFCONFIG; all"
    echo "toolchain: $("${CROSS}gcc" --version | head -1)"
    (cd "$OUT" && sha256sum u-boot.bin u-boot)
} > "$OUT/build-u-boot.txt"
cat "$OUT/build-u-boot.txt"
