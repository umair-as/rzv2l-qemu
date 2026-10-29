#!/usr/bin/env bash
# M2-T09 acceptance run for rzv2l-smarc. Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
PROBE_DIR="$HERE/../../probes/hello-rzv2l"
OUT="$HERE/out"
EXP="$HERE/expected"
CHECK="python3 -I $HERE/../m1/check.py"
mkdir -p "$OUT"
failures=0

step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }

# 1. M1 still passes, with the SCIF windows in its mtree/qtree (AC14, A04)
step "M1 acceptance"
"$HERE/../m1/run.sh" > "$OUT/m1.txt" 2>&1
m1=$?
grep -E '^(PASS|FAIL) (mtree|qtree)' "$OUT/m1.txt"
if [ "$m1" -eq 0 ]; then
    echo "PASS M1 acceptance (full output: out/m1.txt)"
else
    echo "FAIL M1 acceptance (full output: out/m1.txt)"; result 1
fi

# 2. The hello probe in direct mode (AC10, AC12, AC13)
step "hello probe"
"$PROBE_DIR/run.sh" > "$OUT/probe.txt" 2>&1
probe=$?
grep -E '^(FAIL|RESULT)' "$OUT/probe.txt"
case "$probe" in
0) echo "PASS probe exited 0: the flush finished, every check passed (A02)" ;;
2) echo "FAIL probe exited 2: no result or the flush timed out (A02)"; result 1 ;;
*) echo "FAIL probe exited $probe (full output: out/probe.txt)"; result 1 ;;
esac

# A01: the greeting on the serial line, exactly; stderr never counts
if cmp -s "$PROBE_DIR/out/serial.log" "$EXP/serial.txt"; then
    echo "PASS serial line carries exactly 'Hello from RZ/V2L' CR LF (A01)"
else
    echo "FAIL serial line differs from expected/serial.txt (A01):"
    od -c "$PROBE_DIR/out/serial.log" | head -5
    result 1
fi

# A03 and A06, from the probe's own check lines
for want in "PASS IRQ INTID: 415" "PASS   ESR.DFSC: 0x0000000000000010"; do
    if grep -qxF "$want" "$OUT/probe.txt"; then
        echo "PASS probe reported '$want'"
    else
        echo "FAIL probe did not report '$want'"; result 1
    fi
done

# 3. The G0 kernel prints through earlycon on SCIF0 (L02), with the
#    unmodified DTB-U and its bootargs plus a bare earlycon (decision (b),
#    device map section 4 row 6). Earlycon prints within the first second;
#    the timeout bounds the run (it ends at the first unmodelled block:
#    the CPG in M2, OSTM after M3b-cpg).
step "G0 kernel earlycon"
KERNEL="$HERE/../../guests/out/g0/linux/arch/arm64/boot/Image"
DTB_U="$HERE/../../guests/out/g0/r9a07g054l2-smarc.dtb"
if [ ! -f "$KERNEL" ] || [ ! -f "$DTB_U" ]; then
    echo "FAIL G0 kernel or DTB-U missing: run tests/guests/g0/build-kernel.sh and build-dtb.sh (L02)"
    result 1
else
    rm -f "$OUT/g0-serial.log"
    timeout 20 "$QEMU" -M rzv2l-smarc -kernel "$KERNEL" -dtb "$DTB_U" \
        -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon" \
        -display none -nodefaults \
        -chardev file,id=scif0,path="$OUT/g0-serial.log" -serial chardev:scif0 \
        -d unimp,guest_errors,invalid_mem -D "$OUT/g0-qemu.log" >/dev/null 2>&1
    for want in "] Linux version 6.12.59 " \
                "] earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')"; do
        if grep -qF "$want" "$OUT/g0-serial.log"; then
            echo "PASS kernel serial has '$want' (L02)"
        else
            echo "FAIL kernel serial lacks '$want' (L02)"; result 1
        fi
    done
fi

# 4. Log gate of the probe run (A05)
step "log gate"
$CHECK log "$PROBE_DIR/out/qemu.log" "$EXP/log-allow.txt"; result $?

echo
if [ "$failures" -eq 0 ]; then
    echo "M2 ACCEPTANCE: PASS"
else
    echo "M2 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
