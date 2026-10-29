# EVK post-firmware register reads — 2026-10-29

**Board:** RZ/V2L SMARC EVK (2 GB variant), console SCIF0 at 115200 8N1.
**Image:** downstream (G2) image built on the Renesas BSP. Not built by this project, so every finding below is labelled as from this firmware:

| Component | Banner | Pinned in `../research/boot-chain-firmware.md` | Match |
|---|---|---|---|
| TF-A BL2/BL31 | `v2.10.5(release):2.10.5/rz_1.1.0-dirty`, `Built : 13:04:30, Sep 25 2025` | `2.10.5/rz_main`, `f59ed5a31` | **no**: different branch name, local changes (`-dirty`), no commit in the banner |
| OP-TEE | `82a5cd3b-dev (gcc version 15.3.0 (GCC)) #1 Fri Nov 21 09:32:50 UTC 2025` | `82a5cd3b` | yes (commit) |
| U-Boot | `U-Boot 2024.07 (Sep 22 2025 - 10:51:32 +0000)` | `v2024.07/rz_dev`, `4eebfbaa4e` | unknown: no commit in the banner |
| Linux (not used here) | `Linux version 6.12.59-cip14-yocto-standard` | — | — |

**Which build (checked 2026-10-29).** The image's build recipes pin the same source revisions this project researched: TF-A `f59ed5a31`, U-Boot `4eebfbaa4e`, OP-TEE `82a5cd3b`. Those pins have not changed since 2026-06-17. On top of them the image carries downstream patches:
- TF-A: BL2 parses the OP-TEE header for BL32, and BL2 prints a boot marker (`plat/renesas/rz/common/bl2_plat_setup.c`). That is the `-dirty` suffix.
- U-Boot: defconfig additions (redundant env, FIT signature, a keyed autoboot with a 3 s delay, bootcount, RNG via OP-TEE, board FDT setup), FDT fixups, boot markers, a `bootm` fix, the boot source in `/chosen`, and two CVE fixes (ext4, FIT signature).
- OP-TEE: a TSIP RNG cast, a gcc-14 build relaxation, one CVE fix (ldelf).

None of these patches touches SCIF, CPG, SDHI, PFC, WDT or GIC code. The banner strings and build dates are identical in every archived capture from June 2026 to today, including the 2026-10-08 capture (`EVK-2026-10-08-boot-log.md`). U-Boot's boot-source marker (`boot-source=esd`) appears on 2026-10-08 and today but not in the 2026-10-07 captures. The flashed U-Boot is therefore at least the 2026-10-08 build; no later U-Boot change touches these blocks. Identical build dates do not prove identical binaries, because the dates are fixed by the build system. **The values below belong to that firmware:** the researched revisions plus the downstream patches above.

**Boot mode:** BL2 prints `SYS_LSI_MODE: 0x10200`: MD_BOOT[2:0] = 0 (eSD), DEBUGEN (bit 9) = 1, STAT_SEC_EN (bit 16) = 1 (§6.3.42 p.207).
**Stage:** U-Boot prompt, post-firmware, before `bootm`. Autoboot stopped with the image's keyed autoboot string. No `mmc`, `boot` or other probing command was run before the reads.
**Method:** `md.b`/`md.w`/`md.l` only, rows of `requests.md` section 1 one at a time. Never FTDR or FRDR. The server-enforced deny list blocked `mw`/`mm`/`nm`/`cp`, `mmc write`, `sf`, `saveenv`, `reset`, `boot*` and `go`.
**Provenance:** the raw console transcript (all `md` output verbatim) is kept privately by the operator, SHA-256 `07d97c90b2b9a24ef90da224c12560a0a2f11022c6b2785f37e48e10f7015fb2`. The values below are copied from it.
**Side effects seen:** two reads abort (R04, R05). Each abort resets the board. The image's own autoboot then writes the U-Boot environment (`Saving Environment to MMC`) before it loads Linux. No command of this session wrote anything.

All results are **hardware observations (O)** for this firmware. "MATCH"/"DIFFERS" compares with the Expected column of `requests.md`.

## 1.1 SYSC (`0x11020000`)

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R01 | MODE `0x00010200`, DEVID `0x18447447`, PRR `0x00000000` | MODE `0x000102xx`, DEVID `0x18447447`, PRR 0 | MATCH |
| EVK-R02 | RVAL0 `0`, RVAH0 `0`, RVAL1 `0x00020000`, RVAH1 `0` | reset values | MATCH |
| EVK-R03 | LP_CTL1/2 `0`/`0`; LP_CTL5/6/7 `0`/`0`/`0`; LP_CM33CTL0 `0x00030000`; LP_CA55CK_CTL1/2/3 `0x7`/`0xF06`/`0xF07`; LP_GPU_CTL `0x1F0A` | Table 6.1 p.168: `0`, `0`, `0x0x0x_0xxx`, `0x0000_0x0x`, `0x0000_0F06`, `0x0x0x_0x0x`, `0xxxxx_1Fxx`; LP_CTL5 b8-9 = 0 | MATCH (every value fits its reset pattern) |
| EVK-R04 | **synchronous external abort** in U-Boot: `"Synchronous Abort" handler, esr 0x96000010, far 0x11020000`, then `Resetting CPU ...` | reset values `0x00AAAA00`, `0xAAAAAAAA`, … | **DIFFERS** |
| EVK-R05 | **synchronous external abort**: `esr 0x96000010, far 0x11020100` (run last, after section 1.7) | reset values | **DIFFERS** |

ESR `0x96000010` = data abort from the current EL, DFSC `0x10` (synchronous external abort). SYS_MSTACCCTL and SYS_SLVACCCTL are not readable from U-Boot's non-secure world on this firmware. **Inference (I):** the access-control registers are secure-only, and the bus returns an error for a non-secure read.

## 1.2 CPG (`0x11010000`)

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R10 | `0x5`, `0x00001901`, `0x00180601`, `0x11`; `0x040` = `0x1`; OTPPLL0-2 `0` | as measured; OTPPLL undefined | MATCH |
| EVK-R11 | `0x200` `0`, `0x204` `0`, `0x208` **`0x100`**, `0x20C` `0`, `0x210` `0`, `0x214` `0x401`, `0x218` **`0x22`**, `0x21C` `0x1`; CLKSTATUS `0`; `0x408` **`0x11`**, `0x40C` `0`, `0x410` `0x11`, `0x414` `0x101`, `0x418` `0x10` | DDIVs `0`; `0x214` `0x401`; `0x218` `0x11`; `0x408` `0x111` | **DIFFERS**: PL3A_DDIV DIVPL3C = 1; SEL_SDHI0 = SEL_SDHI1 = 2 (400 MHz); PL3_SSEL SEL_PLL3_3 (b8) = 0 |
| EVK-R12 | GIC600+IA55: CLK_ON `0x1 0x3`, CLK_MON `0x1 0x3`, RST `0x3 0x1`, RSTMON `0x0 0x0` | same | MATCH |
| EVK-R13 | SCIF: CLK_ON `0x1`, CLK_MON `0x1`, RST `0x1`, RSTMON `0x1E` | same | MATCH |
| EVK-R14 | GPIO: `0x1` / `0x1` / `0x7` / `0x0` | same | MATCH |
| EVK-R15 | GTM: CLK_ON **`0x0`**, CLK_MON **`0x0`**, RST `0x1`, RSTMON `0x6` | reset `0x1` / `0x1` / `0x1` / `0x6` | **DIFFERS**: all OSTM clocks off after firmware |
| EVK-R16 | WDT: CLK_ON **`0xFF`**, CLK_MON **`0x3F`**, RST **`0xF`**, RSTMON **`0x0`** | `0xC3` / `0xC3` / `0x9` / `0x6` | **DIFFERS**: WDT0-2 clocks on and resets released; CLK_MON reads reserved bits 7:6 as 0 |
| EVK-R17 | SDHI: CLK_ON **`0xFF`**, CLK_MON **`0xFF`**, RST **`0x3`**, RSTMON **`0x0`** | `0x0F` / `0x0F` / `0x1` / `0x2` (I) | **DIFFERS**: both SDHI channels on (U-Boot probed `sd@11c00000` and `sd@11c10000`) |
| EVK-R18 | SYC: `0x1` / `0x1` / `0x1` / `0x0` | same (I) | MATCH |
| EVK-R19 | MSTOP `0xB60-0xB88`: all `0` | unknown; reset `0` | MATCH (reset values) |
| EVK-R72 | DRP: CLK_ON `0`, CLK_MON `0`, RST `0`, RSTMON `0x1`; PL3C_SDIV `0x401` | RSTMON `0x1`; `0x401` | MATCH |

## 1.3 SCIF0 (`0x1004B800`)

U-Boot echoes each command on SCIF0, so a read straight after the echo sees the transmitter busy. R23 and R24 were therefore also read after `sleep 1` (line idle).

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R20 | SMR `0x0000` | `0x0000` | MATCH |
| EVK-R21 | `+0x02` (MDDR, SEMR.MDDRS = 1) `0xFE` | `0xFE` | MATCH (claim 2) |
| EVK-R22 | SCR `0x0030` | `0x0030` | MATCH |
| EVK-R23 | FSR `0x0020` twice right after the echo; **`0x0060` after `sleep 1`** | `0x0060` | MATCH when idle. While the echo drains, TEND = 0 and TDFE = 1 |
| EVK-R24 | right after the echo: FCR `0`, FDR `0x0100` (T = 1), SPTR `0x0001`, LSR `0`; after `sleep 1`: `0`, `0x0000`, `0x0001`, `0` | `0`, `0`, `0x00xx`, `0` | MATCH when idle |
| EVK-R25 | SEMR `0x30` | `0x30` | MATCH (claim 3) |
| EVK-R26 | FTCR `0x1F1F` | `0x1F1F` | MATCH |
| EVK-R27 | not run: CLK_MON SCIF b1 = 0 (SCIF1 unclocked) | — | skipped as the row requires |

## 1.4 PFC (`0x11030000`)

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R30 | PMC36 `0x03`, PFC36 `0x00000011`, PM36 `0x0000` | same | MATCH |
| EVK-R31 | PWPR `0x80` | `0x80` | MATCH |
| EVK-R32 | `0x03`, `0x00000011`, `0x03`, `0x00000011` | same | MATCH |
| EVK-R33 | SD_ch0 `0x01`, SD_ch1 `0x00`, QSPI `0x00` | `0x01`, `0x00`, unknown | MATCH (QSPI now known: `0x00`) |
| EVK-R34 | ETH MII/RGMII (OEN) **`0x00`** | `0x03` | **DIFFERS** |
| EVK-R35 | IEN04 `0x00000000` | same | MATCH |
| EVK-R36 | PMC40 `0x00`, PFC40 `0x00000000` | same | MATCH |

## 1.5 WDT0 (`0x12800800`)

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R40 | WDTCNT `0x00000001`, WDTSET `0x2AE00000`, WDTTIM `0x00A0C5BE` (counter, changes), WDTINT `0` | WDTCNT b0 = 1; WDTSET for about 60 s | MATCH (b0 = 1; U-Boot reports a 60 s timeout. The WDTSET decode is not checked here) |

## 1.6 GIC-600

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-R60 | GICD_CTLR `0x00000012`, TYPER `0x0079040F`, IIDR `0x0201743B`, TYPER2 `0` | CTLR `0x12`; ITLinesNumber `0xF`, SecurityExtn (b10) = 1, LPIS (b17) = 0; IIDR `0x0201743B` | MATCH |
| EVK-R61 | `44 00 00 00 92 B4 3B 00 0D F0 05 B1` | same | MATCH |
| EVK-R62 | GICR0 CTLR `0`, IIDR `0x0201743B`, TYPER lo `0x00000020` (Last = 0), hi `0x00000000` | IIDR as shown; hi `0`, Last = 0 | MATCH |
| EVK-R63 | GICR1 CTLR `0`, IIDR `0x0201743B`, TYPER lo `0x00000130` (Last = 1, processor number 1), hi `0x00000100` | hi `0x100`, Last = 1, processor 1 | MATCH |
| EVK-R64 | WAKER CPU0 `0x0`, CPU1 **`0x0`** | CPU0 `0x0`; CPU1 `0x6` (I) | **DIFFERS**: GICR1 is awake although CPU1 has not been started |
| EVK-R65 | `44 00 00 00 93 B4 3B 00 0D F0 05 B1` | same | MATCH |
| EVK-R66 | `44 00 00 00 93 B4 3B 00 0D F0 05 B1` | as R65 | MATCH |

## 1.7 Experimental reads

| ID | Measured | Expected | Result |
|---|---|---|---|
| EVK-X01 | no abort. Every CLK_MON word equals its CLK_ON word except WDT: `+0x548` `0xFF` vs `+0x6C8` `0x3F`. Holes read `0` | CLK_MON == CLK_ON | **DIFFERS** for WDT bits 7:6 only (reserved read-as-1 in CLK_ON, read as 0 in CLK_MON). Implemented bits agree everywhere |
| EVK-X02 | no abort. Every RST/RSTMON word pair satisfies RSTMON = ~RST within the bits either word sets. Holes read `0` | inverted pairs | MATCH |
| EVK-R50 | no abort. CNTCR `0x1`, CNTSR `0`, CNTCV `0x00000009_DAF80D31`, `+0x20` `0x016E3600`, rest `0` | CNTCR b0 = 1; `+0x20` = `0x016E3600` (I) | MATCH: CNTFID0 at `+0x20` = 24 MHz, now (O) |
| EVK-R51 | no abort. `0xE33E0947 0x00000009 0 0` | CNTCV advancing | MATCH: the read frame mirrors CNTCV |
| EVK-R70 | no abort. SCIF0 `+0x18` reads `0x0000` | `0x0000` or abort | answered: zero, no bus error (scif.md Q4) |
| EVK-R71 | no abort. PFC `+0x3100` reads `0x00000000` | `0` or abort | answered: zero (pinctrl.md Q4) |

## Cause of each DIFFERS row

"Firmware" means the value depends on what TF-A or U-Boot did before the prompt, so it is a direct-mode start value for this firmware, not a reset value. "Silicon" means no firmware write can explain it.

| ID | Likely cause | Basis | Label |
|---|---|---|---|
| R04, R05 | undetermined: either TF-A's security setup or the silicon reset state makes the access-control registers secure-only | an abort from non-secure U-Boot; the security state that would tell them apart cannot be read from U-Boot | (A) |
| R11 `0x218` SEL_SDHI0/1 = 2 | firmware: U-Boot's SDHI driver (`sh_sdhi`) probes both channels before the prompt (`MMC: sd@11c00000: 0, sd@11c10000: 1`) | boot log; U-Boot SDHI probe | (I) |
| R11 `0x208` DIVPL3C = 1, `0x408` b8 = 0 | firmware: TF-A BL2 or U-Boot clock setup | no write traced to a file:line yet | (I) |
| R15 GTM clocks off | firmware: something gates the OSTM clocks off after reset | reset value is on; no write traced yet | (I) |
| R16 WDT CLK_ON `0xFF`, RST `0xF`, RSTMON 0 | firmware: U-Boot's board code writes the WDT clock and reset registers directly, and its WDT driver autostarts (`WDT: Started watchdog@12800800`) | boot log; U-Boot board code | (I) |
| R16 / X01 CLK_MON_WDT b7:6 = 0 | **silicon**: these reserved bits are not clock enables, so no firmware write changes what CLK_MON reports for them | Table 7.5 / §7.2.4.44 p.308 vs the observed value | (O) |
| R17 SDHI on, resets released | firmware: U-Boot probes SDHI0 (env, boot) and SDHI1 | boot log | (I) |
| R34 ETH OEN `0x00` | firmware: written by TF-A or U-Boot pin setup | reset value `0x03`; no write traced yet | (I) |
| R64 GICR1 WAKER awake | firmware: TF-A's GICv3 driver performs the WAKER handshake during BL31 GIC setup, and the redistributors are left awake | TF-A `drivers/arm/gic/v3` `gicv3_rdistif_init`; `GICV3_SUPPORT_GIC600=1` @ `f59ed5a31` | (I) |

The SCIF0 rows (R20-R26) come from the same TF-A and U-Boot source revisions that `../research/scif.md` §6.2 reasons from. No downstream patch touches the SCIF code (`scifa.S`, `serial_sh.c`). The observed overlay therefore applies to the researched firmware, and also to this build.

## What this changes

- **SCIF0 direct-mode overlay (`../research/scif.md` §6.2):** every value is now observed. SMR 0, MDDR `0xFE`, SCR `0x30`, FSR `0x60` when idle, FCR/FDR/LSR 0, SEMR `0x30`, FTCR `0x1F1F`, SPTR `0x0001`. BRR stays hidden behind MDDR (indirect only). Claims 2 and 3 hold on this firmware.
- **TEND on silicon:** FSR reads TEND = 0 while U-Boot's echo is still shifting out, and TEND = 1 once the line is idle. That is the deferred-TEND behaviour of `scif.md` §7 (O, indirect: the read timing is U-Boot's).
- **Undefined offsets:** SCIF0 `+0x18` and PFC `+0x3100` read as zero without a bus error. The secure-only SYSC access-control registers abort.
- **CPG:** CLK_MON equals CLK_ON for every implemented bit. WDT reserved bits 7:6 read 1 in CLK_ON but 0 in CLK_MON, which conflicts with Table 7.5 (CLK_MON reset = CLK_ON reset = `0xC3`). Silicon is authority for behaviour; the conflict is recorded, not resolved.
- **Post-firmware CPG/PFC/GIC differences** from the predicted start state: R11, R15, R16, R17, R34, R64. These are the direct-mode values for M3b. They are listed here, and the device map is not changed by this record.
