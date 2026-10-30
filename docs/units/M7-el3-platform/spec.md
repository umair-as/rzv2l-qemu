# M7-el3-platform — spec

**Milestone:** M7 (real firmware; first unit). **Requirements:** REQ-MACH-005, REQ-SYC-001, REQ-GUEST-003; REQ-CPUPWR-001 and REQ-TZC-001 proposed with this page.

## Scope

**The Renesas TF-A BL31 as the board's EL3 firmware**, in place of QEMU's built-in PSCI. A new firmware mode boots the real BL31 (G1: the Renesas vendor stack, TF-A `f59ed5a31`, the BSP's flags `PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0`), and BL31 hands over to the Renesas kernel (G1). Linux's CPU power calls then reach BL31, and BL31 drives the SoC's own core power and reset hardware. Direct mode (`-kernel` alone) stays the default and is unchanged.

- **Firmware mode** (`-bios bl31.bin -kernel Image -dtb …`). The machine does BL2's hand-off: the boot ROM and BL2 are not run (M8). What it supplies, each a recorded gap:
  - BL31 at `0x44000000` (`BL31_BASE`, TF-A `plat/renesas/rz/common/include/platform_def.h:59`).
  - The BL2→BL31 parameters at `0x0002F000` (`PARAMS_BASE`, `rz_soc_def.h:70`): the RZ `bl2_to_bl31_params_mem_t` (`include/rz_private.h:42-46`; layout in `../../research/el3-platform.md` §1), as BL2 writes it (`bl2_plat_setup.c:42-69`): a cold boot, no BL32; BL33 = the kernel at EL1h, interrupts masked, `x0` = the DTB (BL2 gives U-Boot its DTB in `x1`).
  - A six-instruction start stub at BL2's address `0x00012000`: `x0` = `0x2F000`, `x1`-`x3` = 0, branch to BL31. CPU0 starts there after every machine reset.
  - The kernel at `0x48200000` and the DTB at `0x58000000`, where U-Boot puts them on the board (research `boot-chain-firmware.md` §1), with QEMU's loader fixups (device map §4 gap 8). The DTB keeps its own `/psci` node (method `smc`); QEMU adds none.
- **No OP-TEE in this unit.** BL31's OP-TEE dispatcher warns and continues without a BL32 (`services/spd/opteed/opteed_main.c:139-142`). OP-TEE (`CFG_RZ_SCE=n`) and U-Boot are the next unit.
- **Core power and reset**, the path BL31's PSCI takes (`plat_pm.c:30-150`):
  - SYSC `SYS_CA55_CFG_RVAL0/1`, `RVAH0/1` (manual §6.3.38-6.3.41 p.205-206): the reset vector each core starts from.
  - SYSC `SYS_LP_CTL1/2/5/6` (§6.3.54-6.3.57 p.219-224): a core's sleep request sets its `LP_CTL5` flag; `LP_CTL2` bit 0 marks the sleep sequence.
  - CPG `RST_CA55` (§7.2.4.106 p.377-379) with `RSTMON_CA55`, and `CORE0/1_PCHCTL`, `PCHMON` (§7.2.4.186-7.2.4.189 p.464-467): the P-Channel handshake (§2.2 p.84-89) accepts each request; a core starts at its reset vector when its resets are released and the channel accepts ON, and stops when its reset is applied or the channel accepts OFF.
- **TZC-400 ×4** (§13 p.622-626, `0x11040000`-`0x11070000`): BL31 programs the two SRAM controllers (`plat_security.c:154-155`). A register file with the build values; programming is stored, never enforced (device map §4 gap 9).
- **SYC**, the system counter (§15, a CoreSight SoC-400 timestamp generator): BL31 writes `CNTFID0` and `CNTCR` (`drivers/syc.c`).
- **GIC-600 `GICR_PWRR`** (GIC-600 TRM §3.6.1, §4.4.5): the Redistributors are powered down at reset and BL31 powers them up.
- **Cortex-A55 `CPUPWRCTLR_EL1`**: BL31's core power-down writes it (EXP-001: QEMU's Cortex-A55 does not define it).
- **System reset:** BL31's `SYSTEM_RESET` forces a WDT0 parity error (`plat_pm.c:116-136`, `drivers/wdt.c`), already modelled in M4. The machine reset repeats the staging.
- **Not in this unit:** BL2, the boot ROM and DDR (M8); OP-TEE and U-Boot (next unit); PSCI `SYSTEM_OFF`, which this BL31 does not implement (`plat_pm.c:109-114`: `wfi`, then an error and a panic), so `poweroff` does not end QEMU, as it does not power the board off; cluster power-down.

## What the guest needs

BL31 (`plat/renesas/rz/common/`, TF-A `f59ed5a31`), in the order it runs:

1. Entry at EL3 with `x0` = the parameter block; it copies the block (`bl31_plat_setup.c:58`).
2. SCIF0 from reset values (`console_rz_register`), the SYC counter (`syc_init`, `CNTFID0`), the generic timer.
3. TZC-400 at `0x11050000` and `0x11040000`: `BUILD_CONFIG` for the number of filters, region 0 and the region registers (`plat_security.c:76-110`).
4. GIC-600 as distributor and redistributor owner at EL3 (`plat_gic.c`).
5. PSCI: `CPU_ON` (resets, reset vector, P-Channel), `CPU_OFF` (`LP_CTL6`, `LP_CTL1`, poll `LP_CTL5`, `LP_CTL2`), `SYSTEM_RESET` (WDT0).

The kernel (G1, as in M4) needs from BL31: PSCI 1.x over SMC, `CPU_ON(0x100)` to bring CPU1 up, and the same SoC state it has in direct mode.

**Start states:** in firmware mode the new SYSC registers, the P-Channels, the TZCs and the SYC start from manual reset values, and CPU1 is off until BL31 starts it; the CPG clocks and resets, the PFC and SCIF0 keep the direct-mode start values (see "For the operator", gap 19). In direct mode the SYC starts as the EVK reads after the firmware (`CNTCR` 1, `CNTFID0` `0x016E3600`, EVK-R50, O); the new SYSC registers and the TZCs start from reset values there too (I: BL31 writes `RVAL1` only at `CPU_ON`, and nothing in direct mode reads the TZCs).

## Exit criterion

1. qtests assert the manual reset values and rules: `RVAL/RVAH`, `LP_CTL5` set by a sleep request and cleared by a 0 write, `PCHCTL` reset value and `PACCEPT` following `PREQ`, the TZC-400 build values; each seen red on a mutation.
2. The CPG's core run lines follow the manual's start and stop conditions (qtest), and in firmware mode the real CPU1 runs from the reset vector BL31 programs, stops at `CPU_OFF` and runs again at `CPU_ON` (the acceptance below); each seen red on a mutation.
3. Firmware mode, G1 kernel: the BL31 banner on SCIF0; Linux to the shell; both CPUs online through BL31's `CPU_ON`; CPU1 offline and online again; `reboot` resets the board through WDT0 and BL31 starts again in the same QEMU; the kernel reports the PSCI version from BL31.
4. Direct mode: M1-M5 acceptance and the serial-port regression suite pass unchanged.

## Evidence

Manual sections above; TF-A `f59ed5a31` paths above; `../../research/boot-chain-firmware.md` §1-§3; register table in `../../research/el3-platform.md`.

## For the operator

- **Clocks and pins in firmware mode.** Without BL2, nothing sets the clocks and pins that BL2 and U-Boot set on the board. This unit keeps the direct-mode start values for the CPG, PFC and SCIF0 (the post-U-Boot state measured on the EVK) in firmware mode too, and records that as a gap. The alternative, starting them from reset values, needs BL2's clock setup (M8) or U-Boot's (next unit).
- **Linux as BL33** is a staging step: the board always runs U-Boot there. The next unit puts U-Boot in its place.
- **TZC-400 build values:** the manual gives the regions and filters (§13.1), not the address width; the model's 32 and 33 bits are an assumption until read on the EVK (`docs/evidence/requests.md`, `BUILD_CONFIG` at `0x11040000`-`0x11070000`).
- **Simplifications to accept or reject** (device map §4 gaps 19-21): firmware mode's staging; the system counter runs whatever `CNTCR.EN` says; every P-Channel request is accepted at once and a core stops at its OFF handshake or reset, not at its WFI.

## Unit end

- **Met:** exit criteria 1-3; criterion 4 by the cumulative run recorded in `tasks.md`. Firmware mode boots the vendor kernel on the real BL31 to a shell from the SD card, both CPUs through BL31's `CPU_ON`; CPU1 goes offline and online twice; `reboot` restarts the board through WDT0 into BL31 again. The kernel now sees `SMC Calling Convention v1.4` and `MIGRATE_INFO_TYPE not supported`, as on the board (direct mode: v1.0, gap 1).
- **Found in the failure loop (O, model):** BL31 stopped, in order, at the SYC (`0x11000020`), TZC1 (`0x11050000`), the GIC-600's `GICR_PWRR`, SYSC `LP_CTL2`, CPG `CORE1_PCHCTL`, and (at `CPU_OFF`) the Cortex-A55's `CPUPWRCTLR_EL1`; each is modelled now. A first parameter block used the R-Car layout of the same structure name; BL31 then found no BL33 and took a data abort at EL3 (`FAR` `0x4`); the layout is now taken from the RZ header and checked against BL31's code.
- **Not seen:** PSCI `SYSTEM_OFF` is not implemented by this BL31 (`wfi`, then a panic), so `poweroff` does not end QEMU in firmware mode, as it does not power the board off.
- **Next (M7, layer verified: BL31 PSCI to the Linux kernel):** OP-TEE built with `CFG_RZ_SCE=n` as BL32 and the vendor U-Boot as BL33, loading the kernel from the SD card (a FAT boot partition on p1); U-Boot's SDHI PIO path and its RPC/SPI-NOR accesses.
