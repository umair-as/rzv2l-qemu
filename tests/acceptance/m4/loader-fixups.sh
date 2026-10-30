#!/usr/bin/env bash
# The device-tree edits QEMU's loader makes in place of the board's
# U-Boot (docs/units/M4-loader-fixups/spec.md). For the G0 and G1 device
# trees, in every boot mode (0-5), the DTB handed to the kernel
# (-machine dumpdtb) is compared with the DTB file:
#   eSD (0):    /soc/mmc@11c00000 vqmmc-supply = phandle of
#               /regulator-vccq-sdhi0, vmmc-supply unchanged (the DTB has
#               no /regulator-vcc-sdhi0);
#   modes 1-5:  both supplies unchanged (eMMC, QSPI, SCIF download);
#   all:        /aliases mmc0 = SDHI0, mmc1 = SDHI1 added (QEMU's own edit,
#               the stock DTBs have none); no other difference than
#               QEMU's own /psci node.
# A regulator without a phandle gets the next free one (max + 1).
# Exit 0 only if every check passes.
# QEMU binary: $QEMU or ../../../build/qemu/qemu-system-aarch64
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/../../.."
QEMU="${QEMU:-$ROOT/build/qemu/qemu-system-aarch64}"
OUT="$HERE/out/loader-fixups"
mkdir -p "$OUT"
failures=0
MMC=/soc/mmc@11c00000
VCCQ=/regulator-vccq-sdhi0

check() {   # check <label> <got> <want>
    if [ "$2" = "$3" ]; then
        echo "PASS $1: $2"
    else
        echo "FAIL $1: $2, expected $3"; failures=$((failures + 1))
    fi
}

dump() {    # dump <in.dtb> <boot-mode> <out.dtb>
    "$QEMU" -M "rzv2l-smarc,boot-mode=$2,dumpdtb=$3" -display none \
        -kernel "$KERNEL" -dtb "$1" > "$3.log" 2>&1 ||
        { echo "FAIL QEMU on $1 boot-mode $2 (see $3.log)"; failures=$((failures + 1)); }
}

# Every line of the diff outside the /psci node
other_changes() {
    diff <(dtc -q -I dtb -O dts -s "$1") <(dtc -q -I dtb -O dts -s "$2") |
        grep '^[<>]' | grep -v -E 'arm,psci|cpu_off|cpu_on|cpu_suspend|migrate' |
        grep -v -E "vqmmc-supply" |
        grep -v -E '^> \s+mmc[01] = "/soc/mmc@11c[01]0000";$'
}

# The aliases QEMU adds: mmc0 = SDHI0, mmc1 = SDHI1
check_aliases() {   # check_aliases <label> <dtb> <want-mmc0>
    check "$1 /aliases/mmc0" "$(fdtget "$2" /aliases mmc0)" "$3"
    check "$1 /aliases/mmc1" "$(fdtget "$2" /aliases mmc1)" /soc/mmc@11c10000
}

for tier in g0 g1; do
    DTB="$ROOT/tests/guests/out/$tier/r9a07g054l2-smarc.dtb"
    KERNEL="$ROOT/tests/guests/out/$tier/linux/arch/arm64/boot/Image"
    vmmc=$(fdtget -t x "$DTB" $MMC vmmc-supply)
    vqmmc=$(fdtget -t x "$DTB" $MMC vqmmc-supply)
    vccq=$(fdtget -t x "$DTB" $VCCQ phandle)
    [ "$(fdtget -l "$DTB" / | grep -c '^regulator-vcc-sdhi0$')" -eq 0 ] ||
        { echo "FAIL $tier: the DTB has /regulator-vcc-sdhi0"; failures=$((failures + 1)); }

    dump "$DTB" 0 "$OUT/$tier-esd.dtb"
    check "$tier eSD vqmmc-supply" "$(fdtget -t x "$OUT/$tier-esd.dtb" $MMC vqmmc-supply)" "$vccq"
    check "$tier eSD vmmc-supply" "$(fdtget -t x "$OUT/$tier-esd.dtb" $MMC vmmc-supply)" "$vmmc"
    check "$tier eSD other changes" "$(other_changes "$DTB" "$OUT/$tier-esd.dtb" | wc -l)" 0
    check_aliases "$tier" "$OUT/$tier-esd.dtb" /soc/mmc@11c00000

    for bm in 1 2 3 4 5; do
        d="$OUT/$tier-mode$bm.dtb"
        dump "$DTB" $bm "$d"
        check "$tier boot mode $bm vqmmc-supply" "$(fdtget -t x "$d" $MMC vqmmc-supply)" "$vqmmc"
        check "$tier boot mode $bm vmmc-supply" "$(fdtget -t x "$d" $MMC vmmc-supply)" "$vmmc"
        check "$tier boot mode $bm other changes" "$(other_changes "$DTB" "$d" | wc -l)" 0
    done
done

# An alias the DTB already gives stays as it is
cp "$DTB" "$OUT/alias.dtb"
fdtput -t s "$OUT/alias.dtb" /aliases mmc0 /soc/mmc@11c10000
dump "$OUT/alias.dtb" 0 "$OUT/alias-esd.dtb"
check_aliases "g1 existing alias kept:" "$OUT/alias-esd.dtb" /soc/mmc@11c10000

# The regulator without a phandle (and nothing pointing at it): U-Boot's
# fdt_generate_phandle() gives it the highest phandle in the tree + 1
cp "$DTB" "$OUT/nophandle.dtb"
fdtput -d "$OUT/nophandle.dtb" $VCCQ phandle
max=$(dtc -q -I dtb -O dts "$OUT/nophandle.dtb" | sed -n 's/.*phandle = <0x\([0-9a-f]*\)>;.*/\1/p' |
      while read -r h; do echo $((16#$h)); done | sort -n | tail -1)
want=$(printf '%x' $((max + 1)))
dump "$OUT/nophandle.dtb" 0 "$OUT/nophandle-esd.dtb"
check "g1 eSD new phandle" "$(fdtget -t x "$OUT/nophandle-esd.dtb" $VCCQ phandle)" "$want"
check "g1 eSD vqmmc-supply (new phandle)" \
    "$(fdtget -t x "$OUT/nophandle-esd.dtb" $MMC vqmmc-supply)" "$want"

echo
if [ "$failures" -eq 0 ]; then
    echo "LOADER FIXUPS: PASS"
else
    echo "LOADER FIXUPS: FAIL ($failures check(s) failed)"
fi
[ "$failures" -eq 0 ]
