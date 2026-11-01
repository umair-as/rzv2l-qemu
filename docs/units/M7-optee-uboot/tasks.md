# M7-optee-uboot — tasks

Branches `unit/M7-optee-uboot` (project and fork), rebased on M7-el3-platform once it merges.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | OP-TEE build: vendor commit, BSP flags, `CFG_RZ_SCE=n`, reproducible | new `build-optee.sh` in `tests/guests/fw/` | SHA-256 the same over two builds | planned |
| T2 | U-Boot build: vendor commit, `smarc-rzv2l_defconfig`, reproducible | new `build-u-boot.sh` in `tests/guests/fw/` | as T1 | planned |
| T3 | SD card with `boot/Image` and the DTB on partition 2 | `tests/guests/sd/build-image.sh` | U-Boot's `ext4load` | planned |
| T4 | BL2 stand-in: BL32 and BL33 entries in the parameter block, images loaded where BL2 puts them | fork `hw/arm/rzv2l-smarc.c` | firmware boot | planned |
| T5 | Failure loop: OP-TEE, then U-Boot (OTP, RPC, DDR ECC read, USB), each window with its class | fork models and SoC; `docs/device-map.md` | firmware boot, `-d` log gate | planned |
| T6 | Acceptance: OP-TEE and U-Boot banners, Linux from the card, `MIGRATE_INFO_TYPE`, hotplug, reset, watchdog outlived; unit 1's boot and direct mode unchanged | `tests/acceptance/m7/` | M7 ACCEPTANCE | planned |
| T7 | EVK-R80: DDR controller ECC enable as U-Boot reads it | `docs/evidence/` | — | requested |
