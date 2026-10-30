# The EL3 platform: what TF-A BL31 needs from the SoC

What the board's BL31 (TF-A `f59ed5a31`, `PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0`; paths under `plat/renesas/rz/common/` unless named) reads and writes, from entry to Linux and through PSCI. Labels: (F) fact from the manual or the source, (I) inference, (A) assumption. The unit is [M7-el3-platform](../units/M7-el3-platform/spec.md); the boot chain is in [boot-chain-firmware.md](boot-chain-firmware.md).

## 1. Entry: BL2's hand-off

- BL31 runs at `0x44000000` (`include/platform_def.h:59`), entered at EL3 with `x0` = `PARAMS_BASE` = `0x0002F000` (`include/rz_soc_def.h:70`; `bl2_plat_mem_params_desc.c`, BL31 entry) (F).
- The block is the RZ `bl2_to_bl31_params_mem_t` (`include/rz_private.h:42-46`), not the R-Car one of the same name (`plat/renesas/common/include/rcar_private.h`): `boot_kind` at 0 (0 = cold boot), BL32 `entry_point_info_t` at 8, BL33 at 96, 184 bytes; an entry point is 88 bytes: header (type 1, version 2, size 88, attributes), `pc` at +8, `spsr` at +16, `args` at +24 (F: compiled against the headers, and BL31's `bl31_plat_get_next_image_ep_info` reads `from_bl2 + 0x60` for the non-secure image).
- BL2 zeroes the block and copies the entry point of each image it loaded (`bl2_plat_setup.c:42-69`); BL33 is U-Boot at `0x50000000`, EL1h with DAIF masked (`spsr` `0x3c5`), `x1` = its device tree (`bl2_plat_mem_params_desc.c`, BL33 entry) (F).
- BL31 copies the block once, in `bl31_early_platform_setup2` (`bl31_plat_setup.c:58`), and returns NULL for an image whose `pc` is 0 (`:89-100`) (F). Without a BL32 the OP-TEE dispatcher prints `Error initializing runtime service opteed_fast` and BL31 continues (`services/spd/opteed/opteed_main.c:139-142`) (F; seen in the model).

## 2. Registers in scope

| Block, offset | Register | Reset (manual) | Fields used | Class | BL31 `file:line` | Cite |
|---|---|---|---|---|---|---|
| SYC `+0x000` | `CNTCR` | 0 (A: CoreSight SoC-400 TRM, not in the repo); EVK after firmware `0x1` (O, EVK-R50) | EN | config | `drivers/syc.c:29` | §15.3 p.727 → CoreSight SoC-400 TRM 3.10 |
| SYC `+0x020` | `CNTFID0` | 0 (A: as above); EVK after firmware `0x016E3600` (O, EVK-R50) | frequency, 24 000 000 written | config | `drivers/syc.c:34` | as above |
| TZC0/1 `+0x000` | `BUILD_CONFIG` | configuration | `NO_OF_FILTERS` | ID | `drivers/arm/tzc/tzc400.c:206` | §13.1 p.622-623 (8 regions + base; 1 filter, DDR 4) |
| TZC0/1 `+0x008` | `GATE_KEEPER` | 0 | open request, open status (polled) | command / status | `tzc400.c:171-175` | TZC-400 TRM (not in the repo) |
| TZC0/1 `+0x100 + 0x20n` | region base, top, attributes, ID access | 0 | all | config | `plat_security.c:76-110` | as above |
| GIC-600 `GICR +0x024` | `GICR_PWRR` | RDPD = 1 (§3.6.1) | RDPD (written 0, polled), RDGPD = RDGPO (polled) | command / status | `drivers/arm/gic/v3/gic-x00.c:61-86` | GIC-600 TRM §3.6.1, §4.4.5 |
| SYSC `+0x858/0x85C`, `+0x860/0x864` | `CA55_CFG_RVAL0/RVAH0`, `RVAL1/RVAH1` | 0 | address [31:2], [39:32] | config | `plat_pm.c:52-53` | §6.3.38-6.3.41 p.205-206 |
| SYSC `+0xD04` | `LP_CTL1` | 0 | `CA55SLEEP_REQ` [9:8] | command | `plat_pm.c:95` | §6.3.54 p.219 |
| SYSC `+0xD08` | `LP_CTL2` | 0 | `CA55_STBYCTL` [0] | config (read by CPU_ON) | `plat_pm.c:42, 101` | §6.3.55 p.220 |
| SYSC `+0xD14` | `LP_CTL5` | 0 | `CA55SLEEPn_F` [9:8], 0 write clears | status (polled) | `plat_pm.c:97-99` | §6.3.56 p.221 |
| SYSC `+0xD18` | `LP_CTL6` | 0 | `CA55SLEEPn_E` [9:8] | config | `plat_pm.c:92` | §6.3.57 p.223 |
| CPG `+0x800` | `RST_CA55` | `0x00001fff` | `UNITn_RSTB` [12:0] under `WEN` [28:16] | command | `plat_pm.c:56-62` | §7.2.4.106 p.377-379 |
| CPG `+0x980` | `RSTMON_CA55` | computed | reset applied | status (polled) | `plat_pm.c:57-62` | §7.2.4.144 p.420 |
| CPG `+0xB3C/0xB44` | `CORE0/1_PCHCTL` | `0x00080000` | `PSTATE` [21:16], `PREQ` [0] | command | `plat_pm.c:43-48, 65-69` | §7.2.4.187, 7.2.4.189 p.465, 467 |
| CPG `+0xB38/0xB40` | `CORE0/1_PCHMON` | `—` | `PACCEPT` [0] (polled), `PDENY` [1] | status | as above | §7.2.4.186, 7.2.4.188 p.464, 466 |
| WDT0 `+0x014` | `PEEN` | 0 | 1 forces a parity error: system reset | command | `drivers/wdt.c` | §21 (modelled in M4) |
| A55 `S3_0_C15_C2_7` | `CPUPWRCTLR_EL1` | 0 (A55 TRM) | `CORE_PWRDN_EN` set before the last WFI | config | `lib/cpus/aarch64/cortex_a55.S` (`cortex_a55_core_pwr_dwn`) | EXP-001 (QEMU UNDEFs it) |

**Direct-mode start state (rule 9):** SYC as read on the EVK at the U-Boot prompt, `CNTCR` `0x1`, `CNTFID0` `0x016E3600` (O, EVK-R50, [evidence](../evidence/EVK-2026-10-29-post-firmware.md)); the SYSC reset-vector and sleep registers, the P-Channels and the TZCs at their reset values (I: no direct-mode guest touches them, and BL31 writes `RVAL1` only at `CPU_ON`).

## 3. The core power sequences

- **CPU_ON** (`plat_pm.c:30-70`) (F): if `LP_CTL2` bit 0 is set (the core went through `CPU_OFF`), a P-Channel handshake to OFF (`PCHCTL` = PREQ, wait PACCEPT, clear PREQ, wait); the reset vector into `RVALn/RVAHn`; `RST_CA55` = `0x00010000 << n` (apply `CA55_RST1_n`), wait `RSTMON` bit n set; `0x00050005 << n` (release `CA55_RST1_n` and `CA55_RST3_n`), wait clear; a handshake to ON (`PCHCTL` = `0x00080001`, wait, `0x00080000`, wait).
- **CPU_OFF** (`plat_pm.c:83-104`) (F): GIC CPU interface off; `LP_CTL6` = `0x100 << n`, `LP_CTL1` = `0x100 << n`; wait for `LP_CTL5` bit 8 + n; `LP_CTL2` = 1; then the generic PSCI code writes `CPUPWRCTLR_EL1` and executes WFI.
- **The manual's flows** (§2.2.1-2.2.2 p.85-89) (F) do the same steps in another order: the core warm-reset release releases the resets first, then hands the P-Channel to ON. The manual's core 0 warm reset sets `0x1FFF1FF7` and confirms `RSTMON` = `0x4`, its core 1 variant `0x1FFF1FFB` and `0x8`: bit 3 cleared for core 0 but bit 2 confirmed. Record: a conflict inside §2.2.2; BL31 and §2.2.1 agree that bit n + 2 belongs to core n (`0x00050005 << n`), and the model follows them.
- **Model (I):** a core runs while its channel last accepted ON and both its reset terminals are released; it stops at an OFF handshake or a reset. BL31's order then starts the core at the reset release and the ON handshake finds it running; the manual's order starts it at the handshake. Neither order lets software see a difference in the model.
- **Who answers the sleep request (A):** BL31's comment says the Cortex-M33 completes it (`plat_pm.c:97`). The manual's `LP_CTL5` flag is the request itself ("Sleep Mode request (SYS_LPM_INT interrupt occurs)", §6.3.56); the model sets it when an unmasked request arrives, which is all BL31 waits for.

## 4. Not in scope

The cluster P-Channel and cluster resets (§2.2.3), `RMR_EL3` warm reset, the SYC read frame and count, TZC failure reporting and enforcement, OP-TEE's OTP and TSIP accesses, U-Boot's accesses (next unit), BL2 (M8).
