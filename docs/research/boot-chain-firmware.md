# RZ/V2L boot chain: what QEMU must provide

**Date:** 2026-10-08

**Method:** source reading and binary inspection of a Yocto build of the Renesas RZ/V2L BSP (`MACHINE=smarc-rzv2l`), plus serial console logs from the physical EVK. Paths below are relative to each upstream repository.

**Sources:**

| Component | Public source | Revision |
|---|---|---|
| TF-A | https://github.com/renesas-rz/rzg_trusted-firmware-a | `2.10.5/rz_main`, BSP 4.0.1 release tag, `f59ed5a31` |
| U-Boot | https://github.com/renesas-rz/renesas-u-boot-cip | `v2024.07/rz_dev`, `4eebfbaa4e` |
| OP-TEE | https://github.com/renesas-rz/rzg_optee-os | 4.8, `82a5cd3b` |
| Kernel | Renesas CIP kernel | 6.12.59-cip14 (`212f6e88b7`) |

The firmware build configuration was taken from the compile logs. TF-A was built with `PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0`, and OP-TEE with `PLATFORM=rz PLATFORM_FLAVOR=g2l_smarc_2` (V2L reuses the G2L flavor).

**Downstream items.** The build studied carries a few patches of its own on top of the vendor sources. Items that come from those patches rather than from the vendor BSP are marked *(downstream)*. A pure G1 build will not have them.

---

## 1. Chain at a glance

```
Mask ROM ──reads MD_BOOT (SYS_LSI_MODE[2:0])──▶ loads BL2 (512 B boot-param header, 0xAA55 sig, no checksum)
   │                                   eSD: byte 0x200 (header ×7, image @0x1000) | eMMC boot0 @0x200 (image @0x400) | QSPI @0x0 (image @0x200)
   ▼
BL2 @ 0x00012000 (SRAM, EL3)
   checks SYS_LSI_DEVID[27:0] == 0x8447447 (panics otherwise); SCIF boot mode (5) panics
   DDR init: 507 params + 5 training passes, ~11 polled conditions
   TZC-400: region 0 only (TRUSTED_BOARD_BOOT=0)
   loads FIP (eSD/eMMC byte 0x20000, SPI 0x20020000) ──params @0x2F000──▶
   ▼
BL31 @ 0x44000000 (EL3, PSCI, opteed SPD)      sec-entry 0x440000E0, CNTFRQ from SYC CNTFID0 = 24 MHz
   ├─▶ OP-TEE @ 0x44100000 (S-EL1, raw image, x0..x2 = 0)   TZDRAM 0x44100000–0x47DFFFFF, SHM 0x47E00000 (1 MiB)
   │      opens TSIP (closed library) eagerly → panics if absent
   ▼
U-Boot @ 0x50000000 (NS-EL1, SPSR 0x3C5, x1 = 0x58000000)
   mmc0 (SDHI0) → env → FIT (kernel gunzip → 0x48200000, DTB just below 0x58000000); WDT0 running
   ▼
Linux @ EL1, memory 0x48000000 + 0x78000000, PSCI via SMC
```

**Key evidence:**

| Fact | Source |
|---|---|
| U-Boot and the kernel run at EL1. `RCAR_BL33_EXECUTION_EL` is undefined under `plat/renesas/rz`, so it reads as 0, which selects EL1. | TF-A `plat/renesas/common/bl2_plat_mem_params_desc.c:18`; EVK boot log `CPU: All CPU(s) started at EL1` |
| The TZC-400 DDR secure regions exist only under `#if TRUSTED_BOARD_BOOT`, which this build sets to 0 | TF-A `plat/renesas/rz/common/plat_security.c:113-125`, `rz_common.mk:16` |
| SiP `0x82000011` (chip ID) answers secure-world callers only | TF-A `common/rz_plat_sip_handler.c:34`; `PROTECTED_CHIPID=1` in `rz_common.mk:17` and in the compile log |
| The PMIC and non-PMIC variants differ only in the DDR parameter table | TF-A V2L DDR tables; the two BL2 binaries differ by 86 bytes |

## 2. Requirements for the machine

### CPU and core

| # | Requirement | Why |
|---|---|---|
| C1 | `mp-affinity` = `0x0`, `0x100` | DT `cpu@0`/`cpu@100`; TF-A derives the core number from Aff1; Linux issues PSCI `CPU_ON(0x100)` |
| C2 | CPU `cntfrq` = 24 MHz **and** SYC `CNTFID0` reads 24 000 000 | BL31 copies CNTFID0 into CNTFRQ_EL0; the DT timer node has no `clock-frequency` |
| C3 | Direct mode enters the kernel at EL1 | matches the board (§1) |
| C4 | A55 IMPDEF sysregs: `CPUPWRCTLR_EL1` required; `CLUSTERIDR_EL1`/`CLUSTERCFR_EL1` precautionary | EXP-001 |
| C5 | MIDR identifies as Cortex-A55 | TF-A links only the A55 `cpu_ops` and panics on a mismatch |

### SoC registers that must be right even in a minimal machine

| Block | Register | Required behaviour | Consumer |
|---|---|---|---|
| SYSC | `SYS_LSI_DEVID` | low 28 bits = `0x8447447` | BL2 (panics otherwise) |
| SYSC | `SYS_LSI_MODE` @ `0x11020A00` | boot mode (`0x10200` eSD, `0x10201` eMMC, `0x10203` QSPI); MD_BOOT is bits [2:0] (HW manual §6.3.42 p.207). TF-A masks [3:0] (`plat/renesas/rz/common/drivers/sys.c:21,27`), and bit 3 reads 0 | BL2, U-Boot |
| SYSC | `RVAL`/`RVAH` | secondary-core reset vector, latched for CPU_ON | BL31 PSCI |
| SYSC | `SYS_LP_CTL5` bit (8 + core) | CPU_OFF writes `LP_CTL6`/`LP_CTL1` bit (8 + core), then polls `LP_CTL5` bit (8 + core); normally the M33 side completes it. Must read set, otherwise CPU_OFF waits forever (TF-A `plat/renesas/rz/common/plat_pm.c:92-98`) | BL31 PSCI |
| CPG | `CLK_ON_*` (0x500+n) ↔ `CLK_MON_*` (0x680+n) | the monitor register mirrors the enable register (same polarity). Linux polls it for only 10 µs with no delay, so the mirror must be computed on read | U-Boot (SDHI0 probe: 100 ms timeout → no mmc → no boot), Linux |
| CPG | `RST_*` ↔ `RSTMON_*` | **inverted** mirror: an `RST` bit of 1 means released, an `RSTMON` bit of 1 means reset applied, so RSTMON = ~RST over the implemented bits. Both Linux (`drivers/clk/renesas/rzg2l-cpg.c` `__rzg2l_cpg_assert`) and TF-A (`plat_pm.c:56-62`) poll for this; a same-polarity mirror makes every deassert time out | BL31 CPU_ON, Linux |
| CPG | `RST_CA55`, `COREn_PCHCTL`/`COREn_PCHMON` | CPU_ON: PORESET assert/deassert through `RST_CA55` with `RSTMON_CA55` polls, then a four-phase P-channel handshake. TF-A writes PCHCTL = PSTATE `0x08` (bits [23:16]) + PREQ (bit 0) and waits for PCHMON bit 0 (PACCEPT) = 1, then clears PREQ and waits for PACCEPT = 0. PACCEPT must follow PREQ (`plat_pm.c:30-70`). If `SYS_LP_CTL2` bit 0 is set, the same handshake runs first with PSTATE 0 | BL31 CPU_ON |
| WDT0 | `0x12800814` (parity-error force) | writing 1 resets the system | BL31 `SYSTEM_RESET` |
| WDT0 | counter/timeout | started by U-Boot and still running when Linux starts | U-Boot, Linux |
| SCIF0 | `0x1004B800`, RZ/SCIFA layout | `FSR` (0x08) bit 6 `TEND`, FIFO counts. The baud divisor is not enforced: U-Boot's computed divisor is wrong, yet the console works on silicon. | BL2, BL31, OP-TEE, U-Boot, Linux |
| SDHI0 | doubled register offsets, data port at 0xC0 with 64-bit access, `INFO1`/`INFO2` polls | PIO only at the U-Boot level (no DMA, HS200 or tuning) | U-Boot; Linux adds DMA |
| RPC/SPIBSC | status `TEND` | U-Boot `board_init` rewrites the SPI-NOR NVCR on every boot (1 s timeout per access) | U-Boot |
| OTP | chip ID @ `0x11861140` | read by OP-TEE (HUK derivation) | OP-TEE, BL31 |
| TSIP | `0x11850000` ("Reserved" in the HW manual) | closed microcode-FIFO protocol | production OP-TEE only (§3) |

Not touched before Linux: RIIC/PMIC (no U-Boot driver), ravb (network commands disabled).

## 3. Secure world under QEMU

- **The production OP-TEE cannot boot without TSIP.** It opens TSIP eagerly (`CFG_RZ_SCE=y`). With a read-as-zero device it prints `Failed to initialize SCE (0x00010002)` and panics. BL31 starts OP-TEE synchronously, so the boot stops before U-Boot. TSIP is driven by a closed library with an undocumented protocol, so it is classed **UNSUPPORTED / honest-fault**.
- **OP-TEE rebuilt from the same commit with `CFG_RZ_SCE=n`** uses a software RNG. At boot it touches only SCIF0 and OTP, which makes it the Stage B target.
- **The SMC instruction is the hard requirement, not OP-TEE itself.** U-Boot's OP-TEE probe and PSCI reset, Linux PSCI and the Linux optee driver all issue SMCs. EXP-001 shows that QEMU's built-in PSCI (SMC conduit) returns `NOT_SUPPORTED` for unknown SMCs, so OP-TEE's absence is soft: U-Boot skips `kaslr-seed` and the Linux optee probe fails cleanly.
- **The TZC is not enforced.** The board as built leaves DDR accessible to the normal world.

Staging A/B/C/N is defined in `docs/spec/project.md` §12 and DR-0002.

**DDR stub estimate:** two write-retaining register files (about 0x800 and 0x300 bytes) plus about 10 forced status reads, roughly 150–250 lines of C. The cheapest Stage C boot source is SPI: `TEND` plus a flash window at `0x20000000` with the FIP at +0x20000.

## 4. Loader fixup contract (direct mode in place of U-Boot)

These are the kernel-DT changes U-Boot makes at `bootm` in the studied build, and what QEMU's direct loader does about each:

| Fixup | U-Boot behaviour | QEMU direct mode |
|---|---|---|
| `/memory` | rewritten with the same value (`0x48000000`/`0x78000000`) | QEMU rewrites it from `-m` and must produce the same value |
| `/chosen/bootargs` | taken from the DTB when env `bootargs` is unset | no `-append` → preserved |
| `/chosen/u-boot,version`, `u-boot,bootconf` | added | not replicated; listed gap (informational) |
| `/firmware/optee` | *(downstream)* injected from the U-Boot control DT; the kernel DTB has no OP-TEE node | Stage A: omit; Stage B+: real U-Boot |
| `/chosen/kaslr-seed` | only when the OP-TEE RNG works | omit, or a QEMU seed listed as a gap |
| SDHI0 `vqmmc-supply` (eSD boot) | added | listed |
| `local-mac-address` | no-op without `ethaddr` | none |
| reserved-memory, `rng-seed` | none | none |

`wdt_overflow=` (a Renesas `bootm` bootargs append) reads a variable that is never assigned, so it is always 0. It is not part of the contract.

## 5. Open items

- On-board measurements in post-firmware state (U-Boot `md`): CPG `CLK_ON`/`CLK_MON`, PFC SCIF0 pin function, `SYS_LSI_MODE`, `SYS_LSI_DEVID`, `CNTFID0`.
- The exact BL2→BL31 parameter layout needed for direct BL31 entry (Stage B).
- The TSIP register map and whether access control restricts it (unknown).
