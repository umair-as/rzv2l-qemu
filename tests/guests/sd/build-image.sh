#!/usr/bin/env bash
# Build the SD card image for the storage acceptance runs: 64 MiB (a
# power of two, as QEMU's SD card model requires up to 2 GiB) with an
# MS-DOS partition table, as on the board's eSD card:
#   p1  16 MiB from sector 2048, ext4 "rzv2l-sd": a data partition with
#       one known file (README)
#   p2  the rest, ext4 "rzv2l-root": a root file system with the project's
#       static BusyBox (../g0/build-initramfs.sh), BusyBox init and an
#       rcS that counts the boots in /var/boot-count. Linux boots it with
#       "root=/dev/mmcblk0p2 rw rootwait" and no initramfs. Its /boot
#       holds the Renesas kernel (../g1/) as the vendor U-Boot's default
#       command loads it: boot/Image and boot/r9a07g054l2-smarc.dtb.
# No root rights: each file system is made with mkfs.ext4 -d in a separate
# file (under fakeroot, so the root files belong to root) and copied in.
# With --tee: the card for the project's TEE run (DR-0006), ../out/sd/sd-tee.img:
# /boot holds the TEE kernel and DTB (../g1-tee/build-kernel.sh), and the
# root gets the OP-TEE user space (../g1-tee/build-optee-user.sh):
# tee-supplicant, the hello_world client and its trusted application.
# Output: ../out/sd/sd.img, or sd-tee.img (prints its partition table).
# Host tools: sfdisk (util-linux), mkfs.ext4 (e2fsprogs), fakeroot.
set -euo pipefail
umask 022
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../out/sd"
BB="$HERE/../out/g0/busybox/busybox"
G1="$HERE/../out/g1"
IMG=sd.img
TEE_USER=""
if [ "${1:-}" = --tee ]; then
    G1="$HERE/../out/g1-tee"
    IMG=sd-tee.img
    TEE_USER="$G1/user"
    [ -d "$TEE_USER" ] || {
        echo "build-image.sh: $TEE_USER missing; run ../g1-tee/build-optee-user.sh" >&2
        exit 1; }
fi
SIZE=$((64 * 1024 * 1024))
P1_START=2048
P1_SECTORS=$((16 * 1024 * 2))
P2_START=$((P1_START + P1_SECTORS))
P2_SECTORS=$((SIZE / 512 - P2_START))

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
echo "SD-ROOT: ready, root /dev/$dev, boot $(cat /var/boot-count)"
EOF

rm -f "$OUT/$IMG"
truncate -s "$SIZE" "$OUT/$IMG"
printf 'label: dos\nstart=%d, size=%d, type=83\nstart=%d, size=%d, type=83\n' \
    "$P1_START" "$P1_SECTORS" "$P2_START" "$P2_SECTORS" |
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
sfdisk -l "$OUT/$IMG"
