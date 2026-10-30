#!/usr/bin/env bash
# M4 acceptance for rzv2l-smarc: the Renesas vendor kernel (G1) and its
# device tree boot to a BusyBox shell on ttySC0, and the watchdog (WDT0)
# refreshes, stops and resets the board (docs/units/M4-vendor-kernel/spec.md);
# QEMU's loader makes U-Boot's device-tree edits (docs/units/M4-loader-fixups).
# Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
SHELL_PY="$HERE/../m3/shell.py"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

# M3 acceptance, which runs M2 and M1 first: G0 still boots to a shell
step "M3 acceptance"
"$HERE/../m3/run.sh" > "$OUT/m3.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M3 acceptance (full output: out/m3.txt)"
else
    echo "FAIL M3 acceptance (full output: out/m3.txt)"; result 1
fi

# The device-tree edits made in place of U-Boot
step "loader fixups"
"$HERE/loader-fixups.sh" > "$OUT/loader-fixups.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS loader fixups (full output: out/loader-fixups.txt)"
else
    echo "FAIL loader fixups (full output: out/loader-fixups.txt)"; result 1
fi

# G1 to a shell on two cold boots; the watchdog checks on the first
step "G1 shell and watchdog, cold boot 1"
python3 -I "$SHELL_PY" "$OUT/boot1" --tier g1 --watchdog
result $?
step "G1 shell, cold boot 2"
python3 -I "$SHELL_PY" "$OUT/boot2" --tier g1
result $?

# Log gate: every -d line is an access to a stub window the device map
# records; an empty log fails
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
    echo "M4 ACCEPTANCE: PASS"
else
    echo "M4 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
