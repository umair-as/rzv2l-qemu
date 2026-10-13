#!/usr/bin/env bash
# M1-T06/T07 acceptance run for rzv2l-smarc. Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
PROBE_DIR="$HERE/../../probes/m1-skeleton"
G0_DIR="$HERE/../../guests/g0"
DTB_U="$HERE/../../guests/out/g0/r9a07g054l2-smarc.dtb"
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
    local cmd="$1"; shift
    printf '%s\nquit\n' "$cmd" | "$QEMU" -M rzv2l-smarc "$@" \
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

# 5. The stock upstream DTB passes through with only the listed fixups (AC08)
step "dumpdtb with DTB-U"
"$G0_DIR/build-dtb.sh" > "$OUT/build-dtb.txt" 2>&1 || { cat "$OUT/build-dtb.txt"; exit 2; }
rm -f "$OUT/qemu.dtb"
monitor "dumpdtb $OUT/qemu.dtb" -dtb "$DTB_U" > "$OUT/dumpdtb.txt"
if [ -s "$OUT/qemu.dtb" ]; then
    dtc -q -I dtb -O dts -s -o "$OUT/stock.dts" "$DTB_U"
    dtc -q -I dtb -O dts -s -o "$OUT/qemu.dts" "$OUT/qemu.dtb"
    $CHECK dtb "$OUT/qemu.dts" "$OUT/stock.dts"; result $?
else
    echo "FAIL dumpdtb wrote no DTB (monitor output: out/dumpdtb.txt)"; result 1
fi

# 6. The guest probe (AC03-AC06, AC13, AC14)
step "guest probe"
"$PROBE_DIR/run.sh" > "$OUT/probe.txt" 2>&1
probe=$?
grep -E '^(FAIL|RESULT)' "$OUT/probe.txt"
if [ "$probe" -eq 0 ]; then
    echo "PASS probe exited 0"
else
    echo "FAIL probe exited $probe (full output: out/probe.txt)"; result 1
fi

# 7. Log gate: -d unimp,guest_errors,invalid_mem of the probe run (REQ-TEST-003)
step "log gate"
$CHECK log "$PROBE_DIR/out/qemu.log" "$EXP/log-allow.txt"; result $?

echo
if [ "$failures" -eq 0 ]; then
    echo "M1 ACCEPTANCE: PASS"
else
    echo "M1 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
