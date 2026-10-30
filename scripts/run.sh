#!/usr/bin/env bash
# Boot a guest on the rzv2l-smarc machine, interactively, with the serial
# console (SCIF0) on this terminal. For hands-on testing; the acceptance
# scripts under tests/acceptance/ stay the proof.
#
#   scripts/run.sh [options] [-- <extra QEMU arguments>]
#
# Options:
#   -t, --tier g0|g1     guest kernel and DTB: g0 mainline, g1 vendor (default g1)
#   -b, --boot-mode N    MD_BOOT pins 0-5 (default 0, eSD); 1 = eMMC
#   -a, --append "ARGS"  kernel command line (default: the DTB's own bootargs)
#   -n, --no-initrd      boot without the BusyBox initramfs
#       --no-net         no network backend on ETH0: no cable, and the
#                        stock bootargs' ip=on then waits 120 s for one
#                        (default: ETH0 on QEMU user networking, "net0")
#   -s, --sd IMAGE       raw SD card image in the module slot (SDHI0, mmc0);
#                        the guest writes to it, so pass a copy you can lose
#                        (tests/guests/sd/build-image.sh builds one)
#   -d, --debug MASK     QEMU -d mask (default unimp,guest_errors,invalid_mem;
#                        "none" turns it off); the log goes to OUT/qemu.log
#   -o, --out DIR        output directory (default build/run/<tier>)
#   -g, --gdb            wait for gdb on tcp::1234 before the first instruction
#       --dumpdtb        write the DTB QEMU hands the kernel to OUT/qemu.dtb
#                        (and its source to OUT/qemu.dts), then exit
#       --dry-run        print the QEMU command and exit
#   -h, --help           this text
#
# QEMU binary: $QEMU, else build/qemu/qemu-system-aarch64.
# Guest artifacts: tests/guests/out/<tier>/ (built by tests/guests/*/build-*.sh).
#
# On the console: Ctrl-A X quits QEMU, Ctrl-A C switches between the
# serial console and the QEMU monitor (info mtree, info qtree, xp, ...).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QEMU="${QEMU:-$ROOT/build/qemu/qemu-system-aarch64}"
tier=g1
boot_mode=0
append=""
initrd=1
net=1
sd=""
debug="unimp,guest_errors,invalid_mem"
out=""
gdb=0
dumpdtb=0
dry_run=0
extra=()

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }
die() { echo "run.sh: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        -t|--tier) tier="${2:?}"; shift 2 ;;
        -b|--boot-mode) boot_mode="${2:?}"; shift 2 ;;
        -a|--append) append="${2?}"; shift 2 ;;
        -n|--no-initrd) initrd=0; shift ;;
        --no-net) net=0; shift ;;
        -s|--sd) sd="${2:?}"; shift 2 ;;
        -d|--debug) debug="${2:?}"; shift 2 ;;
        -o|--out) out="${2:?}"; shift 2 ;;
        -g|--gdb) gdb=1; shift ;;
        --dumpdtb) dumpdtb=1; shift ;;
        --dry-run) dry_run=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; extra=("$@"); break ;;
        *) die "unknown option $1 (see --help)" ;;
    esac
done

case "$tier" in g0|g1) ;; *) die "tier must be g0 or g1" ;; esac
case "$boot_mode" in [0-5]) ;; *) die "boot mode must be 0-5" ;; esac

GUEST="$ROOT/tests/guests/out/$tier"
KERNEL="$GUEST/linux/arch/arm64/boot/Image"
DTB="$GUEST/r9a07g054l2-smarc.dtb"
# One initramfs serves both kernels
INITRD="$ROOT/tests/guests/out/g0/initramfs.cpio.gz"
out="${out:-$ROOT/build/run/$tier}"

[ -x "$QEMU" ] || die "no QEMU at $QEMU (build it: docs/learning/building-and-testing.md)"
for f in "$KERNEL" "$DTB"; do
    [ -f "$f" ] || die "missing $f (run tests/guests/$tier/build-*.sh)"
done
[ -z "$sd" ] || [ -f "$sd" ] || die "no SD image at $sd"
[ "$initrd" -eq 0 ] || [ -f "$INITRD" ] || die "missing $INITRD (run tests/guests/g0/build-initramfs.sh)"
mkdir -p "$out"

machine="rzv2l-smarc,boot-mode=$boot_mode"
[ "$dumpdtb" -eq 0 ] || machine="$machine,dumpdtb=$out/qemu.dtb"

cmd=("$QEMU" -M "$machine" -kernel "$KERNEL" -dtb "$DTB"
     -display none -nodefaults -serial mon:stdio)
[ "$initrd" -eq 0 ] || cmd+=(-initrd "$INITRD")
[ -z "$append" ] || cmd+=(-append "$append")
[ -z "$sd" ] || cmd+=(-drive "if=sd,index=0,format=raw,file=$sd")
# A cable on ETH0, as on the EVK's cabled port: user networking (slirp)
[ "$net" -eq 0 ] || cmd+=(-nic user,id=net0)
[ "$debug" = none ] || cmd+=(-d "$debug" -D "$out/qemu.log")
[ "$gdb" -eq 0 ] || cmd+=(-s -S)
cmd+=("${extra[@]}")

if [ "$dry_run" -eq 1 ]; then
    printf '%q ' "${cmd[@]}"; echo
    exit 0
fi

if [ "$dumpdtb" -eq 1 ]; then
    "${cmd[@]}" < /dev/null
    dtc -q -I dtb -O dts -s -o "$out/qemu.dts" "$out/qemu.dtb"
    echo "DTB handed to the kernel: $out/qemu.dtb (source: $out/qemu.dts)"
    exit 0
fi

echo "rzv2l-smarc: tier $tier, boot mode $boot_mode; quit with Ctrl-A X, monitor Ctrl-A C"
[ -z "$sd" ] || echo "SD card (SDHI0, /dev/mmcblk0): $sd"
[ "$debug" = none ] || echo "QEMU -d log: $out/qemu.log"
[ "$gdb" -eq 0 ] || echo "waiting for gdb: target remote :1234"
exec "${cmd[@]}"
