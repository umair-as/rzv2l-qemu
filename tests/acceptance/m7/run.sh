#!/usr/bin/env bash
# M7 acceptance for rzv2l-smarc: the board's TF-A BL31 as the PSCI
# firmware, in firmware mode (-bios), with the Renesas kernel (G1) and
# the root file system on the SD card (docs/units/M7-el3-platform/spec.md);
# M5 acceptance first (which runs M4 to M1 in direct mode).
# Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
# Guests: tests/guests/out (BL31: tests/guests/fw/build-tf-a.sh).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

step "M5 acceptance"
"$HERE/../m5/run.sh" > "$OUT/m5.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M5 acceptance (full output: out/m5.txt)"
else
    echo "FAIL M5 acceptance (full output: out/m5.txt)"; result 1
fi

step "firmware mode: BL31, G1 kernel, root on the SD card"
python3 -I "$HERE/firmware.py" "$OUT/firmware"
result $?

step "EL3 probe: GICR_PWRR and TZC access by security state"
"$HERE/../../probes/el3-secure/run.sh" > "$OUT/el3-secure.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS EL3 probe (full output: out/el3-secure.txt)"
else
    echo "FAIL EL3 probe (full output: out/el3-secure.txt)"; result 1
fi

# Log gate: every -d line is a recorded stub window or a listed line
step "log gate"
allow=$(cat "$HERE/../m4/expected/log-allow.txt" \
            "$HERE/../m5/expected/log-allow.txt" | grep -v -e '^#' -e '^$')
log="$OUT/firmware/qemu.log"
if [ ! -s "$log" ]; then
    echo "FAIL firmware/qemu.log: missing or empty"; result 1
else
    bad=$(grep -v -E -f <(echo "$allow") "$log" | sort -u)
    if [ -z "$bad" ]; then
        echo "PASS firmware/qemu.log: only recorded stub windows and listed lines"
    else
        echo "FAIL firmware/qemu.log: lines outside the allow list:"
        echo "$bad" | head -10 | sed 's/^/    /'
        result 1
    fi
fi

echo
if [ "$failures" -eq 0 ]; then
    echo "M7 ACCEPTANCE: PASS"
else
    echo "M7 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
