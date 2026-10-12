#!/usr/bin/env bash
# M1-T05: build the probe and run it on rzv2l-smarc.
# Exit status: 0 when every check passes, 1 on a failed check,
# 2 when the probe produced no result (crash, hang, no semihosting).
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
# Semihosting output arrives on QEMU's stderr; it is merged into out/probe.log.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
make -s -C "$HERE" || exit 2

timeout 20 "$QEMU" -M rzv2l-smarc -kernel "$HERE/out/probe.Image" \
    -semihosting-config enable=on,target=native \
    -display none -nodefaults \
    -d unimp,guest_errors,invalid_mem -D "$HERE/out/qemu.log" \
    "$@" 2>&1 | tee "$HERE/out/probe.log"
status=${PIPESTATUS[0]}

if ! grep -q '^RESULT: ' "$HERE/out/probe.log"; then
    echo "run.sh: no RESULT line (QEMU status $status): probe did not finish" >&2
    exit 2
fi
echo "run.sh: QEMU status $status; QEMU log in out/qemu.log"
exit "$status"
