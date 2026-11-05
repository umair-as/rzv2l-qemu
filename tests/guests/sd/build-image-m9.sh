#!/usr/bin/env bash
# The M9 profile's SD card (docs/decisions/DR-0008 decision 2), for the
# module slot (mmc 0): an MS-DOS partition table with disk identifier
# 0x525a0003, so its PARTUUIDs differ from the other project cards:
#   p1  16 MiB from 0x400000, ext4 "rzv2l-sd": data
#   p2  48 MiB, ext4 "m9-slot-a": slot A's root, /boot/fitImage
#   p3  the rest, ext4 "m9-slot-b": slot B's root, /boot/fitImage
# and both U-Boot environment copies (0x1F0000, 0x210000) holding the
# M9 policy (../fw/u-boot-m9.env), written by uboot-env.py m9-write,
# which checks the copies' places against the M9 build's effective
# configuration and that p1 starts at or above 0x400000.
# Each root is the BusyBox root of build-image.sh with the signed FIT
# (../fw/build-fit-m9.sh) in /boot, its slot name in /etc/m9-slot, the
# static fw_printenv/fw_setenv of the M9 build, and the health service
# m9-health with its checks in /etc/m9-health.d/, run last by rcS.
# Output: ../out/sd/sd-m9.img (prints its partition table).
# Host tools: sfdisk, mkfs.ext4, fakeroot, python3.
set -euo pipefail
umask 022
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../out/sd"
BB="$HERE/../out/g0/busybox/busybox"
FIT="$HERE/../out/m9/fit/fitImage"
FWENV="$HERE/../out/m9/fw_printenv"
ENV="$HERE/../fw/u-boot-m9.env"
IMG=sd-m9.img
DISK_ID=0x525a0003
SIZE=$((128 * 1024 * 1024))
P1_START=8192                      # 0x400000
P1_SECTORS=$((16 * 1024 * 2))
P2_START=$((P1_START + P1_SECTORS))
P2_SECTORS=$((48 * 1024 * 2))
P3_START=$((P2_START + P2_SECTORS))
P3_SECTORS=$((SIZE / 512 - P3_START))

for f in "$BB" "$FIT" "$ENV" "$FWENV"; do
    [ -e "$f" ] || { echo "build-image-m9.sh: missing $f" >&2; exit 1; }
done
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir "$work/data"
echo "rzv2l-smarc M9 SD card (tests/guests/sd/build-image-m9.sh)" \
    > "$work/data/README"

# root SLOT DIR: a slot's root file system
root() {
    local r="$2"
    mkdir -p "$r"/{bin,sbin,usr/bin,usr/sbin,etc/init.d,dev,proc,sys,tmp,run,mnt,root,var,boot}
    chmod 1777 "$r/tmp"
    cp "$BB" "$r/bin/busybox"
    "$BB" --list-full | while read -r applet; do
        [ "$applet" = bin/busybox ] || ln -s /bin/busybox "$r/$applet"
    done
    echo 0 > "$r/var/boot-count"
    echo sd-m9 > "$r/etc/rzv2l-card"
    echo "$1" > "$r/etc/m9-slot"
    cp "$FIT" "$r/boot/fitImage"
    cp "$FWENV" "$r/sbin/fw_printenv"
    ln -s fw_printenv "$r/sbin/fw_setenv"
    cp "$HERE/m9-health" "$r/sbin/m9-health"
    chmod 755 "$r/sbin/m9-health"
    mkdir -p "$r/etc/m9-health.d"
    printf '#!/bin/sh\n# the root file system is writable\ntouch /var/.m9-rw && rm /var/.m9-rw\n' \
        > "$r/etc/m9-health.d/10-root-rw"
    printf '#!/bin/sh\n# /proc and /sys are mounted\ngrep -q " /proc proc " /proc/mounts && grep -q " /sys sysfs " /proc/mounts\n' \
        > "$r/etc/m9-health.d/20-proc-sys"
    chmod 755 "$r"/etc/m9-health.d/*
    cat > "$r/etc/inittab" <<'EOF'
::sysinit:/etc/init.d/rcS
::respawn:/bin/cttyhack /bin/sh -l
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
EOF
    cat > "$r/etc/init.d/rcS" <<'EOF'
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp
# fw_printenv keeps its lock file in /run
mount -t tmpfs tmpfs /run
n=$(( $(cat /var/boot-count) + 1 ))
echo "$n" > /var/boot-count
sync
printf '\n  M9 slot %s, Linux %s, boot %d of this slot\n\n' \
    "$(cat /etc/m9-slot)" "$(uname -r)" "$n"
/sbin/m9-health
EOF
    chmod 755 "$r/etc/init.d/rcS"
    cat > "$r/etc/profile" <<'EOF'
e=$(printf '\033')
export PS1="\[$e[1;32m\]rzv2l\[$e[0m\]:\w# "
dev=$(sed -n 's/^DEVNAME=//p' "/sys/dev/block/$(mountpoint -d /)/uevent")
disk=$(basename "$(readlink -f "/sys/class/block/$dev/..")")
id=$(od -A n -t x4 -j 440 -N 4 "/dev/$disk" | tr -d ' ')
puuid=$(printf '%s-%02x' "$id" "$(cat "/sys/class/block/$dev/partition")")
echo "SD-ROOT: ready, root /dev/$dev, boot $(cat /var/boot-count)," \
    "partuuid $puuid, card $(cat /etc/rzv2l-card)"
EOF
}
root A "$work/a"
root B "$work/b"

rm -f "$OUT/$IMG"
truncate -s "$SIZE" "$OUT/$IMG"
printf 'label: dos\nlabel-id: %s\nstart=%d, size=%d, type=83\nstart=%d, size=%d, type=83\nstart=%d, size=%d, type=83\n' \
    "$DISK_ID" "$P1_START" "$P1_SECTORS" "$P2_START" "$P2_SECTORS" \
    "$P3_START" "$P3_SECTORS" | sfdisk -q "$OUT/$IMG"
truncate -s $((P1_SECTORS * 512)) "$work/p1.img"
mkfs.ext4 -q -F -L rzv2l-sd -d "$work/data" "$work/p1.img"
for s in a b; do
    n=$([ $s = a ] && echo "$P2_SECTORS" || echo "$P3_SECTORS")
    truncate -s $((n * 512)) "$work/p-$s.img"
    fakeroot sh -c "chown -R 0:0 '$work/$s' &&
        mknod -m 600 '$work/$s/dev/console' c 5 1 &&
        mkfs.ext4 -q -F -L m9-slot-$s -d '$work/$s' '$work/p-$s.img'"
done
dd if="$work/p1.img" of="$OUT/$IMG" bs=512 seek="$P1_START" conv=notrunc status=none
dd if="$work/p-a.img" of="$OUT/$IMG" bs=512 seek="$P2_START" conv=notrunc status=none
dd if="$work/p-b.img" of="$OUT/$IMG" bs=512 seek="$P3_START" conv=notrunc status=none
python3 -I "$HERE/uboot-env.py" m9-write "$OUT/$IMG" "$ENV"
python3 -I "$HERE/uboot-env.py" m9-read "$OUT/$IMG"
sfdisk -l "$OUT/$IMG"
