# SYSC (system controller) and SYC (system counter): what firmware and the G0 kernel need

Based on the pinned guest kernels (`docs/sources.md` "Pinned guest kernels").

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference) and the RZ/V2L HW manual Rev 1.50. Firmware requirements are taken from `boot-chain-firmware.md` (public TF-A/U-Boot repos and SHAs listed there) and are not re-derived. The first draft of this note was written against linux v6.18.55; differences are kept in "Newer mainline (v6.18.55)" near the end.

**Labels:** **FACT** = stated by the manual or directly visible in the cited code. **INFERENCE** = derived by reasoning. **ASSUMPTION** = not yet backed. No EVK measurements were taken for this note.

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N`. `renesas-soc.c`, `Kconfig` and `Makefile` are under `drivers/soc/renesas/`; `r9a07g054.dtsi` is under `arch/arm64/boot/dts/renesas/`; `base.c` is `drivers/of/base.c`. G1 citations are written out as `rz_linux-cip 212f6e88b7 <path>:N`.

---

## 1. Block identity

| Item | Value | Evidence |
|---|---|---|
| SYSC base / size | `0x11020000`, 64 KiB | FACT: HW manual Rev 1.50 §5.2.1, Table 5.1 (2/3), p.144; §6.2, p.167; r9a07g054.dtsi:886-896 |
| DT node | `renesas,r9a07g054-sysc`, 4 interrupts, **`status = "disabled"`** | FACT: r9a07g054.dtsi:886-896 (status at :895). Not re-enabled by `r9a07g054l2-smarc.dts` or its includes (grep of the board DTS chain) |
| Interrupts | SPI 42 `lpm_int`, SPI 43 `ca55stbydone_int`, SPI 44 `cm33stbyr_int`, SPI 45 `ca55_deny`, all level-high | FACT: r9a07g054.dtsi:889-894; HW manual Rev 1.50 §8.2, Table 8.2 (3/13), p.536 (GIC IDs 74-77, level) |
| Clocks / resets | none in DT; no CPG gate for SYSC in Table 7.5 | FACT: r9a07g054.dtsi:886-896; HW manual Rev 1.50 §7.2.3, Table 7.5, p.246-251 |
| SYC (counter) | **separate block** at `0x11000000` (Table 5.1 lists 64 KiB; §15.2 says the SYC address space is 8 KiB) | FACT: Table 5.1 (2/3), p.144; §15.2, Table 15.1, p.727 |

G1: identical node (r9a07g054.dtsi has no G0 → G1 diff).

SYSC functions (FACT, §6.1.1, p.165): product information and pin capture, bus security attribute control, 34-bit address offset for 32-bit masters, low-power sequencing, and WDT stop control.

## 2. What Linux v6.12.59 does with SYSC

### 2.1 SoC identification (the only access)

- **FACT.** `renesas-soc.c` is built whenever `ARCH_RENESAS` is set (`SOC_RENESAS` defaults to y: Kconfig:2-4; Makefile:3). It runs at `early_initcall` (renesas-soc.c:572).
- **FACT.** The root compatible `renesas,r9a07g054` selects `soc_rz_v2l`: family "RZ/V2L", `id = 0x8447447` (renesas-soc.c:82-84, :189-192, :411).
- **FACT.** It then looks up the first node matching `renesas_ids`. `renesas,r9a07g054-sysc` maps to `id_rzg2l`, which is offset **0xA04** with mask 0x0FFFFFFF (renesas-soc.c:442-445, :463-473). The node is mapped with `of_iomap` and **one 32-bit read** is made at SYSC + 0xA04 (`SYS_LSI_DEVID`) (:497-502, :519).
- **FACT (was INFERENCE).** `of_find_matching_node_and_match()` walks all nodes and matches on compatible only; neither it nor `__of_match_node` checks `status` (base.c:1051-1074, :997-1016). The **disabled** SYSC node is therefore found and mapped, and Linux reads SYSC MMIO at early boot even though no SYSC driver binds.
- **FACT.** Decoding (renesas-soc.c:534-551):
  - The revision string is `bits[31:28]`, printed as "Rev N".
  - If `(DEVID & 0x0FFFFFFF) != 0x8447447`, it prints `SoC mismatch (product = 0x...)`, returns `-ENODEV` and registers no `soc_device`.
  - On a match it prints `Detected Renesas RZ/V2L r9a07g054 Rev N` (:554-555).
- **Consequences for the model** (INFERENCE):
  - An unmapped SYSC means a synchronous external abort in `early_initcall`, so the kernel dies before the console driver runs.
  - A read-as-zero SYSC gives a "SoC mismatch" and no `/sys/devices/soc0`. That is visible, but it is silent-wrong with respect to the board.
  - SYSC must therefore implement at least `SYS_LSI_DEVID` for answer (b). It is not needed for (a): earlycon output starts before `early_initcall`.
- **G1 (rz-6.12-cip14) delta: none at register level.** The 33-line `renesas-soc.c` diff only **removes** the RZ/G3S and RZ/V2H family/SoC entries and the `id_rzv2h` (offset 0x304) case (rz_linux-cip 212f6e88b7 drivers/soc/renesas/renesas-soc.c:503-506 now tests `id_rzg2l` only). The V2L path is unchanged: `soc_rz_v2l.id = 0x8447447` (:171-174, :392), `renesas,r9a07g054-sysc` → `id_rzg2l` offset 0xA04 mask 0x0FFFFFFF (:417-420, :436), one read (:466, :488), soft mismatch (:517), `early_initcall` (:541). G1's `drivers/of/base.c` only adds a new helper; `of_find_matching_node_and_match` is unchanged.

### 2.2 Everything else: nothing

- **FACT.** No v6.12.59 driver binds `renesas,r9a07g054-sysc`. `drivers/soc/renesas/` has no RZ SYSC driver at all in v6.12.59 (Makefile:1-12 builds only `renesas-soc.o`, `r9a06g032-smp.o`, `pwc-rzv2m.o`, `rcar-rst.o`), and the compatible appears only in `renesas-soc.c` and the DTSI. The node is disabled in any case.
- **G1 (rz-6.12-cip14) delta (no effect on V2L).** G1 backports `rz-sysc.c`, but its match table lists only r9a08g045, r9a09g047, r9a09g056 and r9a09g057 (rz_linux-cip 212f6e88b7 drivers/soc/renesas/rz-sysc.c:84-99). Nothing in G1 binds `renesas,r9a07g054-sysc` either.
- **FACT.** SPIs 42-45 are therefore never requested by G0 or G1 Linux. LP_CTL*, RVAL/RVAH, the CA55 clock-control registers, the access-control registers and the address-offset registers are never accessed by Linux.
- **FACT.** In the sparse checkout, `soc_device_match()` users exist only for R-Car (rcar-gen2/3 CPG, r8a7795 CPG-MSSR, r8a7795/r8a77990/r8a774c0 sysc, r8a7790/r8a7794 PFC), in both G0 and G1. None match r9a07g054 or "RZ/V2L". **Not checked:** drivers outside the checkout (for example `drivers/mmc/host/renesas_sdhi_core.c` and other `soc_device_match` tables). See the claims below.
- **INFERENCE.** PSCI `CPU_ON` from Linux goes to the PSCI provider. In Stage A that is QEMU's built-in PSCI, which does not need RVAL. In Stage B it is real BL31, which writes RVAL1/RVAH1 and polls CPG (`boot-chain-firmware.md` §2).

## 3. Register map: what matters and to whom

Offsets, access and reset values are from FACT, HW manual Rev 1.50 §6.2, Table 6.1 (1/2)-(2/2), p.167-168, unless noted. The "Linux" column holds for G0 (v6.12.59) and G1 alike.

| Offset | Register | R/W | Manual reset | Linux (G0/G1) | Firmware (`boot-chain-firmware.md`) |
|---|---|---|---|---|---|
| 0x000-0x014 | SYS_MSTACCCTL0-5 | RW | 0x00AAAA00, 0xAAAAAAAA, ... | no | not listed |
| 0x100-0x138 | SYS_SLVACCCTL0-14 | RW | 0x0AAAAAA0, 0x0800C0AA, 0x2, 0... | no | not listed |
| 0x200-0x214 | SYS_RAM0/1_ECC/EN | RW | 0 / 0x3 | no | not listed |
| 0x220/0x230/0x240 | SYS_WDT0-2_CTRL | RW | 0x00010000 | no | not listed |
| 0x330/0x340 | SYS_GETH0/1_CFG | R | 0 | no | no |
| 0x400-0x430 | SYS_I2C0-3_CFG | RW | 0 | no | no |
| 0x804-0x814 | SYS_CM33_CFG0-3, CM33_LOCK | RW | 0x3D08, 0x3D08, 0x10010000, 0x00018000, 0 | no | no |
| 0x858/0x85C | SYS_CA55_CFG_RVAL0/RVAH0 | RW | 0 / 0 | no | possibly (not listed) |
| 0x860/0x864 | SYS_CA55_CFG_RVAL1/RVAH1 | RW | 0x00020000 / 0 | no | **BL31 PSCI CPU_ON** |
| 0xA00 | SYS_LSI_MODE | R | pin-dependent (`0x000x_xx0x`) | no | **BL2, U-Boot boot source** |
| 0xA04 | SYS_LSI_DEVID | R | see §4 (conflict) | **yes, `early_initcall`** | **BL2: `[27:0]` must be 0x8447447** |
| 0xA08 | SYS_LSI_PRR | R | `0x0000_0xxx` | no | not listed |
| 0xC00-0xC20 | SYS_AOF0-8 | RW | 0x32103210 (AOF3/5: 0x3210) | no | no |
| 0xD04/0xD08 | SYS_LP_CTL1/2 | RW | 0 | no | (low-power flows) |
| 0xD14 | SYS_LP_CTL5 | RW | 0 | no | **BL31 CPU_OFF waits on an ack** |
| 0xD18/0xD1C | SYS_LP_CTL6/7 | RW | 0 | no | no |
| 0xD24 | SYS_LP_CM33CTL0 | RW | `0x0x0x_0xxx` | no | no |
| 0xD38/0xD3C/0xD40 | SYS_LP_CA55CK_CTL1/2/3 | R / RW / R | `0x0000_0x0x` / 0x0F06 / `0x0x0x_0x0x` | no | no |
| 0xD50 | SYS_LP_GPU_CTL | RW | `0xxxxx_1Fxx` | no | no |
| 0xE00-0xE0C | SYS_GPREG_0-3 | RW | 0 | no | no |

**Field notes:**

- **SYS_LSI_MODE** (FACT, §6.3.42, p.207):
  - b16 `STAT_SEC_EN`: security function supported.
  - b15:14 `MD_OSCDRV`, b12 `MD_CLKS`, b9 `DEBUGEN`, b2:0 `MD_BOOT`.
  - All fields are latched at the PRST# rising edge and are not updated by internal resets.
  - The firmware-observed values 0x10200 (eSD) and 0x10201 (eMMC) (`boot-chain-firmware.md` §2) decode as SEC_EN=1, DEBUGEN=1, MD_BOOT = 0 or 1. INFERENCE.
- **SYS_LSI_PRR** (FACT, §6.3.44, p.209): b0 `CA55_1CPU` (0 = dual, 1 = single). Bits 8 and 4 are reserved with part-dependent values. R9A07G054**L2** is the dual-core part, so b0 should read 0 (INFERENCE; measure).
- **RVAL1/RVAH1** (FACT, §6.3.40-41, p.206): the reset vector `[31:2]` of core 1, plus `[39:32]` in RVAH1. The new value takes effect at the core's next reset release. RVAL1's reset value 0x00020000 is consistent with the field description (H'0000_8000 in `[31:2]`).
- **SYS_LP_CTL5** (FACT, §6.3.56, p.221):
  - b10/b9/b8 are sleep-request flags (CM33, CA55 core1, CA55 core0). Each raises `SYS_LPM_INT` and is cleared by writing 0.
  - b2/b1 are A55 ACE bridge QDENY flags, which raise `SYS_CA55_DENY`.
  - The manual's low-power flow reads LP_CTL5 on `SYS_LPM_INT` to find the cause (HW manual Rev 1.50 §42.3.2, p.3432-3433).
  - BL31's CPU_OFF acknowledge is bit (8 + core); see the Verification table.

## 4. Manual vs driver/firmware conflict: SYS_LSI_DEVID

- **Conflict (FACT, recorded, not resolved).** Table 6.1 (2/2), p.168 gives the initial value `H'x841_C447`, which is the RZ/G2L ID (`soc_rz_g2l.id = 0x841c447`, renesas-soc.c:169-172). The register description gives `DEV_ID[27:0] = H'844_7447` with `[31:28]` = revision (§6.3.43, p.208). Linux (renesas-soc.c:189-192; G1 identical) and BL2 (`boot-chain-firmware.md` §1) both require 0x8447447.
- **Resolution for the model:** use §6.3.43 (`0x8447447`), which is consistent with both guests. Table 6.1 looks like a carry-over from the G2L manual (INFERENCE). The revision nibble `[31:28]` is undefined ("—") in the manual and must be measured. Until then it is a documented ASSUMPTION, and the model must expose it as a property rather than a silent constant.

## 5. SYC: where CNTFID0 lives

- **FACT.** The system counter is the **SYC**, a separate block at `0x11000000`, not part of SYSC (Table 5.1 (2/3), p.144; §15, p.725-727).
  - It is a CoreSight SoC-400 Timestamp Generator counting at 24 MHz (`SYC_CNT_CLK`) and feeding a 64-bit Gray-coded count to the A55 generic timers and the 3DGE.
  - `0x0000-0x0FFF` is the PSELCTRL (control) region and `0x1000-0x1FFF` the PSELREAD (read-only) region.
  - The manual defers the register layout to the Arm CoreSight SoC-400 TRM §3.10.
- **INFERENCE (Arm architecture, not in the RZ manual).** The Timestamp Generator control frame follows the Arm generic-counter `CNTControlBase` layout: `CNTCR` @ 0x000 (EN bit 0), `CNTSR` @ 0x004, `CNTCV` @ 0x008/0x00C, `CNTFID0` @ 0x020. This would put the CNTFID0 that BL31 copies into `CNTFRQ_EL0` (`boot-chain-firmware.md` C2) at **0x11000020**. Verify against the TF-A source and the EVK.
- **FACT.** SYC is CPG-gated: `CPG_CLKON_SYC` (0x528) resets to 0, `CPG_RST_SYC` (0x828) resets to 0 (in reset), and `CPG_RSTMON_SYC` (0x9A8) resets to 1 (HW manual Rev 1.50 §7.2.3, Table 7.5 (2/6)-(4/6), p.247-249). **INFERENCE:** firmware must ungate SYC, release its reset and set `CNTCR.EN` before the generic timer advances. In direct mode this belongs to the post-firmware overlay.
- **FACT.** Linux never touches SYC. There is no DT node at 0x11000000 (the DTSI `timer` node has no `clock-frequency`, r9a07g054.dtsi:1344-1352). `R9A07G054_SYC_CNT_CLK` / `R9A07G054_SYC_RESETN` exist as binding IDs (linux v6.12.59 include/dt-bindings/clock/r9a07g054-cpg.h:50, :162), but `r9a07g044-cpg.c` defines no module clock or reset for them (G1 likewise: its additions are DRP-AI only). The clk core therefore cannot disable SYC as unused (see `cpg-reset.md` §4).

## 6. Who needs what

| Need | TF-A BL2/BL31 (G1, Stage B/C) | U-Boot | Linux v6.12.59 / G1 (direct mode) |
|---|---|---|---|
| `SYS_LSI_DEVID` | BL2 panics unless `[27:0]` = 0x8447447 | — | read once at `early_initcall`; mismatch → no soc_device |
| `SYS_LSI_MODE` | BL2 boot device | boot source | — |
| `RVAL1/RVAH1` | BL31 CPU_ON | — | — (QEMU PSCI in Stage A) |
| `SYS_LP_CTL5` ack | BL31 CPU_OFF | — | — |
| SYC `CNTFID0` (+ CNTCR) | BL31 → `CNTFRQ_EL0` | — | — (QEMU sets `cntfrq` = 24 MHz, REQ-MACH-003) |
| SPIs 42-45 | not used by the studied firmware (INFERENCE) | — | never requested |

## 7. Minimal model proposal

> **Staging:** this section is the **full target** for SYSC, reached in M7 (Stage B, real BL31). The model implements items 2–4 only (`LSI_DEVID`, `LSI_MODE`, `LSI_PRR`, read-only); every other offset is a bus error. Items 1 and 5–8 (register file, `RVAL1/RVAH1`, `LP_CTL5` ack, stored security/ECC/offset registers) are the M7 target.

**SYSC: FUNCTIONAL / faithful for the registers listed; side effects STUB.**
1. A 64 KiB MMIO region. All registers of Table 6.1 form a register file with the manual reset values and R/W attributes. Writes to read-only registers are ignored and logged under `-d guest_errors`. Undocumented offsets read 0, ignore writes and are logged.
2. `SYS_LSI_DEVID`: properties `devid` = 0x8447447 and `revision` (4 bits), composed on read. **EVK-measured default: revision 1, i.e. `0x18447447`** (BL2 print, every boot; `../evidence/EVK-2026-10-08-boot-log.md`).
3. `SYS_LSI_MODE`: a machine property set from the selected boot source (0x10200 eSD, 0x10201 eMMC per `boot-chain-firmware.md`). Reads the same in both start states, because it is latched from pins.
4. `SYS_LSI_PRR`: property, default `0x0` (b0 = 0, dual core). **EVK-measured:** `0x00000000` on every boot (BL2 print).
5. `RVAL1/RVAH1`: R/W. Stage B wires them to core 1's reset vector on the CPG-driven release, using the CPG PCH/RST_CA55 handshake. Stage A only stores them.
6. `LP_CTL5`: R/W, write-0-to-clear flags. The ack behaviour BL31 needs (bit 8 + core) is implemented exactly as the TF-A code requires and is recorded as a model-supplied stand-in for the M33 (honest: documented, not silent).
7. Security, ECC, address-offset and low-power side effects are **not modelled**: the registers store values only. SPIs 42-45 are left unconnected (never asserted). This is faithful as long as no guest enters the low-power flow; the gap is listed.
8. **Start states:** identical except for registers firmware writes (RVAL1/RVAH1, possibly MSTACCCTL/SLVACCCTL). The direct-mode overlay takes measured U-Boot values.

The re-base to v6.12.59 and G1 changes none of these requirements: both kernels make exactly the one DEVID read.

**SYC: STUB → FUNCTIONAL at Stage B.** A small device at 0x11000000:
- `CNTCR` (EN) R/W.
- `CNTFID0` = 24 000 000. The firmware-mode reset value comes from the CoreSight TRM, the post-firmware value from measurement.
- `CNTCV` derived from the QEMU virtual clock at 24 MHz, consistent with the CPU generic timer.
- The PSELREAD mirror at +0x1000.

Linux does not need SYC; firmware does. QEMU has no CoreSight Timestamp Generator model today (no analogue found in qemu v11.1.2 `hw/`). The nearest precedents are the Arm SSE system-counter-style devices, to be surveyed in M1.

**Verification:** a qtest asserting DEVID `[27:0]` = 0x8447447 (§6.3.43, *not* the Table 6.1 value), LSI_MODE / PRR from properties, the RVAL1 reset value 0x00020000, and the Table 6.1 reset values for a sample of RW registers. Mutation-check the DEVID test.

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target. Citations are `linux v6.18.55 drivers/soc/renesas/<file>:N`. The SYSC contract is the same as in v6.12.59 (one 32-bit read of SYSC + 0xA04 at `early_initcall`, soft mismatch); only the code layout differs:

- `renesas-soc.c`: `soc_rz_v2l` at :175-178, `id_rzg2l` match at :429-432/:444-453, map and read at :478-501, decode at :515-532, message at :535-536, `early_initcall` at :553. It also keeps the RZ/G3S and RZ/V2H entries that G1 drops.
- `rz-sysc.c` exists in mainline v6.18 and matches only r9a08g045, r9a09g047, r9a09g056 and r9a09g057 (:90-99); `SYSC_R9A08G045` is selected only by `ARCH_R9A08G045` (Kconfig:383-388, :465). It does not bind V2L.

## Claims to verify

1. **DEVID conflict:** Table 6.1 (2/2), p.168 (`x841_C447`) vs §6.3.43, p.208 (`844_7447`). Guests require the latter; silicon decides the revision nibble. **Resolved:** the EVK BL2 print reads `0x18447447` (`../evidence/EVK-2026-10-08-boot-log.md`).
2. CNTFID0 is at SYC + 0x020 (0x11000020): an Arm generic-counter layout inference. Cross-check the TF-A `plat/renesas/rz` timer/SYC code (TF-A `f59ed5a31`) and the CoreSight SoC-400 TRM §3.10.
3. No G0 or G1 driver outside the sparse checkout applies `soc_device_match` quirks for r9a07g054 or "RZ/V2L". Check `drivers/mmc/host/renesas_sdhi_core.c`, `drivers/gpu`, `drivers/media` and `drivers/net/ethernet/renesas` in both trees.
4. Firmware must enable the SYC clock and reset in CPG (reset values 0, Table 7.5, p.247-249) before the counter runs.

## Questions for the EVK

All are read-only `md.l` reads at the **U-Boot prompt before `bootm`** (post-firmware state) unless stated otherwise.

1. ~~`md.l 0x11020a00 3`~~: **answered** by the BL2 prints across about 150 archived boots (DEVID `0x18447447`, PRR `0x0`, LSI_MODE per boot mode); see `../evidence/EVK-2026-10-08-boot-log.md`.
2. `md.l 0x11020858 4`: RVAL0/RVAH0/RVAL1/RVAH1. Did firmware change them from the reset values?
3. `md.l 0x11020d00 0x18`: LP_CTL1..GPU_CTL, including the CA55CK_CTL status values.
4. `md.l 0x11020000 6` and `md.l 0x11020100 0x10`: the access-control registers as left by firmware.
5. `md.l 0x11000000 0x10` and `md.l 0x11001000 4`: SYC CNTCR/CNTSR/CNTCV/CNTFID0 and the read frame. Expect CNTFID0 = 0x016E3600 if the inference in §5 holds.
6. `md.l 0x11010528 1`, `md.l 0x11010828 1`, `md.l 0x110109a8 1`: CPG CLKON/RST/RSTMON for SYC.
7. **Post-Linux** (read-only, from the G1 console log): the exact `Detected Renesas RZ/V2L r9a07g054 Rev N` line, or a `SoC mismatch` warning.

## Verification

| Claim | Result | Evidence |
|---|---|---|
| SYSC is read although its DT node is disabled | **Confirmed** | linux v6.12.59 `drivers/soc/renesas/renesas-soc.c:497-502, :519`: `of_find_matching_node_and_match` + `of_iomap` on `renesas,r9a07g054-sysc`, offset `0xa04`, mask `0xfffffff`; `drivers/of/base.c:1051-1074` does not check `status`. The DTSI node has `status = "disabled"` (`r9a07g054.dtsi:895`). G1 identical (rz_linux-cip 212f6e88b7 `renesas-soc.c:466, :488`). |
| A DEVID mismatch is soft | **Confirmed** | linux v6.12.59 `renesas-soc.c:546-551`: `pr_warn("SoC mismatch ...")` and `-ENODEV` from soc identification; the boot continues. G1 `:517`. |
| The expected V2L ID is `0x8447447` | **Confirmed** | linux v6.12.59 `renesas-soc.c:189-192` `soc_rz_v2l.id = 0x8447447`; G1 `:171-174` |
| The manual contradicts itself on DEVID | **Confirmed** | HW manual Rev 1.50 Table 6.1 lists `H'x841_C447` (the RZ/G2L value); §6.3.43 p.208 gives `H'844_7447` for bits [27:0]. Silicon decides; this is an EVK question. |
| `LP_CTL5` "acknowledge" bit | **Resolved** | TF-A `f59ed5a31` `plat_pm.c:92-98`: CPU_OFF polls `SYS_LP_CTL5` bit (8 + core) after writing `LP_CTL6`/`LP_CTL1` bit (8 + core) |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7`. No change to the SYSC register contract: G0 has no RZ SYSC driver; G1's `rz-sysc.c` and its `renesas-soc.c` delta do not touch V2L. v6.18.55 layout kept under "Newer mainline". |

## EVK results (2026-10-29, U-Boot prompt, downstream firmware; `../evidence/EVK-2026-10-29-post-firmware.md`)

- **OBSERVED.** Q1: SYS_LSI_MODE `0x00010200`, DEVID `0x18447447`, PRR 0 at the U-Boot stage, as BL2 prints them. Q2: RVAL/RVAH at reset values. Q3: the low-power registers fit their Table 6.1 reset patterns, and LP_CTL5 bits 8-9 are 0.
- **OBSERVED, conflicts with the prediction.** Q4: SYS_MSTACCCTL0 (`0x11020000`) and SYS_SLVACCCTL0 (`0x11020100`) give a synchronous external abort (`esr 0x96000010`) when read from U-Boot (non-secure). INFERENCE: secure-only on this firmware. The reset values in Table 6.1 cannot be confirmed from the non-secure side.
- **Conflict, recorded (lead for the Secure-only rule).** `SYS_SLVACCCTL1` bits 15:14 are `SYSC_SL`, initial `11b`, read-only (§6.3.8 p.184): by Table 5.5 (p.159) the whole SYSC would then take only privileged Secure accesses. On the board the Non-secure world reads the ID registers (Linux `renesas-soc` reads `SYS_LSI_DEVID`, U-Boot `md` reads `SYS_LSI_MODE`, EVK-R01) without an abort, while `SYS_MSTACCCTL0` and `SYS_SLVACCCTL0` abort (Q4). Silicon rules actual behaviour: the model refuses Non-secure accesses to the access-control bank only (I), and leaves the rest of the SYSC open, as observed. A Non-secure read of another bank register (for example `SYS_SLVACCCTL14`, `0x11020138`) would test the bank-wide part of that inference.
- **OBSERVED.** Q5 / claim 2: the SYC control frame is readable from the non-secure side. CNTCR = 1, CNTFID0 at `+0x20` = `0x016E3600` (24 MHz), and the read frame at `0x11001000` mirrors CNTCV (EVK-R50, R51). The `+0x20` offset label moves from (I) to (O).
