#!/usr/bin/env bash
# M1-T07: build DTB-U, the stock upstream r9a07g054l2-smarc.dtb, from the
# pinned G0 kernel (docs/sources.md). Only the device-tree sources are fetched.
# Output: ../out/g0/r9a07g054l2-smarc.dtb (prints its SHA-256).
# The commands copy kbuild's at the pin: scripts/Makefile.dtbs:91-128 and
# arch/arm64/boot/dts/renesas/Makefile:134-137 (a base DTB for an overlay,
# so kbuild adds -@). The host dtc is used, not the kernel's scripts/dtc.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
TAG=v6.12.59
COMMIT=d5dc97879a97b328a89ec092271faa3db9f2bff3
# DTB-U as built with host DTC 1.7.0 (M1-T07). Another dtc version may give
# other bytes for the same source, so a mismatch is a warning, not an error.
SHA256=4c33990670502cff968ac7f01874c4c80553f939f72f14eac47c0d8662e85620
SRC="$HERE/../dl/linux-$TAG"
OUT="$HERE/../out/g0"
DTS=arch/arm64/boot/dts/renesas/r9a07g054l2-smarc.dts

if [ ! -d "$SRC/.git" ]; then
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$TAG" \
        --filter=blob:none --sparse "$REPO" "$SRC"
    git -C "$SRC" sparse-checkout set \
        arch/arm64/boot/dts include/dt-bindings scripts/dtc/include-prefixes
fi
got=$(git -C "$SRC" rev-parse HEAD)
if [ "$got" != "$COMMIT" ]; then
    echo "build-dtb.sh: $SRC is at $got, expected $COMMIT" >&2
    exit 1
fi
if [ -n "$(git -C "$SRC" status --porcelain)" ]; then
    echo "build-dtb.sh: $SRC has local changes; remove it and run again" >&2
    exit 1
fi

mkdir -p "$OUT"
INC="$SRC/scripts/dtc/include-prefixes"
cc -E -nostdinc -I "$INC" -undef -D__DTS__ -x assembler-with-cpp \
    -o "$OUT/r9a07g054l2-smarc.dts.tmp" "$SRC/$DTS"
dtc -O dtb -o "$OUT/r9a07g054l2-smarc.dtb" -b 0 \
    -i "$(dirname "$SRC/$DTS")" -i "$INC" \
    -Wno-unique_unit_address -Wno-unit_address_vs_reg \
    -Wno-avoid_unnecessary_addr_size -Wno-alias_paths \
    -Wno-graph_child_address -Wno-simple_bus_reg -@ \
    "$OUT/r9a07g054l2-smarc.dts.tmp"
rm -f "$OUT/r9a07g054l2-smarc.dts.tmp"
(cd "$OUT" && sha256sum r9a07g054l2-smarc.dtb)
got=$(sha256sum "$OUT/r9a07g054l2-smarc.dtb" | cut -d' ' -f1)
if [ "$got" != "$SHA256" ]; then
    echo "build-dtb.sh: warning: SHA-256 differs from the recorded $SHA256" \
         "($(dtc --version | head -1))" >&2
fi
