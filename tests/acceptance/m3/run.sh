#!/usr/bin/env bash
# M3 acceptance for rzv2l-smarc: the G0 kernel boots to a BusyBox shell on
# ttySC0 (docs/units/M3b-shell/spec.md, exit criterion 1-7).
# Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

# 6. M2 acceptance, which runs M1 first
step "M2 acceptance"
"$HERE/../m2/run.sh" > "$OUT/m2.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M2 acceptance (full output: out/m2.txt)"
else
    echo "FAIL M2 acceptance (full output: out/m2.txt)"; result 1
fi

# 1-4 on two cold boots (7)
for boot in 1 2; do
    step "G0 shell, cold boot $boot"
    python3 -I "$HERE/shell.py" "$OUT/boot$boot"
    result $?
done

# 5. Log gate: every -d line is an access to a stub window the device map
#    records (UNIMP, or a write-retaining stub); an empty log fails
step "log gate"
for boot in 1 2; do
    if [ ! -s "$OUT/boot$boot/qemu.log" ]; then
        echo "FAIL boot $boot log: missing or empty"; result 1; continue
    fi
    bad=$(grep -v -E -f <(grep -v -e '^#' -e '^$' "$HERE/expected/log-allow.txt") \
          "$OUT/boot$boot/qemu.log" | sort -u)
    if [ -z "$bad" ]; then
        echo "PASS boot $boot log: only accesses to the recorded stub windows"
    else
        echo "FAIL boot $boot log: lines outside the allow list:"
        echo "$bad" | head -10 | sed 's/^/    /'
        result 1
    fi
done

echo
if [ "$failures" -eq 0 ]; then
    echo "M3 ACCEPTANCE: PASS"
else
    echo "M3 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
