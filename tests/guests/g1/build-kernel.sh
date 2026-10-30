#!/usr/bin/env bash
# Build the G1 kernel: the Renesas vendor kernel rz_linux-cip at the pinned
# commit (docs/sources.md), with its own in-tree arm64 defconfig, as the
# Renesas BSP recipe does (KBUILD_DEFCONFIG = "defconfig"), and its own
# device tree, DTB-V. Out of tree, unmodified.
# Source: $LINUX_SRC if set (any clean checkout at the pinned commit, for
# example a clone of a local mirror), otherwise a clone into
# ../dl/rz_linux-cip-<commit>.
# Output: ../out/g1/linux/arch/arm64/boot/Image and
# ../out/g1/r9a07g054l2-smarc.dtb; prints their SHA-256.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=https://github.com/renesas-rz/rz_linux-cip.git
BRANCH=rz-6.12-cip14
COMMIT=212f6e88b7249f803ff5475c07b72c92ce2d929d
SRC="${LINUX_SRC:-$HERE/../dl/rz_linux-cip-${COMMIT:0:10}}"
OUT="$HERE/../out/g1"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
DTB=renesas/r9a07g054l2-smarc.dtb

if [ ! -d "$SRC/.git" ] && [ ! -f "$SRC/.git" ]; then
    git -c advice.detachedHead=false clone -q --branch "$BRANCH" \
        "$REPO" "$SRC"
    git -C "$SRC" -c advice.detachedHead=false checkout -q "$COMMIT"
fi
got=$(git -C "$SRC" rev-parse HEAD)
if [ "$got" != "$COMMIT" ]; then
    echo "build-kernel.sh: $SRC is at $got, expected $COMMIT" >&2
    exit 1
fi
if [ -n "$(git -C "$SRC" status --porcelain --untracked-files=no)" ]; then
    echo "build-kernel.sh: $SRC has local changes; use a clean checkout" >&2
    exit 1
fi

mkdir -p "$OUT/linux"
make -s -C "$SRC" O="$OUT/linux" ARCH=arm64 CROSS_COMPILE="$CROSS" defconfig
make -s -C "$SRC" O="$OUT/linux" ARCH=arm64 CROSS_COMPILE="$CROSS" \
    -j"$(nproc)" Image "$DTB"
cp "$OUT/linux/arch/arm64/boot/dts/$DTB" "$OUT/"
(cd "$OUT" && sha256sum linux/arch/arm64/boot/Image r9a07g054l2-smarc.dtb)
# The effective configuration, not the defconfig source (AGENTS.md rule 3)
grep -E '^CONFIG_(SERIAL_SH_SCI|SERIAL_SH_SCI_CONSOLE|RENESAS_RZG2LWDT|BLK_DEV_INITRD|RD_GZIP|DEVTMPFS)=' \
    "$OUT/linux/.config"
