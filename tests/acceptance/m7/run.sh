#!/usr/bin/env bash
# M7 acceptance for rzv2l-smarc: the board's TF-A BL31 as the PSCI
# firmware, in firmware mode (-bios), with the Renesas kernel (G1) and
# the root file system on the SD card (docs/units/M7-el3-platform/spec.md);
# then BL31, OP-TEE and U-Boot booting the kernel from the card
# (docs/units/M7-optee-uboot/spec.md); then the project's TEE kernel
# reaching OP-TEE from Linux (docs/units/M7-optee-linux/spec.md). M6
# acceptance first (which runs M5 to M1 in direct mode).
# Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
# Guests: tests/guests/out (tests/guests/fw/build-tf-a.sh, build-optee.sh,
# build-u-boot.sh; tests/guests/g1-tee/build-kernel.sh,
# build-optee-user.sh; the cards: tests/guests/sd/build-image.sh and
# build-image.sh --tee).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
export QEMU
OUT="$HERE/out"
mkdir -p "$OUT"
failures=0
step() { echo "== $*"; }
result() { [ "$1" -eq 0 ] || failures=$((failures + 1)); }
# A failed boot run is kept: out/<run> is overwritten by the next run
keep() {
    [ "$1" -eq 0 ] && return
    dest="$OUT/kept/$(date +%Y%m%d-%H%M%S)-$2"
    mkdir -p "$OUT/kept" && cp -r "$OUT/$2" "$dest"
    echo "     (failed run kept in out/kept/$(basename "$dest"))"
}

step "M6 acceptance"
"$HERE/../m6/run.sh" > "$OUT/m6.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS M6 acceptance (full output: out/m6.txt)"
else
    echo "FAIL M6 acceptance (full output: out/m6.txt)"; result 1
fi

step "firmware mode: BL31, G1 kernel, root on the SD card"
python3 -I "$HERE/firmware.py" "$OUT/firmware"
rc=$?; result $rc; keep $rc firmware

step "boot loader: BL31, OP-TEE, U-Boot, G1 kernel from the SD card"
python3 -I "$HERE/bootloader.py" "$OUT/bootloader"
rc=$?; result $rc; keep $rc bootloader

step "Linux and OP-TEE: TEE kernel, driver, devices, a trusted application"
python3 -I "$HERE/tee.py" "$OUT/tee"
rc=$?; result $rc; keep $rc tee

step "EL3 probe: GICR_PWRR, TZC access by security state, MPIDR"
"$HERE/../../probes/el3-secure/run.sh" > "$OUT/el3-secure.txt" 2>&1
if [ $? -eq 0 ]; then
    echo "PASS EL3 probe (full output: out/el3-secure.txt)"
else
    echo "FAIL EL3 probe (full output: out/el3-secure.txt)"; result 1
fi

# Log gate: every -d line is a recorded stub window or a listed line
step "log gate"
allow=$(cat "$HERE/../m4/expected/log-allow.txt" \
            "$HERE/../m5/expected/log-allow.txt" \
            "$HERE/expected/log-allow.txt" | grep -v -e '^#' -e '^$')
for run in firmware bootloader tee; do
    log="$OUT/$run/qemu.log"
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
    echo "M7 ACCEPTANCE: PASS"
else
    echo "M7 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
