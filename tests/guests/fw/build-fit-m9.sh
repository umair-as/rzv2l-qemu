#!/usr/bin/env bash
# The M9 profile's FIT images (docs/units/M9-fit/spec.md): the Renesas
# kernel (G1) and its unmodified DTB, one configuration "conf" signed
# with the profile's key (keys/m9-dev, from build-u-boot-m9.sh), and the
# negative images made from that signed FIT:
#   kernel-changed  one byte of the kernel's data changed after signing
#   dtb-changed     one byte of the DTB's data changed after signing
#   unsigned        the same images, no configuration signature
#   other-key       signed with keys/m9-other, which U-Boot does not hold
#   kernel-only     signed with the profile key, but the signature covers
#                   only the kernel: the DTB could be swapped. The pinned
#                   U-Boot trusts the signature's hashed-nodes list and
#                   accepts it; with the backport (patches/u-boot-m9/) the
#                   signed nodes come from the configuration, and U-Boot
#                   refuses it. The build checks both, with the host
#                   fit_check_sign of each build.
#   fakeroot, kernel-at
#                   upstream U-Boot's two crafted-FIT attacks
#                   (test/py/tests/vboot_evil.py of the M9 source): an
#                   evil kernel hidden behind a fake root node or a
#                   "kernel@" node, the signature left as signed
# The host's fit_check_sign (M9 source, with the U-Boot DTB that holds
# the key) must accept fitImage and refuse each negative: a build check,
# not the acceptance, which boots them (tests/acceptance/m9/fit.py).
# Output: ../out/m9/fit/ and its build.txt with every SHA-256.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
M9="$HERE/../out/m9"
OUT="$M9/fit"
KEYS="$M9/keys"
SRC="$HERE/../dl/u-boot-m9-src"
B="$HERE/../dl/u-boot-m9-build"
KERNEL="$HERE/../out/g1/linux/arch/arm64/boot/Image"
DTB="$HERE/../out/g1/r9a07g054l2-smarc.dtb"
MKIMAGE="$M9/mkimage"

for f in "$KERNEL" "$DTB" "$MKIMAGE" "$KEYS/m9-dev.key" "$KEYS/m9-other.key" \
         "$B/tools/fit_check_sign" "$M9/smarc-rzv2l.dtb"; do
    [ -e "$f" ] || { echo "build-fit-m9.sh: missing $f" >&2; exit 1; }
done
rm -rf "$OUT"
mkdir -p "$OUT"

VENDOR_CHECK="$HERE/../dl/u-boot-build/tools/fit_check_sign"
[ -e "$VENDOR_CHECK" ] || {
    echo "build-fit-m9.sh: missing $VENDOR_CHECK (build-u-boot.sh)" >&2; exit 1; }

# its KEY [IMAGES]: the FIT source; KEY empty = no signature node;
# IMAGES the signed images (default kernel and fdt)
its() {
    local images=${2:-'"kernel", "fdt"'}
    cat <<EOF
/dts-v1/;
/ {
	description = "qemu-rzv2l M9: Renesas kernel and DTB";
	#address-cells = <1>;
	images {
		kernel {
			description = "Linux kernel (G1)";
			data = /incbin/("$KERNEL");
			type = "kernel";
			arch = "arm64";
			os = "linux";
			compression = "none";
			load = <0x48080000>;
			entry = <0x48080000>;
			hash-1 { algo = "sha256"; };
		};
		fdt {
			description = "r9a07g054l2-smarc.dtb (vendor, unmodified)";
			data = /incbin/("$DTB");
			type = "flat_dt";
			arch = "arm64";
			compression = "none";
			hash-1 { algo = "sha256"; };
		};
	};
	configurations {
		default = "conf";
		conf {
			description = "slot FIT";
			kernel = "kernel";
			fdt = "fdt";
EOF
    if [ -n "$1" ]; then
        cat <<EOF
			signature-1 {
				algo = "sha256,rsa2048";
				key-name-hint = "$1";
				sign-images = $images;
			};
EOF
    fi
    printf '\t\t};\n\t};\n};\n'
}

its m9-dev > "$OUT/fit.its"
"$MKIMAGE" -q -f "$OUT/fit.its" -k "$KEYS" "$OUT/fitImage"
its "" > "$OUT/unsigned.its"
"$MKIMAGE" -q -f "$OUT/unsigned.its" "$OUT/fitImage-unsigned"
its m9-other > "$OUT/other-key.its"
"$MKIMAGE" -q -f "$OUT/other-key.its" -k "$KEYS" "$OUT/fitImage-other-key"
its m9-dev '"kernel"' > "$OUT/kernel-only.its"
"$MKIMAGE" -q -f "$OUT/kernel-only.its" -k "$KEYS" "$OUT/fitImage-kernel-only"

# One byte changed inside an image's data: found by a 64-byte run of that
# image, which must occur once in the FIT
python3 - "$OUT/fitImage" "$KERNEL" "$DTB" "$OUT" <<'EOF'
import sys
fit_path, kernel, dtb, out = sys.argv[1:]
fit = open(fit_path, "rb").read()
for name, src, at in (("kernel-changed", kernel, 0x10000),
                      ("dtb-changed", dtb, 0x200)):
    data = open(src, "rb").read()
    run = data[at:at + 64]
    pos = fit.find(run)
    if pos < 0 or fit.find(run, pos + 1) >= 0:
        sys.exit("build-fit-m9.sh: %s: no unique place to change" % name)
    bad = bytearray(fit)
    bad[pos] ^= 0x01
    open("%s/fitImage-%s" % (out, name), "wb").write(bad)
EOF

# Upstream's crafted FITs, from the signed one, with an evil kernel
head -c 65536 /dev/zero | tr '\0' 'E' > "$OUT/evil-kernel"
for attack in fakeroot kernel@; do
    python3 "$SRC/test/py/tests/vboot_evil.py" "$OUT/fitImage" \
        "$OUT/fitImage-${attack/@/-at}" "$OUT/evil-kernel" "$attack"
done

# Host check: the signed FIT verifies, every negative does not
check() {   # check FIT WANT(0 accept, 1 refuse)
    if "$B/tools/fit_check_sign" -f "$1" -k "$M9/smarc-rzv2l.dtb" \
            > "$1.check" 2>&1; then got=0; else got=1; fi
    [ "$got" = "$2" ] || {
        echo "build-fit-m9.sh: fit_check_sign on $(basename "$1"): want" \
             "$([ "$2" = 0 ] && echo accept || echo refuse)" >&2
        cat "$1.check" >&2; exit 1; }
}
check "$OUT/fitImage" 0
for n in kernel-changed dtb-changed unsigned other-key kernel-only fakeroot \
         kernel-at; do
    check "$OUT/fitImage-$n" 1
done
# The backport's effect: the pinned, unpatched tool accepts kernel-only
"$VENDOR_CHECK" -f "$OUT/fitImage-kernel-only" -k "$M9/smarc-rzv2l.dtb" \
    > "$OUT/fitImage-kernel-only.vendor-check" 2>&1 || {
    echo "build-fit-m9.sh: the unpatched fit_check_sign refuses kernel-only;" \
         "the case no longer shows the backport's effect" >&2; exit 1; }

{
    echo "key: keys/m9-dev ($(sha256sum < "$KEYS/m9-dev.crt" | cut -c1-64) m9-dev.crt)"
    (cd "$OUT" && sha256sum fitImage $(cd "$OUT" && ls fitImage-* | grep -v '\.') evil-kernel)
    (cd "$(dirname "$KERNEL")" && sha256sum Image)
    (cd "$(dirname "$DTB")" && sha256sum "$(basename "$DTB")")
} > "$OUT/build.txt"
cat "$OUT/build.txt"
