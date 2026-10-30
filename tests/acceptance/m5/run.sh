#!/usr/bin/env bash
# M5 acceptance for rzv2l-smarc: an ext4 file system on an SD card behind
# the SD/MMC host interface (docs/units/M5-sdhi/spec.md), and user space
# from an ext4 root file system on the card, without an initramfs
# (docs/units/M5-sd-rootfs/spec.md), with the mainline (G0) and the
# Renesas (G1) kernel; M4 acceptance first.
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

# M4 acceptance, which runs M3, M2 and M1 first
step "M4 acceptance"
"$HERE/../m4/run.sh" > "$OUT/m4.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M4 acceptance (full output: out/m4.txt)"
else
    echo "FAIL M4 acceptance (full output: out/m4.txt)"; result 1
fi

# The SD card image, built once
step "SD card image"
"$HERE/../../guests/sd/build-image.sh" > "$OUT/build-image.txt" 2>&1
result $?

for tier in g0 g1; do
    step "storage, $tier"
    python3 -I "$HERE/storage.py" "$OUT/$tier" --tier "$tier"
    result $?
done

for tier in g0 g1; do
    step "root file system on the card, $tier"
    python3 -I "$HERE/rootfs.py" "$OUT/root-$tier" --tier "$tier"
    result $?
done

# Log gate: every -d line is a recorded stub window or a listed line
step "log gate"
allow=$(cat "$HERE/../m4/expected/log-allow.txt" "$HERE/expected/log-allow.txt" |
        grep -v -e '^#' -e '^$')
for log in "$OUT"/g[01]/boot[12]/qemu.log "$OUT"/root-g[01]/boot[12]/qemu.log; do
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
    echo "M5 ACCEPTANCE: PASS"
else
    echo "M5 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
