#!/usr/bin/env bash
# Build TF-A BL2 and BL31 for the RZ/V2L SMARC EVK from the Renesas
# sources, at the commit and with the flags of the board's BSP build (G1:
# the Renesas vendor stack): PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0.
# Source: github.com/renesas-rz/rzg_trusted-firmware-a, f59ed5a31 (the
# BSP 4.0.1 release tag on 2.10.5/rz_main), cloned once into ../dl.
# BL31 alone runs in QEMU's firmware mode (-bios), where QEMU stages what
# BL2 hands it; BL2, with its boot parameter block for the SPI flash
# (TF-A's bptool), runs from the flash image (build-spi-image.sh, which
# also uses the fiptool built here).
# The banner's build time is replaced by the commit, so the same sources
# give the same binary.
# Output: ../out/fw/bl31.bin, bl31.elf, bl31.map, bl2.bin, bl2.elf,
# bl2.map, bp_spi.bin and build.txt (the make line, the toolchain and the
# SHA-256 of each output); the tools stay in the source tree
# (tools/fiptool/fiptool, tools/renesas/bptool, ignored by its git).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
URL=https://github.com/renesas-rz/rzg_trusted-firmware-a
REV=f59ed5a31
DL="$HERE/../dl"
SRC="$DL/rzg_tf-a"
OUT="$HERE/../out/fw"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
FLAGS=(PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0)

mkdir -p "$DL" "$OUT"
[ -d "$SRC/.git" ] || git clone -q --filter=blob:none "$URL" "$SRC"
git -C "$SRC" checkout -q "$REV"
[ -z "$(git -C "$SRC" status --porcelain)" ] || {
    echo "build-tf-a.sh: $SRC has local changes" >&2; exit 1; }

rm -rf "$SRC/build"
make -s -C "$SRC" CROSS_COMPILE="$CROSS" "${FLAGS[@]}" \
    BUILD_MESSAGE_TIMESTAMP="\"$REV\"" -j"$(nproc)" bl2 bl31 bptool fiptool
B="$SRC/build/v2l/release"
# The SPI boot parameter block, as the platform's "pkg" target makes it
"$SRC/tools/renesas/bptool" "$B/bl2.bin" "$B/bp_spi.bin" 0x00012000 spi \
    > /dev/null
cp "$B/bl31.bin" "$B/bl31/bl31.elf" "$B/bl31/bl31.map" \
   "$B/bl2.bin" "$B/bl2/bl2.elf" "$B/bl2/bl2.map" "$B/bp_spi.bin" "$OUT/"
{
    echo "source: $URL $(git -C "$SRC" rev-parse HEAD)"
    echo "make: CROSS_COMPILE=$CROSS ${FLAGS[*]} bl2 bl31 bptool fiptool"
    echo "bptool: bl2.bin bp_spi.bin 0x00012000 spi"
    echo "toolchain: $("${CROSS}gcc" --version | head -1)"
    (cd "$OUT" && sha256sum bl31.bin bl31.elf bl2.bin bl2.elf bp_spi.bin)
} > "$OUT/build.txt"
cat "$OUT/build.txt"
