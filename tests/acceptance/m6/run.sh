#!/usr/bin/env bash
# M6 acceptance for rzv2l-smarc: Ethernet through the ravb driver, its
# KSZ9131 PHY and the IRQC (docs/units/M6-ravb/spec.md), with the
# mainline (G0) and the Renesas (G1) kernel on QEMU user networking;
# M5 acceptance first. QEMU must be built with slirp.
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

# M5 acceptance, which runs M4 to M1 first
step "M5 acceptance"
"$HERE/../m5/run.sh" > "$OUT/m5.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M5 acceptance (full output: out/m5.txt)"
else
    echo "FAIL M5 acceptance (full output: out/m5.txt)"; result 1
fi

step "user networking"
if "$QEMU" -M none -netdev help 2>/dev/null | grep -qx user; then
    echo "PASS QEMU has the user network backend"
else
    echo "FAIL QEMU has no user network backend (configure with slirp)"
    result 1
fi

for tier in g0 g1; do
    step "network, $tier"
    python3 -I "$HERE/net.py" "$OUT/$tier" --tier "$tier"
    result $?
done

# Log gate: every -d line is a recorded stub window or a listed line
step "log gate"
allow=$(grep -v -e '^#' -e '^$' "$HERE/../m4/expected/log-allow.txt")
for log in "$OUT"/g[01]/qemu.log; do
    name=${log#"$OUT"/}
    if [ ! -s "$log" ]; then
        echo "FAIL $name: missing or empty"; result 1; continue
    fi
    bad=$(grep -v -E -f <(echo "$allow") "$log" | sort -u)
    if [ -z "$bad" ]; then
        echo "PASS $name: only recorded stub windows and listed lines"
    else
        echo "FAIL $name: lines outside the allow list:"
        echo "$bad" | head -10 | sed 's/^/    /'
        result 1
    fi
done

echo
if [ "$failures" -eq 0 ]; then
    echo "M6 ACCEPTANCE: PASS"
else
    echo "M6 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
