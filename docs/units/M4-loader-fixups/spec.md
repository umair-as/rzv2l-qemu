# M4-loader-fixups — spec

**Milestone:** M4 (second unit). **Requirement:** REQ-GUEST-005 (in direct mode, the QEMU loader applies the G1 loader fixup contract or lists each omission).

## Scope

**Direct mode** is QEMU loading the kernel and device tree itself (`-kernel`, `-dtb`) instead of running firmware. On the board, the vendor U-Boot (G1: `renesas-u-boot-cip` `4eebfbaa4e`, `../../sources.md`) edits the kernel's device tree in `image_setup_libfdt()` before it starts Linux. This unit makes QEMU's loader apply each edit the vendor U-Boot makes, or lists it as a fidelity gap. The edits of the G2 image's own U-Boot patches are studied, not modelled.

| Edit (U-Boot `4eebfbaa4e`) | When, on the board | QEMU direct mode |
|---|---|---|
| eSD supplies: `ft_verify_fdt` sets `/soc/mmc@11c00000` `vmmc-supply` = `<&/regulator-vcc-sdhi0>` and `vqmmc-supply` = `<&/regulator-vccq-sdhi0>` (`board/renesas/rzv2l-dev/rzv2l-dev.c:269-292`, `board/renesas/rzg-common/update_fdt.c:162-246`, called at `boot/image-fdt.c:654`) | `SYS_LSI_MODE[2:0]` = 0 (eSD); observed on the EVK (O, EVK evidence §4) | **applied** from the machine's `boot-mode` (the pins `SYS_LSI_MODE` latches). The DTBs have no `/regulator-vcc-sdhi0`, so `vmmc-supply` keeps its value (C: the old value is read from the working FDT, `update_fdt.c:172`, which `boot_relocate_fdt()` sets to the blob being edited, `image-fdt.c:271-272`; a missing regulator leaves it, `update_fdt.c:84-85,173-178`); `vqmmc-supply` becomes the phandle of `/regulator-vccq-sdhi0` (G0 and G1: `0x18` → `0x74`) |
| `/memory` rewritten from U-Boot's DRAM bank (`image-fdt.c:603`) | always | already applied: QEMU writes `0x48000000`/`0x78000000`, the same value |
| `/chosen/u-boot,version` (`boot/fdt_support.c:328`) | always | **gap**: QEMU is not U-Boot and does not claim a version. No G0 or G1 kernel code reads it (C) |
| `/chosen/bootargs` from env `bootargs` (`fdt_support.c:315-319`) plus ` wdt_overflow=0` (`arch/arm/lib/bootm.c:205-210`) | vendor `bootcmd` sets `rw rootwait earlycon root=/dev/mmcblk{1,0}p2` (`include/configs/smarc-rzv2l.h:49-58`); the flag is never assigned, so always 0 | **gap**: `-append` is the env's place; without it the DTB's bootargs stay. ` wdt_overflow=` is not appended: only the R-Car watchdog driver parses it (`drivers/watchdog/renesas_wdt.c:172`), which RZ/V2L does not bind |
| `/firmware/optee` (`image-fdt.c:608`, `lib/optee/optee.c:121-126`) | only if U-Boot's own DT has the node; the vendor's has none | none needed (G2: patch adds the node) |
| `/chosen/kaslr-seed` from the OP-TEE RNG (`ft_board_setup`, `image-fdt.c:627-640`) | never with the vendor code: `OF_BOARD_SETUP` is on (`RCAR_GEN3` selects `RCAR_64`, which selects it, `arch/arm/mach-renesas/Kconfig:8,30`), but the vendor `ft_board_setup()` only scrubs duplicate `/memory` nodes and updates an RPC node these DTBs lack (`board/renesas/rcar-common/common.c:243-250`); the G2 patches add the seed (EVK: `[EDGE] UBOOT kaslr-seed=ok`) | none needed (G2). G1 is built without `RANDOMIZE_BASE`; G0 prints `KASLR disabled due to lack of seed`, as it would under the vendor U-Boot |
| `u-boot,bootconf` (`image-fdt.c:615-619`) | FIT images only; the vendor boots `booti` | none needed (G2 boots a FIT) |
| `linux,initrd-*` (`image-fdt.c:651`) | no initrd (`booti … -`) | QEMU adds them for `-initrd` (existing gap 8 note) |
| `local-mac-address` (`image-fdt.c:622`) | env `ethaddr` only. `NET_RANDOM_ETHADDR=y` sets a random one when the Ethernet driver probes, but the vendor `bootcmd` starts with `env default -a`, which drops it before `booti` (I, not checked on the EVK) | none |
| root `serial-number` (`fdt_root`, `boot/fdt_support.c:202-205`) | env `serial#` only; the vendor env sets none | none |
| `/chosen/stdout-path` from the console alias | only with `OF_STDOUT_VIA_ALIAS`, not set in the vendor `defconfig` (`fdt_support.c:176-179`) | none |
| `/psci` | as in the DTB | replaced by QEMU (gap 7, unchanged) |

**Firmware mode** (no `-kernel`): the loader makes no edits; a real U-Boot does them (M7).

## What the guest needs

`mmc_regulator_get_supply()` looks up `vmmc` and `vqmmc` (linux v6.12.59 and rz_linux-cip `212f6e88b7` `drivers/mmc/core/regulator.c:253-254`); the SDHI driver switches the I/O voltage through `vqmmc` (`drivers/mmc/host/renesas_sdhi_core.c:282` in G0, `:285` in G1). The SD host is still a stub, so the effect becomes visible in M5. No register is involved: the unit is a device-tree contract.

## Exit criterion

1. `tests/acceptance/m4/loader-fixups.sh`: for the G0 and G1 DTBs, the DTB handed to the kernel (`-machine dumpdtb`) has, in eSD mode, `vqmmc-supply` = the phandle of `/regulator-vccq-sdhi0` and `vmmc-supply` unchanged; in boot modes 1-5 both unchanged; in all modes, no difference but `/psci`. A regulator without a phandle gets the highest phandle + 1, as U-Boot's `fdt_generate_phandle()`. Each check seen red on a mutation.
2. M4 acceptance (G1 shell, watchdog, M3/M2/M1) still passes.

## Evidence

EVK evidence §4 (`../../evidence/EVK-2026-10-30-linux.md`, O: the U-Boot log of the edits); vendor U-Boot `renesas-u-boot-cip` `4eebfbaa4e` (C, lines above; `smarc-rzv2l_defconfig` read, no effective `.config` of a vendor build available: Kconfig defaults assumed for options it does not set, A); effective kernel `.config` files in `tests/guests/out/`.

## For the operator

- **Not written: `u-boot,version`, ` wdt_overflow=0`.** Both would claim a firmware that did not run, and no guest code reads them (C). Listed as gaps.
- **The EVK's live device tree was not read** (it runs a G2 DTB, where the regulator's phandle is `0x81`). A live check under Linux would need a login; the U-Boot log already shows the edit.

## Next blocker

None in this unit: the G1 boot is unchanged. M5 (SD host) is next.
