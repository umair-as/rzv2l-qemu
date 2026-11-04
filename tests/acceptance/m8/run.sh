#!/usr/bin/env bash
# M8 acceptance for rzv2l-smarc: the board's TF-A BL2 from the QSPI flash
# in boot mode 3, with the machine standing in for the boot ROM
# (docs/units/M8-bl2-staging/spec.md); M7 acceptance first (which runs
# M6 to M1). BL2 runs to its DDR set-up, the next unit's work.
# Exit 0 only if every check passes ("M8 ACCEPTANCE").
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
# Guests: tests/guests/out (tests/guests/fw/build-tf-a.sh,
# build-optee.sh, build-u-boot.sh, then build-spi-image.sh), and those of
# the M7 run.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

step "M7 acceptance"
"$HERE/../m7/run.sh" > "$OUT/m7.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M7 acceptance (full output: out/m7.txt)"
else
    echo "FAIL M7 acceptance (full output: out/m7.txt)"; result 1
fi

step "BL2 from the QSPI flash: banner, the stop at the DDR set-up, the boot ROM stand-in's errors"
python3 -I "$HERE/bl2.py" "$OUT/bl2"
result $?

echo
if [ "$failures" -eq 0 ]; then
    echo "M8 ACCEPTANCE: PASS"
else
    echo "M8 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
