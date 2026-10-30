#!/usr/bin/env bash
# Build the G0 initramfs: a static BusyBox 1.36.1 (aarch64) and an /init
# that mounts proc, sysfs and devtmpfs, prints a ready line and runs a
# shell on the console. Nothing in it knows about QEMU.
# Source: busybox.net tarball, checked against its pinned SHA-256, kept in
# ../dl. The cpio list is made with the G0 kernel's own gen_init_cpio, so
# build-kernel.sh runs first.
# Output: ../out/g0/initramfs.cpio.gz; prints its SHA-256.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VER=1.36.1
SHA256=b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314
URL=https://busybox.net/downloads/busybox-$VER.tar.bz2
DL="$HERE/../dl"
OUT="$HERE/../out/g0"
BB="$OUT/busybox"
CPIO="$OUT/linux/usr/gen_init_cpio"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"

if [ ! -x "$CPIO" ]; then
    echo "build-initramfs.sh: $CPIO missing; run build-kernel.sh first" >&2
    exit 1
fi
mkdir -p "$DL" "$BB"
tarball="$DL/busybox-$VER.tar.bz2"
[ -f "$tarball" ] || curl -sSfL -o "$tarball" "$URL"
echo "$SHA256  $tarball" | sha256sum -c --quiet -
[ -d "$DL/busybox-$VER" ] || tar -xjf "$tarball" -C "$DL"

# defconfig, static, and without tc: its CBQ code does not build against
# kernel headers from v6.8 on (the uapi definitions were removed).
make -s -C "$DL/busybox-$VER" O="$BB" ARCH=arm64 CROSS_COMPILE="$CROSS" \
    defconfig >/dev/null
sed -i -e 's/^# CONFIG_STATIC is not set/CONFIG_STATIC=y/' \
       -e 's/^CONFIG_TC=y/# CONFIG_TC is not set/' "$BB/.config"
make -s -C "$BB" ARCH=arm64 CROSS_COMPILE="$CROSS" oldconfig </dev/null >/dev/null
make -s -C "$BB" ARCH=arm64 CROSS_COMPILE="$CROSS" -j"$(nproc)" busybox
file "$BB/busybox" | grep -q 'statically linked'

cat > "$OUT/init" <<'EOF'
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
echo "G0-INIT: ready, cpus online $(cat /sys/devices/system/cpu/online)"
exec setsid cttyhack sh
EOF

# One busybox binary; each applet is a link to it
{
    echo "dir /bin 755 0 0"
    echo "dir /sbin 755 0 0"
    echo "dir /usr 755 0 0"
    echo "dir /usr/bin 755 0 0"
    echo "dir /usr/sbin 755 0 0"
    echo "dir /dev 755 0 0"
    echo "dir /proc 755 0 0"
    echo "dir /sys 755 0 0"
    echo "dir /tmp 1777 0 0"
    echo "nod /dev/console 600 0 0 c 5 1"
    echo "file /bin/busybox $BB/busybox 755 0 0"
    echo "file /init $OUT/init 755 0 0"
    "$BB/busybox" --list-full | while read -r applet; do
        [ "$applet" = bin/busybox ] || echo "slink /$applet /bin/busybox 777 0 0"
    done
} > "$OUT/initramfs.list"
"$CPIO" -t 0 "$OUT/initramfs.list" | gzip -9 -n > "$OUT/initramfs.cpio.gz"
(cd "$OUT" && sha256sum initramfs.cpio.gz)
