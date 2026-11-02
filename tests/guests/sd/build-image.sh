#!/usr/bin/env bash
# Build the SD card image for the storage acceptance runs: 64 MiB (a
# power of two, as QEMU's SD card model requires up to 2 GiB) with an
# MS-DOS partition table, as on the board's eSD card, with a disk
# identifier of its own (sd.img 0x525a0001, sd-tee.img 0x525a0002), so
# each partition has a distinct Linux PARTUUID (525a0001-02, ...):
#   p1  16 MiB from sector 8192 (4 MiB), ext4 "rzv2l-sd": a data partition with
#       one known file (README)
#   p2  the rest, ext4 "rzv2l-root": a root file system with the project's
#       static BusyBox (../g0/build-initramfs.sh), BusyBox init and an
#       rcS that counts the boots in /var/boot-count. Linux boots it with
#       "root=/dev/mmcblk0p2 rw rootwait" and no initramfs. Its /boot
#       holds the Renesas kernel (../g1/) as the vendor U-Boot's default
#       command loads it: boot/Image and boot/r9a07g054l2-smarc.dtb.
#       /etc/rzv2l-card names the card (sd or sd-tee).
# Before p1: U-Boot's saved environment (0x1F0000, 128 KiB), written by
# uboot-env.py: the vendor's default environment (../fw/build-u-boot.sh)
# with boot.env's lines, the project's boot configuration, which loads
# the kernel from mmc 0:2 and passes root=PARTUUID=<this card's p2>
# (DR-0007). A copy with that block cleared boots the vendor's default
# command instead.
# No root rights: each file system is made with mkfs.ext4 -d in a separate
# file (under fakeroot, so the root files belong to root) and copied in.
# With --tee: the card for the project's TEE run (DR-0006), ../out/sd/sd-tee.img:
# /boot holds the TEE kernel and DTB (../g1-tee/build-kernel.sh), and the
# root gets the OP-TEE user space (../g1-tee/build-optee-user.sh):
# tee-supplicant, the hello_world client and its trusted application.
# Output: ../out/sd/sd.img, or sd-tee.img (prints its partition table).
# Host tools: sfdisk (util-linux), mkfs.ext4 (e2fsprogs), fakeroot, python3.
set -euo pipefail
umask 022
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../out/sd"
BB="$HERE/../out/g0/busybox/busybox"
G1="$HERE/../out/g1"
IMG=sd.img
CARD=sd
DISK_ID=0x525a0001
TEE_USER=""
if [ "${1:-}" = --tee ]; then
    G1="$HERE/../out/g1-tee"
    IMG=sd-tee.img
    CARD=sd-tee
    DISK_ID=0x525a0002
    TEE_USER="$G1/user"
    [ -d "$TEE_USER" ] || {
        echo "build-image.sh: $TEE_USER missing; run ../g1-tee/build-optee-user.sh" >&2
        exit 1; }
fi
SIZE=$((64 * 1024 * 1024))
P1_START=8192
P1_SECTORS=$((16 * 1024 * 2))
P2_START=$((P1_START + P1_SECTORS))
P2_SECTORS=$((SIZE / 512 - P2_START))

UBOOT_ENV="$HERE/../out/fw/u-boot-initial-env"
[ -f "$UBOOT_ENV" ] || {
    echo "build-image.sh: $UBOOT_ENV missing; run ../fw/build-u-boot.sh" >&2
    exit 1; }
if [ ! -x "$BB" ]; then
    echo "build-image.sh: $BB missing; run ../g0/build-initramfs.sh first" >&2
    exit 1
fi
for f in "$G1/linux/arch/arm64/boot/Image" "$G1/r9a07g054l2-smarc.dtb"; do
    [ -f "$f" ] || {
        echo "build-image.sh: $f missing; build the G1 kernel first" >&2
        exit 1; }
done
mkdir -p "$OUT"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# p1: data
mkdir "$work/data"
echo "rzv2l-smarc SD card image (tests/guests/sd/build-image.sh)" \
    > "$work/data/README"

# p2: root file system; one busybox binary, each applet a link to it
r="$work/root"
mkdir -p "$r"/{bin,sbin,usr/bin,usr/sbin,etc/init.d,dev,proc,sys,tmp,mnt,root,var}
chmod 1777 "$r/tmp"
cp "$BB" "$r/bin/busybox"
"$BB" --list-full | while read -r applet; do
    [ "$applet" = bin/busybox ] || ln -s /bin/busybox "$r/$applet"
done
echo 0 > "$r/var/boot-count"
echo "$CARD" > "$r/etc/rzv2l-card"
mkdir "$r/boot"
cp "$G1/linux/arch/arm64/boot/Image" "$G1/r9a07g054l2-smarc.dtb" "$r/boot/"
if [ -n "$TEE_USER" ]; then
    cp -a "$TEE_USER/." "$r/"
    mkdir -p "$r/var/lib/tee"
fi

cat > "$r/etc/inittab" <<'EOF'
::sysinit:/etc/init.d/rcS
::respawn:/bin/cttyhack /bin/sh -l
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
EOF

cat > "$r/etc/init.d/rcS" <<'EOF'
#!/bin/sh
# /dev is the kernel's devtmpfs (CONFIG_DEVTMPFS_MOUNT); / is mounted rw
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp
n=$(( $(cat /var/boot-count) + 1 ))
echo "$n" > /var/boot-count
sync
dev=$(sed -n 's/^DEVNAME=//p' "/sys/dev/block/$(mountpoint -d /)/uevent")
model=$(tr -d '\000' < /proc/device-tree/model 2>/dev/null)
printf '\n  %s, Linux %s\n' "${model:-unknown}" "$(uname -r)"
printf '  root file system on /dev/%s, boot %d from this card\n' "$dev" "$n"
printf '  BusyBox root: tests/guests/sd/build-image.sh\n\n'
EOF
chmod 755 "$r/etc/init.d/rcS"

cat > "$r/etc/profile" <<'EOF'
e=$(printf '\033')
export PS1="\[$e[1;32m\]rzv2l\[$e[0m\]:\w# "
dev=$(sed -n 's/^DEVNAME=//p' "/sys/dev/block/$(mountpoint -d /)/uevent")
# The root's PARTUUID, as Linux forms it: disk identifier, partition number
disk=$(basename "$(readlink -f "/sys/class/block/$dev/..")")
id=$(od -A n -t x4 -j 440 -N 4 "/dev/$disk" | tr -d ' ')
puuid=$(printf '%s-%02x' "$id" "$(cat "/sys/class/block/$dev/partition")")
echo "SD-ROOT: ready, root /dev/$dev, boot $(cat /var/boot-count)," \
    "partuuid $puuid, card $(cat /etc/rzv2l-card)"
EOF

rm -f "$OUT/$IMG"
truncate -s "$SIZE" "$OUT/$IMG"
printf 'label: dos\nlabel-id: %s\nstart=%d, size=%d, type=83\nstart=%d, size=%d, type=83\n' \
    "$DISK_ID" "$P1_START" "$P1_SECTORS" "$P2_START" "$P2_SECTORS" |
    sfdisk -q "$OUT/$IMG"
truncate -s $((P1_SECTORS * 512)) "$work/p1.img"
mkfs.ext4 -q -F -L rzv2l-sd -d "$work/data" "$work/p1.img"
truncate -s $((P2_SECTORS * 512)) "$work/p2.img"
fakeroot sh -c "chown -R 0:0 '$r' && mknod -m 600 '$r/dev/console' c 5 1 &&
    mkfs.ext4 -q -F -L rzv2l-root -d '$r' '$work/p2.img'"
dd if="$work/p1.img" of="$OUT/$IMG" bs=512 seek="$P1_START" conv=notrunc \
    status=none
dd if="$work/p2.img" of="$OUT/$IMG" bs=512 seek="$P2_START" conv=notrunc \
    status=none
python3 -I "$HERE/uboot-env.py" write "$OUT/$IMG" "$UBOOT_ENV" "$HERE/boot.env"
sfdisk -l "$OUT/$IMG"
