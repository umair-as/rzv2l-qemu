#!/usr/bin/env bash
# The M9 profile's U-Boot (docs/decisions/DR-0008): the pinned vendor
# source of build-u-boot.sh, one listed patch (patches/u-boot-m9/), the
# configuration fragment u-boot-m9.cfg, the default environment
# u-boot-m9.env and the profile's public key in every control DTB.
# The vendor-default build (build-u-boot.sh) is not changed.
#
# The key: tests/guests/out/m9/keys/m9-dev.key (RSA-2048), made once and
# reused by every later build and every test, so that one trust anchor
# signs and checks; m9-other.key, a second key, signs the wrong-key test
# FIT. Keys are test material, untracked, never product secrets.
# The patch: upstream U-Boot 2092322b31cc ("boot: Add
# fit_config_get_hash_list() to build signed node list"), code and doc
# hunks only: the signed-node list comes from the configuration's image
# references, not from the signature's hashed-nodes property.
#
# Needs: build-u-boot.sh run once (the pinned clone), python3 with
# pycryptodome (U-Boot's tools/key2dtsi.py), openssl, dtc, fdtget.
# Output: ../out/m9/ (u-boot.bin, mkimage, fw_printenv, u-boot.config, the keys, the
# key's .dtsi, build.txt with hashes).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REV=4eebfbaa4e61f8d3fa0e44ae59449213ffee981c
DEFCONFIG=smarc-rzv2l_defconfig
DL="$HERE/../dl"
SRC="$DL/renesas-u-boot-cip"
M9SRC="$DL/u-boot-m9-src"
B="$DL/u-boot-m9-build"
OUT="$HERE/../out/m9"
KEYS="$OUT/keys"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"

[ -d "$SRC/.git" ] || { echo "build-u-boot-m9.sh: run build-u-boot.sh first" >&2; exit 1; }
[ "$(git -C "$SRC" rev-parse HEAD)" = "$REV" ] || {
    echo "build-u-boot-m9.sh: $SRC is not at $REV" >&2; exit 1; }

mkdir -p "$OUT" "$KEYS"
for k in m9-dev m9-other; do
    if [ ! -e "$KEYS/$k.key" ]; then
        openssl genpkey -quiet -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
            -out "$KEYS/$k.key"
        openssl req -batch -new -x509 -days 3650 -key "$KEYS/$k.key" \
            -subj "/CN=$k" -out "$KEYS/$k.crt"
    fi
done

# The source: the pinned tree, exported, then the profile's patch
rm -rf "$M9SRC" "$B"
mkdir -p "$M9SRC"
git -C "$SRC" archive "$REV" | tar -x -C "$M9SRC"
for p in "$HERE"/patches/u-boot-m9/*.patch; do
    patch -s -p1 -d "$M9SRC" < "$p"
done

# The public key, required for configurations, as a .dtsi for the
# control DTBs
python3 "$M9SRC/tools/key2dtsi.py" --required-conf "$KEYS/m9-dev.crt" \
    "$OUT/m9-dev.dtsi"
# U-Boot looks for the include beside the board's .dts files
# (scripts/Makefile.lib dtsi_include_list_deps)
cp "$OUT/m9-dev.dtsi" "$M9SRC/arch/arm/dts/m9-dev.dtsi"

export SOURCE_DATE_EPOCH="$(git -C "$SRC" log -1 --format=%ct)"
make -s -C "$M9SRC" O="$B" CROSS_COMPILE="$CROSS" "$DEFCONFIG"
{
    cat "$HERE/u-boot-m9.cfg"
    echo "CONFIG_DEFAULT_ENV_FILE=\"$HERE/u-boot-m9.env\""
    echo "CONFIG_DEVICE_TREE_INCLUDES=\"m9-dev.dtsi\""
} > "$B/m9.cfg"
"$M9SRC/scripts/kconfig/merge_config.sh" -m -O "$B" "$B/.config" \
    "$B/m9.cfg" > /dev/null
make -s -C "$M9SRC" O="$B" CROSS_COMPILE="$CROSS" olddefconfig
# Every option of the fragment must be in the effective configuration
while read -r line; do
    case "$line" in
        "# CONFIG_"*" is not set") ;;
        "#"*|"") continue ;;
    esac
    grep -qxF "$line" "$B/.config" || {
        echo "build-u-boot-m9.sh: '$line' is not in the effective .config" >&2
        exit 1; }
done < "$B/m9.cfg"

make -s -C "$M9SRC" O="$B" CROSS_COMPILE="$CROSS" -j"$(nproc)"
# fw_printenv / fw_setenv for the slots' Linux (tools/env): the same
# source and configuration as U-Boot, so they read and write the two
# copies as U-Boot does; static, for the BusyBox root
make -s -C "$M9SRC" O="$B" CROSS_COMPILE="$CROSS" HOSTLDFLAGS=-static \
    envtools
file "$B/tools/env/fw_printenv" | grep -q "ARM aarch64.*statically linked" || {
    echo "build-u-boot-m9.sh: fw_printenv is not a static aarch64 binary" >&2
    exit 1; }

# The key must be in every control DTB U-Boot can select, and those
# DTBs must be what u-boot.bin carries
for dt in $(sed -n 's/^CONFIG_OF_LIST="\(.*\)"$/\1/p' "$B/.config"); do
    dtb="$B/arch/arm/dts/$dt.dtb"
    [ "$(fdtget "$dtb" /signature/key-m9-dev required)" = conf ] || {
        echo "build-u-boot-m9.sh: no required key in $dtb" >&2; exit 1; }
    cp "$dtb" "$OUT/$dt.dtb"
done
blob="$B/fit-dtb.blob"
size=$(stat -c %s "$blob")
cmp -s <(tail -c "$size" "$B/u-boot.bin") "$blob" || {
    echo "build-u-boot-m9.sh: u-boot.bin does not end in fit-dtb.blob" >&2
    exit 1; }

# bootargs and the vendor's in-place append (DR-0007 decision 6): the
# longest value, with an 11-character PARTUUID, must fit its allocation
python3 - "$HERE/u-boot-m9.env" <<'EOF'
import re, sys
env = dict(l.split("=", 1) for l in open(sys.argv[1]).read().splitlines()
           if l and not l.startswith("#"))
m = re.search(r'setenv bootargs "([^"]*)"', env["m9_load"])
args = m.group(1).replace("${root_wait}", env["root_wait"]) \
                 .replace("${m9_puuid}", "x" * 11)
usable = ((len(args) + 1 + 8 + 15) & ~15) - 8
if usable < len(args) + len(" wdt_overflow=0") + 1:
    sys.exit("build-u-boot-m9.sh: bootargs of %d characters overruns" % len(args))
EOF

cp "$B/u-boot.bin" "$B/u-boot" "$B/tools/mkimage" "$B/tools/env/fw_printenv" \
    "$OUT/"
cp "$B/.config" "$OUT/u-boot.config"
{
    echo "source: $REV + patches/u-boot-m9/ ($(cd "$HERE/patches/u-boot-m9" && ls))"
    echo "make: CROSS_COMPILE=$CROSS $DEFCONFIG + u-boot-m9.cfg; all"
    echo "toolchain: $("${CROSS}gcc" --version | head -1)"
    (cd "$OUT" && sha256sum u-boot.bin u-boot mkimage fw_printenv u-boot.config \
        m9-dev.dtsi ./*.dtb keys/m9-dev.crt keys/m9-other.crt)
    (cd "$HERE" && sha256sum u-boot-m9.cfg u-boot-m9.env patches/u-boot-m9/*.patch)
} > "$OUT/build.txt"
cat "$OUT/build.txt"
