#!/usr/bin/env bash
# Write the QSPI flash image the SMARC module boots from in boot mode 3
# (1.8 V serial flash): what the board's flash holds when it boots TF-A
# from QSPI, laid out as TF-A f59ed5a31 reads it (docs/research/bl2.md
# section 2):
#   0x00000  boot parameter block (512 bytes, TF-A's bptool: BL2's size,
#            load offset 0x200, destination 0x12000, signature 0xAA55)
#   0x00200  bl2.bin
#   0x20000  fip.bin: BL31 (soc-fw), OP-TEE tee-raw.bin (tos-fw), U-Boot
#            (nt-fw), made with TF-A's fiptool
#   the rest of the 64 MiB erased (0xFF)
# Inputs: ../out/fw from build-tf-a.sh, build-optee.sh and build-u-boot.sh;
# fiptool from the TF-A source tree build-tf-a.sh builds in.
# Output: ../out/spi/spi.img, fip.bin and build.txt (with --m9:
# spi-m9.img, fip-m9.bin, build-m9.txt) (the commands and the
# SHA-256 of each input and output). The same inputs give the same image.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../out/fw"
OUT="$HERE/../out/spi"
# --m9: the M9 profile's U-Boot as BL33 (build-u-boot-m9.sh), image
# spi-m9.img; everything else as the vendor-default image
BL33="$FW/u-boot.bin"
IMG=spi.img
FIP=fip.bin
LOG=build.txt
if [ "${1:-}" = --m9 ]; then
    BL33="$HERE/../out/m9/u-boot.bin"
    IMG=spi-m9.img
    FIP=fip-m9.bin
    LOG=build-m9.txt
fi
FIPTOOL="$HERE/../dl/rzg_tf-a/tools/fiptool/fiptool"
SIZE=$((64 * 1024 * 1024))
FIP_OFFSET=$((0x20000))
BL2_MAX=$((0x1D000))

for f in "$FW/bp_spi.bin" "$FW/bl2.bin" "$FW/bl31.bin" "$FW/tee-raw.bin" \
         "$BL33" "$FIPTOOL"; do
    [ -e "$f" ] || { echo "build-spi-image.sh: missing $f" >&2; exit 1; }
done
bl2_size=$(stat -c %s "$FW/bl2.bin")
[ "$bl2_size" -le "$BL2_MAX" ] || {
    echo "build-spi-image.sh: bl2.bin is $bl2_size bytes, the boot ROM" \
         "copies at most $BL2_MAX" >&2; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT/$FIP"
"$FIPTOOL" create --align 16 --soc-fw "$FW/bl31.bin" \
    --tos-fw "$FW/tee-raw.bin" --nt-fw "$BL33" "$OUT/$FIP" \
    > /dev/null
fip_size=$(stat -c %s "$OUT/$FIP")
[ $((FIP_OFFSET + fip_size)) -le "$SIZE" ] || {
    echo "build-spi-image.sh: fip.bin does not fit" >&2; exit 1; }

img="$OUT/$IMG.tmp"
head -c "$SIZE" /dev/zero | tr '\000' '\377' > "$img"
dd if="$FW/bp_spi.bin" of="$img" conv=notrunc status=none
dd if="$FW/bl2.bin" of="$img" bs=512 seek=1 conv=notrunc status=none
dd if="$OUT/$FIP" of="$img" bs=4096 seek=$((FIP_OFFSET / 4096)) \
    conv=notrunc status=none
mv "$img" "$OUT/$IMG"

{
    echo "fiptool: create --align 16 --soc-fw bl31.bin --tos-fw tee-raw.bin" \
         "--nt-fw $BL33 $FIP"
    echo "layout: bp_spi.bin @0x0, bl2.bin @0x200, fip.bin @0x20000," \
         "0xFF to $SIZE bytes"
    (cd "$FW" && sha256sum bp_spi.bin bl2.bin bl31.bin tee-raw.bin)
    sha256sum "$BL33" | sed 's:  .*/:  :'
    (cd "$OUT" && sha256sum "$FIP" "$IMG")
} > "$OUT/$LOG"
cat "$OUT/$LOG"
