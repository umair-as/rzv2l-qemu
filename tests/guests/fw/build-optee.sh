#!/usr/bin/env bash
# Build OP-TEE OS (BL32) for the RZ/V2L SMARC EVK from the Renesas sources,
# at the commit and with the flags of the board's BSP build (G1: the
# Renesas vendor stack), except CFG_RZ_SCE=n: the production build opens
# the closed TSIP crypto engine at boot and panics without it, so the
# emulated chain runs OP-TEE with its software RNG instead (a recorded
# build-configuration gap, not a source patch).
# Source: github.com/renesas-rz/rzg_optee-os, 82a5cd3b (branch 4.8.0/rz),
# cloned once into ../dl.
# SOURCE_DATE_EPOCH is the commit time, so the same sources give the same
# binary.
# Output: ../out/fw/tee-raw.bin, tee.elf and build-optee.txt (the make
# line, the toolchain and the SHA-256 of each output).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
URL=https://github.com/renesas-rz/rzg_optee-os
REV=82a5cd3b26ed319e8fa72b305462a78417d68daa
DL="$HERE/../dl"
SRC="$DL/rzg_optee-os"
OUT="$HERE/../out/fw"
B="$DL/optee-build"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
FLAGS=(PLATFORM=rz PLATFORM_FLAVOR=g2l_smarc_2 CFG_ARM64_core=y
       CFG_REE_FS=y CFG_RPMB_FS=n CFG_CRYPTO_WITH_CE=n CFG_RZ_SCE=n)

mkdir -p "$DL" "$OUT"
[ -d "$SRC/.git" ] || git clone -q --filter=blob:none "$URL" "$SRC"
git -C "$SRC" checkout -q "$REV"
[ -z "$(git -C "$SRC" status --porcelain)" ] || {
    echo "build-optee.sh: $SRC has local changes" >&2; exit 1; }

rm -rf "$B"
SOURCE_DATE_EPOCH="$(git -C "$SRC" log -1 --format=%ct)" \
make -s -C "$SRC" O="$B" CROSS_COMPILE64="$CROSS" "${FLAGS[@]}" \
    -j"$(nproc)" all
cp "$B/core/tee-raw.bin" "$B/core/tee.elf" "$OUT/"
{
    echo "source: $URL $(git -C "$SRC" rev-parse HEAD)"
    echo "make: CROSS_COMPILE64=$CROSS ${FLAGS[*]}"
    echo "toolchain: $("${CROSS}gcc" --version | head -1)"
    (cd "$OUT" && sha256sum tee-raw.bin tee.elf)
} > "$OUT/build-optee.txt"
cat "$OUT/build-optee.txt"
