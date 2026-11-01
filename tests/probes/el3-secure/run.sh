#!/usr/bin/env bash
# Build the EL3 secure-access probe and run it on rzv2l-smarc in firmware
# mode: the probe is -bios (entered at EL3 by the machine's BL2 stub) and
# also -kernel, which firmware mode requires and the probe never enters;
# -dtb is the Renesas kernel's DTB (tests/guests/g1), likewise unused.
# Exit status: 0 when every check passes, 1 on a failed check, 2 when the
# probe produced no result (crash, hang, no semihosting).
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
DTB="$HERE/../../guests/out/g1/r9a07g054l2-smarc.dtb"
make -s -C "$HERE" || exit 2
[ -f "$DTB" ] || { echo "run.sh: missing $DTB (tests/guests/g1)" >&2; exit 2; }

timeout 20 "$QEMU" -M rzv2l-smarc \
    -bios "$HERE/out/probe.bin" -kernel "$HERE/out/probe.bin" -dtb "$DTB" \
    -semihosting-config enable=on,target=native \
    -display none -nodefaults \
    -d unimp,guest_errors,invalid_mem -D "$HERE/out/qemu.log" \
    "$@" 2>&1 | tee "$HERE/out/probe.log"
status=${PIPESTATUS[0]}

if ! grep -q '^RESULT: ' "$HERE/out/probe.log"; then
    echo "run.sh: no RESULT line (QEMU status $status): probe did not finish" >&2
    exit 2
fi
exit "$status"
