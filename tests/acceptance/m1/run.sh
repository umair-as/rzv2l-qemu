#!/usr/bin/env bash
# M1-T06 acceptance run for rzv2l-smarc. Exit 0 only when every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
PROBE_DIR="$HERE/../../probes/m1-skeleton"
OUT="$HERE/out"
EXP="$HERE/expected"
CHECK="python3 -I $HERE/check.py"
mkdir -p "$OUT"
failures=0

step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

# 1. The machine is registered (AC01)
step "-M help"
if "$QEMU" -M help | grep -q '^rzv2l-smarc '; then
    echo "PASS -M help lists rzv2l-smarc"
else
    echo "FAIL -M help does not list rzv2l-smarc"; result 1
fi

# 2-4. Monitor views of the paused machine with the probe loaded (AC02, AC07)
make -s -C "$PROBE_DIR" || exit 2
monitor() {
    printf '%s\nquit\n' "$1" | "$QEMU" -M rzv2l-smarc \
        -kernel "$PROBE_DIR/out/probe.Image" -S -display none -nodefaults \
        -monitor stdio 2>&1 | tr -d '\r' | sed 's/\x1b\[[0-9;]*[A-Za-z]//g'
}
step "info mtree -f"
monitor "info mtree -f" > "$OUT/mtree.txt"
$CHECK mtree "$OUT/mtree.txt" "$EXP/mtree.txt"; result $?
step "info qtree"
monitor "info qtree" > "$OUT/qtree.txt"
$CHECK qtree "$OUT/qtree.txt" "$EXP/qtree.txt"; result $?
step "info roms"
monitor "info roms" > "$OUT/roms.txt"
$CHECK roms "$OUT/roms.txt"; result $?

# 5. The guest probe (AC03-AC06, AC13, AC14)
step "guest probe"
"$PROBE_DIR/run.sh" > "$OUT/probe.txt" 2>&1
probe=$?
grep -E '^(FAIL|RESULT)' "$OUT/probe.txt"
if [ "$probe" -eq 0 ]; then
    echo "PASS probe exited 0"
else
    echo "FAIL probe exited $probe (full output: out/probe.txt)"; result 1
fi

# 6. Log gate: -d unimp,guest_errors,invalid_mem of the probe run (REQ-TEST-003)
step "log gate"
$CHECK log "$PROBE_DIR/out/qemu.log" "$EXP/log-allow.txt"; result $?

echo
if [ "$failures" -eq 0 ]; then
    echo "M1 ACCEPTANCE: PASS"
else
    echo "M1 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
