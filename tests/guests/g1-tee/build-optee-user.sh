#!/usr/bin/env bash
# Build the OP-TEE user space for the project's TEE run (DR-0006), static,
# for the BusyBox root file system:
#   optee_client 4.8.0 (github.com/OP-TEE/optee_client, 9d6f69844f):
#     libteec and tee-supplicant; no plugins, no libteeacl, no systemd or
#     udev files; trusted applications looked up in /lib/optee_armtz
#   optee_examples 4.8.0 (github.com/linaro-swg/optee_examples, 3ef17eb1f3):
#     hello_world, its client and its trusted application, built with the
#     TA dev kit of the OP-TEE build (../fw/build-optee.sh) and signed with
#     OP-TEE's public development key (an emulation test, not a product key)
# The releases match OP-TEE 4.8 (82a5cd3b). Sources cloned once into ../dl.
# Output: ../out/g1-tee/user/{usr/bin,usr/sbin,lib/optee_armtz} and
# build-user.txt (the commits and the SHA-256 of each output).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DL="$HERE/../dl"
OUT="$HERE/../out/g1-tee/user"
CROSS="${CROSS_COMPILE:-aarch64-linux-gnu-}"
TA_DEV_KIT="$DL/optee-build/export-ta_arm64"
CLIENT_REV=9d6f69844ff60ec0966cf3659abcc38eda8b31ea
EXAMPLES_REV=3ef17eb1f309def91113637f95f67613b1d89119

[ -d "$TA_DEV_KIT" ] || { echo "build-optee-user.sh: no $TA_DEV_KIT; run ../fw/build-optee.sh" >&2; exit 1; }
fetch() {
    [ -d "$DL/$1/.git" ] || git clone -q "$2" "$DL/$1"
    git -C "$DL/$1" -c advice.detachedHead=false checkout -q "$3"
    [ -z "$(git -C "$DL/$1" status --porcelain)" ] || {
        echo "build-optee-user.sh: $DL/$1 has local changes" >&2; exit 1; }
}
fetch optee_client https://github.com/OP-TEE/optee_client.git "$CLIENT_REV"
fetch optee_examples https://github.com/linaro-swg/optee_examples.git "$EXAMPLES_REV"

rm -rf "$OUT" "$DL/optee_client-build" "$DL/optee_client-install"
mkdir -p "$OUT/usr/bin" "$OUT/usr/sbin" "$OUT/lib/optee_armtz"

# optee_client: static libteec and tee-supplicant
cmake -S "$DL/optee_client" -B "$DL/optee_client-build" -Wno-dev \
    -DCMAKE_C_COMPILER="${CROSS}gcc" -DCMAKE_SYSTEM_NAME=Linux \
    -DCMAKE_SYSTEM_PROCESSOR=aarch64 -DCMAKE_INSTALL_PREFIX=/usr \
    -DBUILD_SHARED_LIBS=OFF -DCMAKE_EXE_LINKER_FLAGS=-static \
    -DWITH_TEEACL=OFF -DCFG_TEE_SUPP_PLUGINS=OFF \
    -DCFG_ENABLE_SYSTEMD=OFF -DCFG_ENABLE_UDEV=OFF \
    -DCFG_TEE_FS_PARENT_PATH=/var/lib/tee > /dev/null
cmake --build "$DL/optee_client-build" -j"$(nproc)" > /dev/null
DESTDIR="$DL/optee_client-install" cmake --install "$DL/optee_client-build" > /dev/null
EXPORT="$DL/optee_client-install/usr"
cp "$EXPORT/sbin/tee-supplicant" "$OUT/usr/sbin/"

# hello_world: the client, static, and the trusted application
HW="$DL/optee_examples/hello_world"
make -s -C "$HW/host" CROSS_COMPILE="$CROSS" TEEC_EXPORT="$EXPORT" \
    LDADD="-L$EXPORT/lib -lteec -lpthread -static" --no-builtin-variables clean all
make -s -C "$HW/ta" CROSS_COMPILE="$CROSS" PLATFORM=rz \
    TA_DEV_KIT_DIR="$TA_DEV_KIT" clean all
cp "$HW/host/optee_example_hello_world" "$OUT/usr/bin/"
cp "$HW/ta/"*.ta "$OUT/lib/optee_armtz/"
make -s -C "$HW/host" clean > /dev/null
make -s -C "$HW/ta" TA_DEV_KIT_DIR="$TA_DEV_KIT" clean > /dev/null

{
    echo "optee_client: $(git -C "$DL/optee_client" rev-parse HEAD)"
    echo "optee_examples: $(git -C "$DL/optee_examples" rev-parse HEAD)"
    echo "toolchain: $("${CROSS}gcc" --version | head -1)"
    (cd "$OUT" && find . -type f | sort | xargs sha256sum)
} > "$OUT/../build-user.txt"
cat "$OUT/../build-user.txt"
