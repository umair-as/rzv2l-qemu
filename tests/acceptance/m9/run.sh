#!/usr/bin/env bash
# M9 acceptance for rzv2l-smarc: the M9 boot-policy profile
# (docs/decisions/DR-0008) on the whole chain from the QSPI flash: signed
# FIT images (docs/units/M9-fit/spec.md); A/B slots, Linux's commit,
# rollback and damaged environment copies (docs/units/M9-ab/spec.md).
# M8 acceptance first (which runs M7 to M1, and the vendor-default U-Boot
# on the same chain).
# Exit 0 only if every check passes ("M9 ACCEPTANCE").
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
# Guests: those of the M8 run, then tests/guests/fw/build-u-boot-m9.sh,
# build-fit-m9.sh, build-spi-image.sh --m9 and
# tests/guests/sd/build-image-m9.sh.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

step "M8 acceptance"
"$HERE/../m8/run.sh" > "$OUT/m8.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M8 acceptance (full output: out/m8.txt)"
else
    echo "FAIL M8 acceptance (full output: out/m8.txt)"; result 1
fi

step "signed FIT: accepted on slot A; eight refused cases, each to the prompt"
python3 -I "$HERE/fit.py" "$OUT/fit"
result $?

step "A/B slots: selection, a good and a bad update (with a QEMU restart), both slots exhausted, damaged environment copies"
python3 -I "$HERE/ab.py" "$OUT/ab"
result $?

# Log gate: every -d line is a recorded stub window, one of BL2's lines,
# a line of the M8 chain's list or of M9's own
step "log gate"
allow=$(cat "$HERE/../m4/expected/log-allow.txt" \
            "$HERE/../m5/expected/log-allow.txt" \
            "$HERE/../m8/expected/log-allow.txt" \
            "$HERE/../m8/expected/log-allow-chain.txt" \
            "$HERE/expected/log-allow.txt" | grep -v -e '^#' -e '^$')
for log in "$OUT"/fit/*/qemu.log "$OUT"/ab/*/qemu.log "$OUT"/ab/*/*/qemu.log; do
    [ -e "$log" ] || continue
    run=${log#"$OUT"/}; run=${run%/qemu.log}
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
    echo "M9 ACCEPTANCE: PASS"
else
    echo "M9 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
