# M7-optee-uboot — spec

**Milestone:** M7 (real firmware; second unit). **Requirements:** REQ-MACH-005, REQ-GUEST-003 (OP-TEE's `CFG_RZ_SCE=n` is the spec's recorded exception, §12). **Status:** planned; implementation follows after M7-el3-platform merges.

**Acceptance is vendor-only (G1):** the unmodified vendor TF-A, OP-TEE and U-Boot builds and the vendor kernel. OP-TEE running as BL32, and what the secure world changes in PSCI, are M7 results; Linux using OP-TEE (`/dev/tee0`) is not. The product-side (G2) experiment below is separate and never a build dependency.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). Sources: TF-A `f59ed5a31`, OP-TEE `82a5cd3b` (`github.com/renesas-rz/rzg_optee-os`), U-Boot `4eebfbaa4e` (`github.com/renesas-rz/renesas-u-boot-cip`, `smarc-rzv2l_defconfig`), all as pinned in `../../sources.md`.

## Scope

**Stage B of spec §12: the board's BL31, then OP-TEE, then U-Boot, which loads Linux from the SD card.** Firmware mode (M7-el3-platform) already runs BL31 and stages BL2's hand-off; this unit fills in the two images BL2 loads besides BL31, so the chain after BL2 is the board's own.

- **OP-TEE as BL32**, rebuilt from the vendor commit with the BSP's flags (`PLATFORM=rz PLATFORM_FLAVOR=g2l_smarc_2 CFG_ARM64_core=y CFG_REE_FS=y CFG_RPMB_FS=n CFG_CRYPTO_WITH_CE=n`) and **`CFG_RZ_SCE=n`**: the production build opens the closed TSIP crypto engine eagerly and panics without it (`../../research/boot-chain-firmware.md` §3). A recorded gap (spec §12, REQ-GUEST-003's exception). Raw image `tee-raw.bin` at `0x44100000`, Secure EL1, `x0`-`x2` = 0; TZDRAM `0x44100000`-`0x47DFFFFF`, shared memory `0x47E00000` (1 MiB) (research §1).
- **U-Boot as BL33**, the vendor build of `smarc-rzv2l_defconfig`: `u-boot.bin` at `CONFIG_TEXT_BASE` `0x50000000`, Non-secure EL1h, interrupts masked (`spsr` `0x3c5`), as BL2 sets it (research `el3-platform.md` §1).
- **The machine's BL2 stand-in** fills the parameter block's BL32 and BL33 entries (`include/rz_private.h:42-46`) from the images it is given, and loads each where BL2 would. **BL32's `args.arg0` must be `MODE_RW_64`** (0, `include/arch/aarch64/arch.h:865`): BL31's OP-TEE dispatcher takes OP-TEE's execution state from it (`services/spd/opteed/opteed_main.c:153`, `OPTEE_AARCH64` = `MODE_RW_64`, `opteed_private.h:42`); `arg1`-`arg3` (pageable part, memory limit, DT address) are 0. The stand-in writes it explicitly, not as a side effect of zeroing the block. The vendor BL2 copies BL32's entry from its image descriptor (`plat/renesas/rz/common/bl2_plat_setup.c:55-57`), which sets `pc` and `spsr` but no arguments (`bl2_plat_mem_params_desc.c:46-49`); the product build patches BL2 to set it because OP-TEE 4.x started in the wrong mode otherwise (edge-ai-yocto `0001-rz-common-bl2-parse-optee-header-for-BL32.patch`; G2, a lead). Whether the unpatched vendor BL2 gets it right is M8's question, with BL2 itself. How the images are named on the command line is a design choice (below). With U-Boot as BL33, the machine stages no kernel and applies no loader fixups: U-Boot makes its own.
- **The SD card** carries what the BSP's root file system carries: `boot/Image` and `boot/r9a07g054l2-smarc.dtb` on the ext4 partition 2. U-Boot's default command (`include/configs/smarc-rzv2l.h:34-43`) is `env default -a; run bootcmd_check; run bootimage`: `mmc dev 1` (the carrier slot, SDHI1) if a card is there, else mmc 0 (SDHI0); `ext4load mmc N:2 0x48080000 boot/Image`, the DTB to `0x48000000`, `root=/dev/mmcblkNp2`, then `booti 0x48080000 - 0x48000000`. The card image gets a `/boot` (`tests/guests/sd/`); no guest file is edited.
- **Blocks U-Boot touches beyond Linux's**, each mapped with its device-map class as the failure loop meets it:
  - RPC/SPIBSC `0x10060000`: `s_init` writes `CMNCR`; `board_init` reads and rewrites the SPI-NOR's NVCR through it every boot (`board/renesas/rzv2l-dev/rzv2l-dev.c:171-226`; polls `TEND`, 1 s timeout per device map). Today a stub. If U-Boot continues after the bounded failure, the missing flash is a recorded gap here and the RPC + SPI-NOR model is its own unit (spec §11: "functional by M7"; M8's SPI boot needs it too).
  - DDR controller `0x11410000 + 0x18C`: U-Boot reads the ECC enable bits [25:24] to pick its device tree (`board_fit_config_name_match`); 0 selects `smarc-rzv2l`. Needs the board's value (EVK-R80) before a model value is written.
  - USB PHY control and the two OHCI hosts (`board_usb_init`): stores into the existing stubs.
  - WDT0: U-Boot starts it (60 s) and Linux takes it over (M4 model). Whether the vendor kernel keeps it fed without a user-space daemon is checked by the run outliving the timeout (I: the watchdog core pings a running watchdog until user space opens it, if the driver reports it running).
  - OTP `0x11860000` (chip ID `0x11861140`): OP-TEE's hardware unique key (research §1-§3); a stub with a documented value, not silicon's (device map).
- **What Linux sees of OP-TEE:** BL31's OP-TEE dispatcher registers its PSCI hooks once OP-TEE is up, so `MIGRATE_INFO_TYPE` answers 2, `Trusted OS migration not required`, as on the board (EVK-L07; `services/spd/opteed/opteed_main.c:568`). The Linux OP-TEE driver does not probe on the vendor stack, because no device tree Linux gets has `/firmware/optee`:
  - the vendor kernel's `r9a07g054l2-smarc.dtb` (`rz-6.12-cip14` `212f6e88b7`) has no such node, not even a disabled one (F, `dtc` of the built DTB);
  - the vendor U-Boot's effective configuration (`smarc-rzv2l_defconfig` at `4eebfbaa4e`, generated `.config`) has `CONFIG_TEE=y`, `CONFIG_OPTEE=y`, `CONFIG_OPTEE_LIB=y` (default from `OPTEE`, `lib/optee/Kconfig:3`) and `CONFIG_OF_LIBFDT=y`, so the real `optee_copy_fdt_nodes()` is built, not the empty stub (`include/tee/optee.h:59-66`). `booti` reaches it through `image_setup_linux()` (`arch/arm/lib/bootm.c:214`, `boot/image-board.c:904`, `boot/image-fdt.c:608`); it copies `/firmware/optee` from U-Boot's own DT into the kernel's, and does nothing when U-Boot's DT has no such node (`lib/optee/optee.c:121-126`). Neither DT U-Boot builds (`CONFIG_OF_LIST` `smarc-rzv2l smarc-rzv2l-ecc`) has one (F).
  
  **History (F):** Renesas's 5.10 kernels carried the node in `r9a07g054.dtsi`, disabled (`rz-5.10-cip41`, `rz-5.10-cip54`), and the RZ/V2L Security Package v3.2.0.0 (Yocto dunfell, OP-TEE 3.19, U-Boot 2021.10) enabled it with a kernel patch (`meta-rz-security/recipes-kernel/linux/linux-renesas/g2l/0001-arm64-dts-renesas-r9a07g0-43-44-54-enable-OP-TEE.patch`). From `rz-6.1-cip` on, the node is gone from the vendor kernel; no vendor U-Boot RZ/V2L DT has it (`v2021.10/rz`, `v2024.07/rz`). The board's product image puts it in U-Boot's DT instead (edge-ai-yocto `0004-smarc-rzv2l-dts-add-optee-firmware-node-for-rng.patch`; G2). That is the experiment below, not acceptance.
- **CPU power with OP-TEE present:** `CPU_ON` and `CPU_OFF` now also enter OP-TEE on the core concerned (the dispatcher's `cpu_on_finish` and `cpu_off` hooks). The hotplug and reset checks of unit 1 are repeated with OP-TEE in the chain.
- **Honest failures:** the SPI-NOR path and every other block without a model fail visibly (a timeout, an error status, an abort, a `-d unimp` line); no stub reports a command as done that it did not do.
- **Not in this unit:** BL2, the boot ROM, DDR training and a FIP (M8); the production OP-TEE with TSIP: the negative Stage N needs a production binary, which cannot be built from public sources; it stays unavailable until a suitable legitimate binary exists, and no synthetic result stands in for it; FIT images, with signed boot and the rest of the security scope (M9: M7 follows the vendor's own `booti` path), and U-Boot's A/B and bootcount paths (M9); `saveenv` (the environment at `0x1F0000` on mmc 0 is only read; `env default -a` runs first anyway).

## Design choices for the operator

1. **How the images are named.** Recommended: machine properties, `-machine rzv2l-smarc,bl32=tee-raw.bin,bl33=u-boot.bin` with `-bios bl31.bin`; `-kernel`/`-dtb` are then not needed. The machine keeps the whole BL2 stand-in in one place, and the parameter block is filled from what was given. The alternative, `-device loader` for each image plus entry-point properties, is generic QEMU but leaves the user to know BL2's addresses.
2. **The SPI flash.** Recommended: stub first, model later. The flash is not on U-Boot's boot path (the kernel comes from the SD card). The stub never sets `TEND` or returns flash data, so U-Boot's NVCR access times out and U-Boot reports it. If U-Boot then continues, the RPC + SPI-NOR (QEMU has an `mt25qu512a` flash model) becomes M7 unit 3, before M8 needs it to boot from SPI.

## G2 integration experiment (not acceptance)

A recorded experiment (`docs/experiments/`, when it runs), independent of the exit criterion. It restores OP-TEE device-tree discovery on our newer vendor stack, the part of the 5.10 Security Package's OP-TEE support that the 6.1+ kernels dropped (History, above), in the place the product image puts it. It does not restore the rest of that package (TSIP crypto, secure boot, its OP-TEE 3.19 build). The only change from the acceptance stack: U-Boot built with the product's one-node patch to `arch/arm/dts/smarc-rzv2l.dts` (edge-ai-yocto `0004-smarc-rzv2l-dts-add-optee-firmware-node-for-rng.patch`), applied by the experiment's own script; the acceptance build scripts never apply it and do not depend on it. The patch touches only the non-ECC DT, so the experiment holds only while the model's DDR ECC bits select `smarc-rzv2l` (EVK-R80). User space needs `tee-supplicant` and `xtest` on the card (OP-TEE client and test from their public sources). Each result is reported separately, and a later one is not claimed from an earlier one:

1. **Node propagation:** `/proc/device-tree/firmware/optee` exists in Linux, copied by U-Boot (`compatible` `linaro,optee-tz`, `method` `smc`).
2. **Driver and `/dev/tee0`:** the Linux OP-TEE driver probes (its `dmesg` lines, revision and capabilities as OP-TEE reports them) and `/dev/tee0` and `/dev/teepriv0` exist.
3. **`tee-supplicant`:** it starts and opens `/dev/teepriv0`; the REE file system path it serves works (`CFG_REE_FS=y`).
4. **`xtest`:** the suites that run, with pass/fail counts; failures are listed with their cause. Known limits before running: no TSIP-backed crypto or hardware RNG (`CFG_RZ_SCE=n`, so the product's `kaslr-seed` path and `CFG_HWRNG_PTA` are absent), no RPMB (`CFG_RPMB_FS=n`), and OP-TEE's unique key from the OTP stub, not silicon.

## What the guest needs

In order (research `boot-chain-firmware.md` §1, the EVK's boot of 2026-11-01 for the order of lines):

1. BL31 as in unit 1, then `opteed_setup` finds BL32's entry in the parameter block and enters OP-TEE at S-EL1 (`opteed_main.c`).
2. OP-TEE: console on SCIF0, OTP for its unique key, its memory map; `I/TC: Primary CPU switching to normal world boot`, back to BL31.
3. BL31 enters U-Boot at `0x50000000`, `x1` = its device tree address.
4. U-Boot: CPG and PFC (modelled), `s_init` (PFC, CPG resets, RPC `CMNCR`), DRAM size (the model's `0x78000000`: `DRAM: 1.9 GiB` as on the board), `board_init` (SPI-NOR NVCR, USB), WDT0 start, SDHI0/1 in PIO mode (M5), the environment, the OP-TEE probe by SMC, the default command.
5. Linux from the card, the same kernel and shell as M5, with BL31 + OP-TEE behind PSCI.

## Exit criterion

`scripts/run.sh` in the new mode boots, on SCIF0: the BL31 banner; OP-TEE's banner and `Primary CPU switching to normal world boot`, with no `opteed_fast` error; the U-Boot banner and `DRAM:  1.9 GiB`; U-Boot loads `boot/Image` and the DTB from the card and starts Linux; `psci: Trusted OS migration not required` and `SMC Calling Convention v1.4`; both CPUs; the shell from the card's root. Then CPU1 offline and online twice and `reboot` back through BL31, OP-TEE and U-Boot, and a run that outlives the 60 s watchdog. Every `-d unimp,guest_errors,invalid_mem` line is a recorded stub window. No `/dev/tee0` is expected: Linux's OP-TEE driver does not probe on this stack (above). Firmware mode without OP-TEE and U-Boot (unit 1) and direct mode are unchanged.

Expected next stop: U-Boot's SPI-NOR probe, if the stub is not enough to fail it within its timeout.

## Evidence

- Manual: SPI Multi I/O Bus Controller (RPC) §25 p.1474, OTP Table 5.1 p.143, DDR controller Table 5.1 p.144.
- Research: `../../research/boot-chain-firmware.md` §1-§4, `../../research/el3-platform.md`.
- EVK: `../../evidence/EVK-2026-11-01-firmware.md` (PSCI answers with OP-TEE; the boot chain's banners); EVK-R80 (DDR ECC enable, requested).
