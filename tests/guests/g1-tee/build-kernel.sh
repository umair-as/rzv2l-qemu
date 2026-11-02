#!/usr/bin/env bash
# Build the project's TEE kernel (DR-0006): the G1 vendor kernel source at
# the same pinned commit as ../g1/build-kernel.sh, its own arm64 defconfig
# plus tee.config (CONFIG_TEE, CONFIG_OPTEE), and its own DTB with the
# /firmware/optee node of optee.dtso applied as an overlay. The kernel
# source is not changed.
# Source: as ../g1/build-kernel.sh ($LINUX_SRC or ../dl/rz_linux-cip-<commit>).
# Output: ../out/g1-tee/linux/arch/arm64/boot/Image and
# ../out/g1-tee/r9a07g054l2-smarc.dtb; prints their SHA-256 and the
# effective TEE options.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
COMMIT=212f6e88b7249f803ff5475c07b72c92ce2d929d
SRC="${LINUX_SRC:-$HERE/../dl/rz_linux-cip-${COMMIT:0:10}}"
OUT="$HERE/../out/g1-tee"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
DTB=renesas/r9a07g054l2-smarc.dtb

[ -d "$SRC" ] || { echo "build-kernel.sh: no $SRC; run ../g1/build-kernel.sh first" >&2; exit 1; }
got=$(git -C "$SRC" rev-parse HEAD)
[ "$got" = "$COMMIT" ] || { echo "build-kernel.sh: $SRC is at $got, expected $COMMIT" >&2; exit 1; }
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] || {
    echo "build-kernel.sh: $SRC has local changes; use a clean checkout" >&2; exit 1; }

mkdir -p "$OUT/linux"
make -s -C "$SRC" O="$OUT/linux" ARCH=arm64 CROSS_COMPILE="$CROSS" defconfig
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT/linux" \
    "$OUT/linux/.config" "$HERE/tee.config" > /dev/null
make -s -C "$SRC" O="$OUT/linux" ARCH=arm64 CROSS_COMPILE="$CROSS" olddefconfig
make -s -C "$SRC" O="$OUT/linux" ARCH=arm64 CROSS_COMPILE="$CROSS" \
    -j"$(nproc)" Image "$DTB"
dtc -q -@ -I dts -O dtb -o "$OUT/optee.dtbo" "$HERE/optee.dtso"
fdtoverlay -i "$OUT/linux/arch/arm64/boot/dts/$DTB" -o "$OUT/r9a07g054l2-smarc.dtb" \
    "$OUT/optee.dtbo"
(cd "$OUT" && sha256sum linux/arch/arm64/boot/Image r9a07g054l2-smarc.dtb)
# The effective configuration and the node (AGENTS.md rule 3)
grep -E '^CONFIG_(TEE|OPTEE)=' "$OUT/linux/.config"
fdtget "$OUT/r9a07g054l2-smarc.dtb" /firmware/optee compatible
