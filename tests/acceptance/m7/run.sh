#!/usr/bin/env bash
# M7 acceptance for rzv2l-smarc: the board's TF-A BL31 as the PSCI
# firmware, in firmware mode (-bios), with the Renesas kernel (G1) and
# the root file system on the SD card (docs/units/M7-el3-platform/spec.md);
# then BL31, OP-TEE and U-Boot booting the kernel from the card
# (docs/units/M7-optee-uboot/spec.md); then the project's TEE kernel
# reaching OP-TEE from Linux (docs/units/M7-optee-linux/spec.md); then
# the root chosen by PARTUUID (DR-0007). M6 acceptance first (which runs
# M5 to M1 in direct mode). U-Boot boots with the project's boot
# configuration (tests/guests/sd/boot.env).
# Exit 0 only if every check passes ("M7 ACCEPTANCE").
# Then, separately, the vendor's unchanged U-Boot boot (compat.py): its
# own verdict line, "VENDOR-DEFAULT COMPATIBILITY", which does not change
# the M7 acceptance result or the exit status; its failed boots are kept.
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

step "root by PARTUUID: two attached cards, root on the other one; missing root"
python3 -I "$HERE/rootsel.py" "$OUT/rootsel"
rc=$?; result $rc; keep $rc rootsel

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
for run in firmware bootloader tee rootsel/other-medium \
           rootsel/missing-root; do
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
    verdict="M7 ACCEPTANCE: PASS"
else
    verdict="M7 ACCEPTANCE: FAIL ($failures check(s) failed)"
fi
echo "$verdict"

# Not part of the acceptance: reported on its own line
echo
step "vendor default boot (compatibility, not acceptance): U-Boot's own command, root=/dev/mmcblk0p2"
python3 -I "$HERE/compat.py" "$OUT/compat"
rc=$?; keep $rc compat

echo
echo "$verdict"
[ "$failures" -eq 0 ]
