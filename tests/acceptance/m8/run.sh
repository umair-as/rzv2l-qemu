#!/usr/bin/env bash
# M8 acceptance for rzv2l-smarc: the board's TF-A BL2 from the QSPI flash
# in boot mode 3, with the machine standing in for the boot ROM
# (docs/units/M8-bl2-staging/spec.md); M7 acceptance first (which runs
# M6 to M1). BL2 sets up the DDR, reads the FIP and starts BL31; then
# BL31, OP-TEE and U-Boot from that FIP boot Linux from the SD card
# (docs/units/M8-full-chain/spec.md).
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

step "BL2 from the QSPI flash: banner, DDR set-up to Booting BL31, the boot ROM stand-in's errors"
python3 -I "$HERE/bl2.py" "$OUT/bl2"
result $?

step "the chain from the flash: BL2 loads BL31, OP-TEE and U-Boot from the FIP; Linux, OP-TEE from Linux, boot mode 4, FIP negatives"
python3 -I "$HERE/chain.py" "$OUT/chain"
result $?

# Log gate: every -d line of a chain run is a recorded stub window, one of
# BL2's lines or a line of the chain's own list
step "log gate"
allow=$(cat "$HERE/../m4/expected/log-allow.txt" \
            "$HERE/../m5/expected/log-allow.txt" \
            "$HERE/expected/log-allow.txt" \
            "$HERE/expected/log-allow-chain.txt" | grep -v -e '^#' -e '^$')
for run in chain mode4 tee; do
    log="$OUT/chain/$run/qemu.log"
    if [ ! -s "$log" ]; then
        echo "FAIL $run/qemu.log: missing or empty"; result 1
        continue
    fi
    bad=$(grep -v -E -f <(echo "$allow") "$log" | sort -u)
    if [ -z "$bad" ]; then
        echo "PASS $run/qemu.log: only recorded stub windows and listed lines"
    else
        echo "FAIL $run/qemu.log: lines outside the allow list:"
        echo "$bad" | head -10 | sed 's/^/    /'
        result 1
    fi
done

echo
if [ "$failures" -eq 0 ]; then
    echo "M8 ACCEPTANCE: PASS"
else
    echo "M8 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
