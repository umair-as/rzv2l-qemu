# M8-full-chain — spec

**Milestone:** M8 (the full boot chain, stage C; third unit). **Requirements:** REQ-SYSC-002 (the boot source from `SYS_LSI_MODE`), REQ-GUEST-003 (unmodified firmware), REQ-TEE-001 (Linux reaches OP-TEE), REQ-GUEST-006 (the root by PARTUUID). Statuses change at release closure, not here. **Status:** implemented.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). Guest sources: TF-A `f59ed5a31` (`P/` = `plat/renesas/rz/common/`), U-Boot `4eebfbaa4e` (`B/` = `board/renesas/rzv2l-dev/`).

## Scope

**No new block, and no QEMU change expected.** This unit checks what the board's firmware already does on the flash path: in boot mode 3 the machine stands in for the boot ROM and copies only BL2 from the QSPI flash (M8-bl2-staging). BL2 sets up the DDR (M8-ddr-stub), then reads BL31, OP-TEE (BL32) and U-Boot (BL33) from the FIP (Firmware Image Package, the container at flash offset `0x20000`, `tests/guests/fw/build-spi-image.sh`) and starts BL31. U-Boot then boots the Renesas kernel from the SD card to the Linux shell. A model change is needed only if a check below exposes a gap. In that case the change is a new task with its own qtest and mutation, and the PR gets a review build.

- **No staging.** The command line has no `-bios`, `-kernel`, `bl32=` or `bl33=`. The machine refuses `bl32`/`bl33` without `-bios` (`hw/arm/rzv2l-smarc.c` `rzv2l_smarc_init`). Without `-bios` or `-kernel`, boot modes 3 and 4 take the boot ROM stand-in, which loads BL2 and nothing else.
- **One start state.** On this path everything after the boot ROM writes the post-firmware state itself. Every machine property that otherwise presets that state is off: `cpg-bl2-boot` (needs `bl33`), `scif0-direct-boot`, `pfc-direct-boot`, `syc-direct-boot` (each needs `-kernel`). If this path behaves differently from M7's staged path (`-bios` + `bl32=` + `bl33=`), the difference is a finding of this unit, recorded and not patched over.
- **U-Boot's device-tree edit.** U-Boot's `ft_verify_fdt` (`B/rzv2l-dev.c:274-291`) reads `SYS_LSI_MODE`. It edits SDHI0's two supplies only in eSD mode (boot mode 0) and makes no edit in boot mode 3. Linux therefore receives the stock SD0 node. In a QEMU trial run on fork `176d418966` the card in the module slot still mounted as the root: an emulator observation, not EVK evidence.
  - **(A):** that the board itself, booting from the QSPI flash, runs Linux's root from a microSD card in the module slot. This is not measured on the EVK. It is recorded as a fidelity assumption, not a gap.
- **Not in scope:** U-Boot writing the flash, boot modes 0-2 through BL2 (the stand-in serves only 3 and 4), A/B selection and rollback (M9). The deferred hardware questions stay recorded and deferred, with no EVK read: the SPI flash controller's open questions (`../M7-rpc-spinor/spec.md`, `../../research/rpc.md` §4: U-Boot's 3-byte write tail, SMWDR0's byte order, the direct-mode start state, which SPI clock gates register access) and the SYSC access-control questions of `../M8-bl2-staging/spec.md` (the `SLVACCCTL14` value against Non-secure ID reads; the untested refusal of Non-secure writes).

## What the guest needs

In the order the guest acts:

1. **BL2 picks the FIP's device from the boot-mode bits.**
   - `sys_get_boot_mode()` (`P/drivers/sys.c:25-50`) reads `SYS_LSI_MODE` bits 3:0 and panics on any value other than 0-4.
   - `plat_storage.c:228-265` then opens the FIP on the SPI flash for 3 and 4 (`spi_multi_setup`, chosen by `PLAT_SOC_RZG2L := 1` in `P/rz_common.mk:7`; the build's `spi_multi.o`; memory-mapped reads), on the eMMC for 1 and 2, and on the SD card for 0.
   - BL2 prints the raw register (`P/bl2_plat_setup.c:231`).
2. **The FIP.** `fiptool create --soc-fw bl31.bin --tos-fw tee-raw.bin --nt-fw u-boot.bin` makes the FIP, and the image layout is in `build.txt` beside the image, with the SHA-256 of each part.
   - OP-TEE `82a5cd3b` is built with `CFG_RZ_SCE=n`. The production build panics without TSIP (Renesas's closed crypto engine). This is the existing fidelity gap under REQ-GUEST-003.
3. **U-Boot's environment.** `CONFIG_ENV_IS_IN_MMC=y`, `SYS_MMC_ENV_DEV=0`, `ENV_OFFSET=0x1F0000` (the build's `.config`), with no SPI-flash environment. U-Boot reads the project's boot configuration (`tests/guests/sd/boot.env`, DR-0007) from the card, as in M7.
4. **The kernel.** The kernel takes PSCI from BL31 and the TEE driver from OP-TEE, as in M7 (`../M7-optee-uboot/spec.md`, `../M7-optee-linux/spec.md`).

## Exit criterion

New acceptance script `tests/acceptance/m8/chain.py`. It reuses M7's check functions through a parameter for the firmware source in `bootloader.start`, not through a copy of them.

1. **Chain.** `-M rzv2l-smarc,boot-mode=3`, the flash image and the M7 card in the module slot, without the options of Scope.
   - SCIF0 shows in order (each line searched from the end of the one before): BL2's lines up to `Booting BL31`, then the BL31 banner, OP-TEE's banner and its switch to the normal world, the U-Boot banner, `Loading Environment from MMC... Reading from MMC(0)... OK`, the kernel load, PSCI with OP-TEE up, and the shell with `/` on the PARTUUID partition and both CPUs online (M7's `boot_checks`).
   - `reboot` causes BL31's `SYSTEM_RESET`. Boot 2's checks search from the `reboot` request on and start again at BL2's banner: the stand-in reloads BL2 at each reset (`rzv2l_smarc_rom_cpu_reset`) and the chain repeats to the shell.
2. **From the FIP, not staged.** Each negative case runs a copy of the flash image with one FIP entry removed (`fiptool remove`).
   - BL33 removed: BL2 prints its load error for that image and stops, with no BL31 banner and no U-Boot banner.
   - BL31 removed: BL2 prints its load error and stops, with no BL31 banner.
   - Each case runs a fresh copy of the flash image (the source image is never written). The script asserts its own QEMU command line (none of the Scope options) and records the SHA-256 of the image each run actually used, including each modified one, in its run directory.
3. **Linux and OP-TEE.** M7's `tee_checks` run unchanged on the chain path with the TEE card (`sd-tee.img`, DR-0006): the driver probes and reports `82a5cd3b`, `/dev/tee0` and `/dev/teepriv0` exist, `tee-supplicant` runs, and the `hello_world` TA returns 43 for 42 with exit status 0.
4. **REQ-SYSC-002's criterion: `SYS_LSI_MODE` reports the configured boot source.**
   - The existing qtest (`rzv2l-smarc-test` `/sysc/boot-pins`, `/sysc/boot-mode-reserved`) shows the register value per strap.
   - With the real BL2, boot mode 3 prints `SYS_LSI_MODE: 0x10003` and boot mode 4 prints `0x10004`. In each mode the FIP loads from the flash, which `plat_storage.c` selects from those bits; the FIP exists nowhere else in the run.
   - **Conflict, recorded:** the catalogue names "U-Boot boot-source output" as the verification. U-Boot prints no boot source: `board_late_init` (`B/rzv2l-dev.c:260-267`) only re-arms the watchdog, and `ft_verify_fdt` reads the register silently. BL2's output and its choice of device are the observable consequences. The Verification column and the status are corrected together at release closure.
5. **Log gate.**
   - **The chain's own list.** A separate `m8/expected/log-allow-chain.txt` holds the lines after `Booting BL31`, each checked at its guest source on this path; `log-allow.txt` stays BL2's, so `bl2.py`'s check does not widen. The gate reads M4's, M5's and both M8 lists, not M7's.
   - **M7's lines.** The trial run shows the same set of distinct lines after `Booting BL31` as M7's staged run, minus Linux's write to the watchdog's WDTTIM register (M7 provokes it with its watchdog step, this run does not). M7's four lines (U-Boot's Ethernet PFC writes, the watchdog writes ignored while it runs, SCIF's MDDR, `SDHI_PORTSEL`) go in only after each one's source line is re-read with BL2 in front. In particular, SCIF0's and the PFC's state now come from BL2, not from the machine's preset. The UNIMP windows (the stub windows) and M4's and M5's lists apply as in M7.
6. **Regression.** M8's BL2 checks and M7 acceptance run unchanged.

## Evidence

[`research/bl2.md`](../../research/bl2.md) (BL2 on this path), [`research/sysc.md`](../../research/sysc.md) (`SYS_LSI_MODE`), `../../research/boot-chain-firmware.md`, DR-0006, DR-0007; the device map rows for SYSC, RPC and the DDR; the trial run on fork `176d418966` (`main` `8ac2294`), kept in the working area until the acceptance run replaces it.

## Next blocker (fork `176d418966`)

None in M8. The chain runs from the boot ROM stand-in to the Linux shell twice in one QEMU, with no model change. The `-d unimp,guest_errors,invalid_mem` log of the chain, boot-mode-4 and OP-TEE runs has only the stub windows of M4 and M5 (USB, I2C, CAN-FD, ADC, the thermal sensor, display and sound: UNIMP, the guest's drivers probe and give up or defer), BL2's listed lines, and the four lines of `log-allow-chain.txt`. Layer verified: the serial console and that log. Next: M9 (A/B selection, bootcount, rollback, FIT signatures).
