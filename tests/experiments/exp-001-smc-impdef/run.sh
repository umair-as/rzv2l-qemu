#!/usr/bin/env bash
# EXP-001 runner. Usage: ./run.sh <test>|all     (builds the probe first)
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
QEMU="${QEMU:-$HERE/../../../build/qemu/qemu-system-aarch64}"
make -s -C "$HERE" >/dev/null
IMG="$HERE/out/probe.Image"   # raw arm64 Image -> QEMU's is_linux path
ELF="$HERE/out/probe.elf"     # ELF -> non-Linux path (boots at highest EL)

declare -A T
# t1: has_el3=0 has_el2=1, Linux entry at EL2, PSCI conduit SMC
T[t1-virt-el2-smc]="-M virt,virtualization=on -cpu cortex-a55 -smp 2 -kernel $IMG"
# t2: has_el3=0 has_el2=0, Linux entry at EL1, PSCI conduit HVC
T[t2-virt-el1-hvc]="-M virt -cpu cortex-a55 -smp 2 -kernel $IMG"
# t3: has_el3=1 has_el2=1, no firmware, Linux entry at EL2, conduit SMC
T[t3-virt-el3-el2-smc]="-M virt,secure=on,virtualization=on -cpu cortex-a55 -smp 2 -kernel $IMG"
# t4: has_el3=1, ELF => not Linux => starts at EL3, QEMU PSCI disabled
T[t4-virt-el3-elf]="-M virt,secure=on,virtualization=on -cpu cortex-a55 -smp 1 -kernel $ELF"
# t5: SMC conduit + EL1 entry (has_el2=off on a virt=on machine) -- the rzv2l shape
T[t5-virt-el1-smc]="-M virt,virtualization=on -cpu cortex-a55,has_el2=off -smp 2 -kernel $IMG"
# t6: same as t5 with has_el3=1 too
T[t6-virt-el1-smc-el3]="-M virt,secure=on,virtualization=on -cpu cortex-a55,has_el2=off -smp 2 -kernel $IMG"
# t7: CNTFRQ override + attempt to override MPIDR from the command line
T[t7-cntfrq-mpaff]="-M virt -cpu cortex-a55,cntfrq=24000000,mp-affinity=0x100 -smp 1 -kernel $IMG"
# t8: control CPU that does define CPUPWRCTLR/CPUACTLR/CPUECTLR (EL3 start)
T[t8-n1-el3-elf]="-M virt,secure=on,virtualization=on -cpu neoverse-n1 -smp 1 -kernel $ELF"

# A probe prints "=== DONE" and then idles, so `timeout` ending the run
# (status 124) is expected. A run counts as complete only if DONE was seen.
# Anything else is reported and makes the script exit non-zero: a launch
# failure (QEMU exits with another status) or an incomplete probe.
FAILED=0
run() {
    local out rc
    echo "##### $1: qemu-system-aarch64 ${T[$1]}"
    set +e
    # shellcheck disable=SC2086
    out=$(timeout 10 "$QEMU" -nographic -m 256 -monitor none -serial stdio ${T[$1]} \
        -d guest_errors 2>&1)
    rc=$?
    set -e
    printf '%s\n' "$out" | tr -d '\r'
    if [[ "$out" == *"=== DONE"* ]]; then
        echo "##### $1: COMPLETE (qemu status $rc)"
    elif [[ $rc -ne 0 && $rc -ne 124 ]]; then
        echo "##### $1: LAUNCH FAILURE (qemu status $rc)"; FAILED=1
    else
        echo "##### $1: INCOMPLETE (no DONE marker, qemu status $rc)"; FAILED=1
    fi
}
if [[ "${1:-}" == all ]]; then
    for t in $(printf '%s\n' "${!T[@]}" | sort); do run "$t"; done
    exit $FAILED
elif [[ -n "${1:-}" && -n "${T[$1]:-}" ]]; then
    run "$1"
    exit $FAILED
else
    echo "tests:"; printf '  %s\n' "${!T[@]}" | sort; exit 1
fi
