#!/usr/bin/env bash
# M2-T11: build the G0 kernel, the pinned mainline v6.12.59 arm64 defconfig
# Image (docs/sources.md), out of tree, unmodified.
# Source: $LINUX_SRC if set (any clean checkout at the pinned commit),
# otherwise a clone into ../dl/linux-full-$TAG.
# Output: ../out/g0/linux/arch/arm64/boot/Image and ../out/g0/linux/.config;
# prints the Image SHA-256 and the effective console options.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO=https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
TAG=v6.12.59
COMMIT=d5dc97879a97b328a89ec092271faa3db9f2bff3
SRC="${LINUX_SRC:-$HERE/../dl/linux-full-$TAG}"
OUT="$HERE/../out/g0/linux"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"

if [ ! -d "$SRC/.git" ] && [ ! -f "$SRC/.git" ]; then
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$TAG" \
        "$REPO" "$SRC"
fi
got=$(git -C "$SRC" rev-parse HEAD)
if [ "$got" != "$COMMIT" ]; then
    echo "build-kernel.sh: $SRC is at $got, expected $COMMIT" >&2
    exit 1
fi
if [ "$(git -C "$SRC" config --get core.sparseCheckout || true)" = true ]; then
    echo "build-kernel.sh: $SRC is a sparse checkout; use a full one" >&2
    exit 1
fi
if [ -n "$(git -C "$SRC" status --porcelain --untracked-files=no)" ]; then
    echo "build-kernel.sh: $SRC has local changes; use a clean checkout" >&2
    exit 1
fi

mkdir -p "$OUT"
make -s -C "$SRC" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS" defconfig
make -s -C "$SRC" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS" \
    -j"$(nproc)" Image
(cd "$OUT/arch/arm64/boot" && sha256sum Image)
# The effective configuration, not the defconfig source (AGENTS.md rule 3)
grep -E '^CONFIG_(SERIAL_SH_SCI|SERIAL_SH_SCI_CONSOLE|SERIAL_SH_SCI_EARLYCON|ACPI|ACPI_SPCR_TABLE)=' \
    "$OUT/.config"
