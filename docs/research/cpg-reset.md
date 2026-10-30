# CPG (clock, reset, MSTOP, PM domain): what the G0 kernel needs

Based on the pinned guest kernels (`docs/sources.md` "Pinned guest kernels").

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference) and the RZ/V2L HW manual Rev 1.50. Firmware facts come from `boot-chain-firmware.md` and are not re-derived here. The first draft of this note was written against linux v6.18.55; where that kernel behaves differently, the difference is kept in "Newer mainline (v6.18.55)" near the end.

**Labels:** **FACT** = stated by the manual or directly visible in the cited code. **INFERENCE** = derived from code or manual by reasoning. **ASSUMPTION** = not yet backed by evidence. No EVK measurements were taken for this note.

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N` with these paths:

| Short | Full path |
|---|---|
| `rzg2l-cpg.c`, `rzg2l-cpg.h`, `r9a07g044-cpg.c` | `drivers/clk/renesas/` |
| `r9a07g054.dtsi`, `rzg2l-smarc-som.dtsi` | `arch/arm64/boot/dts/renesas/` |
| `sh-sci.c` | `drivers/tty/serial/` |
| `rzg2l_wdt.c` | `drivers/watchdog/` |
| `pinctrl-rzg2l.c` | `drivers/pinctrl/renesas/` |

G1 citations are written out in full as `rz_linux-cip 212f6e88b7 <path>:N`. **G1 delta** lines appear only where G1 changes the register-level contract. Measured G0 → G1 differences in the files this note uses: `rzg2l-cpg.c` 5 lines (an `IS_ERR_OR_NULL` → `IS_ERR` check in core-clock registration and a debug-print helper; no register access changes), `rzg2l-cpg.h` 2 lines (`CPG_PL3C_SDIV`, `DIVPL3E`), `r9a07g044-cpg.c` 55 lines (DRP-AI clocks and reset, §2.6 and §3), `r9a07g054.dtsi` 0 lines, `sh-sci.c` 2 lines (earlycon struct copy, no register change), `rzg2l_wdt.c` 0 lines.

---

## 1. Block identity

| Item | Value | Evidence |
|---|---|---|
| Base / size | `0x11010000`, 64 KiB | FACT: HW manual Rev 1.50 §5.2.1, Table 5.1 (2/3), p.144; §7.2.2, p.245; linux v6.12.59 arch/arm64/boot/dts/renesas/r9a07g054.dtsi:876-884 |
| Compatible | `renesas,r9a07g054-cpg`, `#clock-cells = <2>`, `#reset-cells = <1>`, `#power-domain-cells = <0>` | FACT: r9a07g054.dtsi:876-884 |
| Input clock | `extal` = 24 MHz (DTSI sets 0, board overrides) | FACT: r9a07g054.dtsi:37-43; linux v6.12.59 arch/arm64/boot/dts/renesas/rzg2l-smarc-som.dtsi:148-150 |
| Driver | `rzg2l-cpg.c`, SoC tables shared with G2L in `r9a07g044-cpg.c` (`r9a07g054_cpg_info`) | FACT: linux v6.12.59 drivers/clk/renesas/rzg2l-cpg.c:1916-1920; drivers/clk/renesas/r9a07g044-cpg.c:476-502 |
| Probe time | `subsys_initcall` via `platform_driver_probe` | FACT: rzg2l-cpg.c:1944-1949 |
| IRQ / DMA | none | FACT: no `interrupts` in the CPG node |

G1: identical DT node and driver entry (r9a07g054.dtsi has no G0 → G1 diff).

**Address-space classes** (FACT, Table 7.4, p.245): `0x000-0x0FF` SSCG PLL1/4/6, `0x100-0x17F` PLL2/3/5, `0x200-0x3FF` dynamic dividers, `0x400-0x4FF` static selectors, `0x500-0x67F` CLK_ON, `0x680-0x7FF` CLK_MON, `0x800-0x97F` RST, `0x980-0xAFF` RSTMON, `0xB00-0xFFF` other (WDT reset, PCH handshake, MSTOP, OTHERFUNC).

## 2. Register families and the driver's use of each

### 2.1 Write-enable convention (upper 16 bits)

- **FACT.** For every writable field the manual places a write-enable bit 16 positions above it. The enable bit is R0W1 (it always reads 0), and a field is written only when its enable bit is set in the same write. The pattern holds for CLK_ON (Table 7.5; §7.2.4.58, p.327), RST (§7.2.4.135, p.409), MSTOP (§7.2.4.192, p.472), the dividers (§7.2.4.16-18, p.274-277) and SEL_SDHI (§7.2.4.21, p.281). In the dividers the enable bit sits at bit 16 + (field LSB), one bit per field, not one per field bit.
- **FACT.** Linux always writes `(bitmask << 16) | value` for CLK_ON and RST: rzg2l-cpg.c:1225-1229 (CLK_ON), :1433-1437 and :1462-1467 (RST). It never does a read-modify-write on these registers. v6.12.59 does not write MSTOP on V2L at all (§2.4).
- **FACT.** Generic dividers and muxes use the clk core's `CLK_DIVIDER_HIWORD_MASK` / `CLK_MUX_HIWORD_MASK` (rzg2l-cpg.h:157-160, :173-176). **INFERENCE** (the clk core is outside the sparse checkout): these write `field_mask << (shift+16) | val << shift`. For a field wider than one bit this also sets reserved bits above the single manual enable bit (for example bit 17 for `DIVPL1_SET`). The manual says those bits ignore writes, so a model must honour only the documented enable bit.
- **Model rule:** `new = (old & ~(wen_mask)) | (wdata & wen_mask)`, where `wen_mask` is derived per register from `wdata[31:16]` and the documented field map. Upper bits always read 0.

### 2.2 CLK_ON (`0x500+n`) and CLK_MON (`0x680+n` = CLK_ON + 0x180)

- **FACT.** CLK_MON sits at the CLK_ON offset + 0x180, with the same bit layout and polarity (1 = clock supplied): Table 7.5 (2/6)-(3/6), p.247-248; §7.2.4.97, p.368; rzg2l-cpg.c:56-57.
- **FACT.** Reset values of the families that matter here: `CLKON_GIC600` (0x514) = 0x1, `CLKON_IA55` (0x518) = 0x3, `CLKON_GTM` (0x534) = 0x1, `CLKON_WDT` (0x548) = 0xC3, `CLKON_SDHI` (0x554) = 0, `CLKON_SCIF` (0x584) = 0, `CLKON_GPIO` (0x598) = 0, `CLKON_SYC` (0x528) = 0. Each CLK_MON reset value equals its CLK_ON value (Table 7.5, p.246-249).
- **FACT.** Some reserved bits read as fixed 1s. `CLKON_WDT` bits 7:6 are reserved with value 1, which is why the reset value is 0xC3 although only bits 5:0 are clock enables (§7.2.4.44, p.308). The model must keep such bits fixed.
- **Driver, enable** (FACT, rzg2l-cpg.c:1209-1246, called from :1248-1266):
  1. Write `bit<<16 | bit` to CLK_ON (:1225-1229). There is no lock around this write and no MSTOP access.
  2. Because `has_clk_mon_regs = true` (r9a07g044-cpg.c:500), poll CLK_MON for the bit with `readl_poll_timeout_atomic(..., delay 0, timeout 10 us)` (rzg2l-cpg.c:1236-1243). On timeout: `Failed to enable CLK_ON` and the poll's `-ETIMEDOUT`.
- **Driver, disable** (FACT, :1225-1232, called from :1268-1286): writes `bit<<16` to CLK_ON and returns. There is no monitor poll and no MSTOP access.
- **Driver, is_enabled** (FACT, :1288-1309): reads **CLK_MON**, not CLK_ON. The monitor is therefore what the clk core believes at registration and in the unused-clock sweep.
- **Coupled clocks** (eth, lcdc): a software-shared bit through `clock->sibling` (:1248-1286, :1317-1337, :1401-1410). Not relevant to the early set.

### 2.3 RST (`0x800+n`) and RSTMON (`0x980+n` = RST + 0x180)

- **FACT. The polarity is inverted.** In RST, 1 = reset released (RSTB). In RSTMON, 1 = reset applied: §7.2.4.135, p.409 vs §7.2.4.173, p.450. Every reset-value pair in Table 7.5 (3/6)-(5/6), p.248-250 satisfies `RSTMON = ~RST & implemented_mask`. Examples: SCIF RST 0x00 ↔ RSTMON 0x1F; GIC600 0x3 ↔ 0x0; WDT 0x9 ↔ 0x6 (bit 3 of RST_WDT is a reserved read-as-1 bit, §7.2.4.121, p.394); SYC 0x0 ↔ 0x1; CA55 0x1FFF ↔ 0x0; DRP 0x0 ↔ 0x1 (p.250).
- **Driver, assert/deassert** (FACT, rzg2l-cpg.c:1425-1482):
  1. Write `bit<<16` (assert, :1433-1437) or `bit<<16 | bit` (deassert, :1462-1467) to RST.
  2. Because `has_clk_mon_regs`, poll RST + 0x180 (`CLK_MRST_R`, :59): assert waits for `mon & bit` (:1450-1451), deassert waits for `!(mon & bit)` (:1480-1481). Step 10 us, timeout 200 us.
  3. On timeout the poll's `-ETIMEDOUT` is returned. v6.12.59 does **not** write the opposite value back (contrast v6.18.55 below).
- **Driver, status** (FACT, :1496-1516): returns `!!(RSTMON & bit)`, so 1 means asserted.
- **FACT.** None of the G2L/V2L resets use `DEF_RST_MON`, so `monbit = -1` for all of them (r9a07g044-cpg.c:371-433; rzg2l-cpg.h:244-251). The `CPG_RST_MON` = 0x680 path (rzg2l-cpg.h:29) is unused on V2L. That offset is `CPG_CLKMON_CA55` on this SoC.
- **INFERENCE (load-bearing).** A plain, same-polarity mirror would make every Linux deassert time out (the driver expects mon = 0 after deassert). `sh-sci` would then fail with `failed to deassert reset` (linux v6.12.59 drivers/tty/serial/sh-sci.c:3358-3367). A read-as-zero RSTMON makes every deassert "succeed" instantly and every assert time out. That would be silent-wrong for deassert. `boot-chain-firmware.md` §2 says RSTMON "mirrors" RST. This note uses the manual's meaning: an **inverted** mirror.
- G1: no delta (rzg2l-cpg.c reset code identical; G1 adds one reset, `STPAI_ARESETN` at RST 0x8E8 b0, rz_linux-cip 212f6e88b7 drivers/clk/renesas/r9a07g044-cpg.c:481-483, which no G1 DT node references).

### 2.4 MSTOP (`0xB60-0xB88`)

- **FACT.** In each MSTOP register, 1 = module stop state and 0 = normal. The upper-16 enable convention applies. All MSTOP registers reset to 0: Table 7.5 (5/6), p.250; §7.2.4.192, p.472-474.
- **FACT. v6.12.59 never writes an MSTOP register on RZ/V2L or RZ/G2L.**
  - Module clocks carry no MSTOP data: `DEF_MOD` has no MSTOP argument and the enable/disable path touches only CLK_ON/CLK_MON (rzg2l-cpg.h:215-226; rzg2l-cpg.c:1209-1246).
  - The only MSTOP writes in the driver are the PM-domain `power_on`/`power_off` callbacks (rzg2l-cpg.c:1675-1699). They use a per-domain `conf.mstop` (rzg2l-cpg.h:258-300) and are installed only for domains that are not always-on (:1701-1718), which exist only when the SoC info provides `pm_domains` and the DT uses `#power-domain-cells = <1>`.
  - `r9a07g054_cpg_info` and `r9a07g044_cpg_info` define no `pm_domains` (r9a07g044-cpg.c:447-502), and the V2L DT uses `#power-domain-cells = <0>` (r9a07g054.dtsi:883). `rzg2l_cpg_add_pm_domains` therefore takes the backward-compatibility path to a single always-on clock domain (rzg2l-cpg.c:1776-1782, :1720-1742) with no `power_on`/`power_off`.
  - There is no `init_mstop` pass at probe and no resume handler in the driver (rzg2l-cpg.c:1839-1901).
  - `CPG_BUS_*_MSTOP` offsets are defined (rzg2l-cpg.h:30-41) and per-domain IDs exist in the bindings (linux v6.12.59 include/dt-bindings/clock/r9a07g054-cpg.h:230 onward), but neither is used for V2L.
- **INFERENCE.** With G0, MSTOP stays at whatever the previous boot stage left: all 0 in firmware mode (manual reset), the firmware's values in direct mode. A model in which MSTOP has no peripheral effect is invisible to G0.
- **FACT.** The manual's register list has no `BUS_MCPU3`/`PERI_CPU2` MSTOP registers (0xB90/0xB94). They appear in rzg2l-cpg.h:40-41, but no V2L table references them.
- G1: no delta. The G1 driver is the G0 driver plus a non-functional 5-line change; G1 also never writes MSTOP on V2L (rz_linux-cip 212f6e88b7 drivers/clk/renesas/rzg2l-cpg.c has the same `power_on`/`power_off` as the only MSTOP writers, and G1's `r9a07g054_cpg_info` has no `pm_domains`, rz_linux-cip 212f6e88b7 drivers/clk/renesas/r9a07g044-cpg.c:527-553).

### 2.5 PLL configuration and monitor

| Offset | Register | Reset | Linux use |
|---|---|---|---|
| 0x000 | SAMPLL1_STBY | 0x5 | none |
| 0x004 | SAMPLL1_CLK1 (DIV_K[31:16] s16, DIV_M[15:6], DIV_P[5:0]) | 0x00001901 (k=0, m=100, p=1) | **read** for PLL1 rate |
| 0x008 | SAMPLL1_CLK2 (MFR[23:16], MRR[13:8], DIV_S[2:0]) | 0x00180601 (s=1) | **read** (DIV_S only) |
| 0x00C | SAMPLL1_MON (LOCK bit 4, RESETB bit 0) | 0x11 | none |
| 0x040 | PLL1_SETTING (SEL_PLL1) | 0x1 | none |
| 0x044-0x04C | OTPPLL0..2_MON | undefined (x) | none |
| 0x11C / 0x13C | SIPLL2_MON / SIPLL3_MON | 0x11 | none |
| 0x140-0x15C | SIPLL5_* | see Table 7.5 | written at probe and for DSI only |

Sources: FACT, Table 7.5 (1/6), p.246; §7.2.4.2-7.2.4.5, p.254-260.

- **Rate formula.** The manual gives `FFout = (m + k/65536) × 24 MHz / (p × 2^s)` (§7.2.4.2 Note 1, p.255; the trailing "×3" in the text extract is a footnote marker, not a factor). The driver computes `parent × ((M<<16)+K) >> (16+S) / P` (rzg2l-cpg.c:957-975; field macros :45-48). Both formulas agree. The reset values give **1200 MHz**, which is the manual's default and maximum for PLL1 (p.255 Note 2). FACT.
- **FACT.** PLL2, PLL3, PLL5 and PLL6 are **fixed factors** in the driver: PLL2 = PLL3 = 24 × 200/3 = 1600 MHz, PLL5 = 3000 MHz, PLL6 = 500 MHz (r9a07g044-cpg.c:128-137). Their registers are never read.
- **Hazard (INFERENCE).** If SAMPLL1_CLK1 reads 0 (read-as-zero stub), `PDIV = 0` and the driver's `DIV_ROUND_CLOSEST_ULL(rate, 0)` (rzg2l-cpg.c:974) divides by zero. On arm64, a hardware divide by zero returns 0, so the CPU clock would read 0 Hz rather than trap. That is silent-wrong.
- **FACT.** At probe, `rzg2l_cpg_sipll5_register` writes SIPLL5_STBY = `SSCG_EN_WEN | RESETB_WEN | RESETB` (0x00050001) (rzg2l-cpg.c:929-930). It does not poll at probe. The lock polls on SIPLL5_MON (:856, :883, inside `rzg2l_cpg_sipll5_set_rate` :824-891) run only on a DSI rate change.
- **Conflict (record).** `SEL_PLL1` resets to 1. This means "use OTP PLL settings when OTP_OTPPLL0 bit 0 = 1" (§7.2.4.5, p.260). Linux reads only SAMPLL1_CLK1/CLK2, so on a part with OTP-programmed PLL1 the driver's computed rate could differ from the real one. Unknown for the EVK; see the questions at the end.

### 2.6 Dividers, selectors and status/busy

| Offset | Field(s) used by Linux | Reset | Linux clock / type |
|---|---|---|---|
| 0x200 PL1_DDIV | `DIVPL1_SET[1:0]` (/1,/2,/4,/8) | 0x0 in §7.2.4.16; Table 7.5 says `0x0000000x` | `I`, `DEF_DIV` (`DIVPL1A`), writable |
| 0x204 PL2_DDIV | `DIVPL2A_SET[2:0]`, `DIVDSILPCLK_SET[13:12]` | 0x0 | `P0`, `.div_dsi_lpclk` |
| 0x208 PL3A_DDIV | `DIVPL3A[2:0]`, `DIVPL3B[6:4]`, `DIVPL3C[10:8]` | 0x0 | `P2`, `P1`, `divpl3c` |
| 0x210 PL6_DDIV | `DIVGPU[1:0]` | 0x0 | `G` |
| 0x214 PL3C_SDIV | `DIVPL3E[12:8]` (table 4..32) | 0x401 (Table 7.5 (5/6), p.250; §7.2.4.203, p.491) | **G0: not used.** G1 only: `DRP_A` (see G1 delta) |
| 0x218 PL2SDHI_DSEL | `SEL_SDHI0[1:0]`, `SEL_SDHI1[5:4]` (1=533, 2=400, 3=266; 0 prohibited) | 0x11 | `SD0`, `SD1` (SD mux) |
| 0x280 CLKSTATUS | busy bits: DIVPL1 b0, DIVPL2A b4, DIVPL3A/B/C b8-10, DIVGPU b20, SELSDHI0/1 b28/29 (1 = busy) | 0x0 | polled for SD mux only |
| 0x408 PL3_SSEL | `SEL_PLL3_3` b8 | 0x111 | read-only mux |
| 0x414 PL6_SSEL | `SEL_GPU2` b12 | 0x101 | read-only mux |
| 0x418 PL6_ETH_SSEL | `SEL_PLL6_2` b0 | 0x10 | `HP` mux, writable |
| 0xBE8 OTHERFUNC1 | `SEL_PLL5_4` b0 (whole register read as parent index) | 0x0 | read at probe when the PLL5_4 mux registers (rzg2l-cpg.c:734-740; seen in the M3b-cpg boot); written for DSI only |

Sources: FACT, Table 7.5, p.246, p.250; §7.2.4.16-25, p.274-286; r9a07g044-cpg.c:119-192; rzg2l-cpg.h:20-29, :67-81.

- **Busy polls** (FACT): only the SD mux (`set_parent`, rzg2l-cpg.c:460-487, and its notifier :178-216) polls CLKSTATUS, through `rzg2l_cpg_wait_clk_update_done` (10 us step, 200 us timeout, waiting for 0) (:169-176). The notifier first switches through 266 MHz (value 3), which the manual requires (§7.2.4.21 Note 1, p.281).
- **FACT.** The generic dividers (`I`, `P0`, `P1`, `P2`, `G`, `divpl3c`) do **not** poll CLKSTATUS (:402-439, plain `clk_hw_register_divider[_table]`). Busy bits that always read 0 are compatible with Linux.
- **INFERENCE.** A read of value 0 in `SEL_SDHI0` maps to no parent: `clk_mux_val_to_index` with mtable {1,2,3} fails, and SD0 becomes an orphan. The model must keep a legal value (reset 0x11).
- **G1 (rz-6.12-cip14) delta:** G1 registers the DRP-AI clocks that G0 leaves out (G0's `drp[]` arrays are empty, r9a07g044-cpg.c:117, :194-195, :202, :366-367). Core: `DRP_M` = PLL3/5, `DRP_D` = PLL3/2 (fixed), and `DRP_A` = PLL3 / `DIVPL3E` with `dtable_4_32` (field values 3..31 → /4../32), a hiword-masked divider on **PL3C_SDIV 0x214 [12:8]** (rz_linux-cip 212f6e88b7 drivers/clk/renesas/r9a07g044-cpg.c:97-130, :229-233; drivers/clk/renesas/rzg2l-cpg.h:24, :74). Consequences: G1 reads 0x214 at probe. **INFERENCE** (clk core outside the checkout): a field value of 0 is not in the table and gives a zero-divisor warning, so the model must hold the manual reset value 0x401 (field 4 → /5 → DRP_A = 320 MHz). No G1 DT node consumes these clocks (r9a07g054.dtsi has no G0 → G1 diff).

## 3. Clock tree Linux computes (extal = 24 MHz)

| Clock | Path (r9a07g044-cpg.c line) | Rate with manual reset values | Registers that must read correctly |
|---|---|---|---|
| I (CPU) | PLL1 / DIVPL1 (:127, :167) | 1200 MHz | 0x004, 0x008, 0x200 |
| P0 (SCIF, WDT pclk, OSTM, I2C) | PLL2/2/8 / DIVPL2A (:128, :139, :145, :168) | 100 MHz | 0x204[2:0] |
| P1 (GIC, IA55_CLK, DMAC, SDHI aclk) | PLL3/2/4 / DIVPL3B (:150, :152, :171) | 200 MHz | 0x208[6:4] |
| P2 (IA55_PCLK, DSI pclk) | PLL3/2/4/2 / DIVPL3A (:153, :173) | 100 MHz | 0x208[2:0] |
| OSC (WDT oscclk, GPIO) | extal (:125) | 24 MHz | none |
| SD0 | mux 533/400/266 (:179) | 533.33 MHz | 0x218[1:0], 0x280[28] |
| TSU, M0, ZT, M2 | fixed (:170, :174-175, :187) | 80, 200, 100, 266.67 MHz | none |

These rates agree with the manual's divider annotations: P0 100 MHz, P1 200 MHz, P2 100 MHz (§7.2.4.17-18, p.275-277). FACT.

G1 (rz-6.12-cip14) delta: adds `DRP_M`, `DRP_D`, `DRP_A` (§2.6) and five module clocks `stpai_*` on **CLK_ON 0x5E8 b0-b4** (monitor 0x768) (rz_linux-cip 212f6e88b7 drivers/clk/renesas/r9a07g044-cpg.c:403-415). The manual lists `CPG_CLKON_DRP` 0x5E8 / `CPG_CLKMON_DRP` 0x768 (reset 0) and `CPG_RST_DRP` 0x8E8 (reset 0) / `CPG_RSTMON_DRP` 0xA68 (reset 0x1) (Table 7.5 (5/6), p.250). None of the rows above change: the SCIF, OSTM, GIC, IA55 (IRQC), GPIO (PFC), WDT and SDHI clock and reset entries and the critical-clock list are identical in G0 and G1 (the 55-line diff touches only the DRP additions).

## 4. Power domains in v6.12.59

- **FACT.** With `#power-domain-cells = <0>` the CPG registers itself as a **single always-on genpd** (rzg2l-cpg.c:1776-1782 → :1720-1742). `rzg2l_cpg_pd_setup(pd, true)` sets `GENPD_FLAG_PM_CLK | GENPD_FLAG_ACTIVE_WAKEUP | GENPD_FLAG_ALWAYS_ON` with the `pm_domain_always_on_gov` governor and installs no `power_on`/`power_off` (:1701-1718).
- **FACT.** When a device attaches, every `<&cpg CPG_MOD n>` entry in its `clocks` is added to the device's pm_clk list (`no_pm_mod_clks` excepted: CRU sysclk/vclk, r9a07g044-cpg.c:441-444). Core clocks are never added (rzg2l-cpg.c:1577-1654). Runtime PM resume and suspend therefore become CLK_ON writes and CLK_MON polls (§2.2), with no MSTOP access.
- **FACT.** The CPG has no power-gating registers. In v6.12.59 on V2L, "power domain" means clock gating only.
- **Probe sequence** (FACT, rzg2l-cpg.c:1839-1901):
  1. Core clocks are registered (:1878-1879), which reads PLL1 and the dividers/muxes and writes SIPLL5_STBY.
  2. Module clocks are registered (:1881-1882). The three critical clocks (`gic`, `ia55_clk`, `dmac_aclk`, r9a07g044-cpg.c:435-439) get `CLK_IS_CRITICAL` (rzg2l-cpg.c:1378-1383). **INFERENCE** (clk core, outside the checkout): the core enables critical clocks at registration, so each one gets the CLK_ON write and 10 us CLK_MON poll of §2.2.
  3. The clk provider (:1884), genpd provider (:1892) and reset controller (:1896) are registered. There is no MSTOP pass.
- **INFERENCE.** At `late_initcall`, the clk core's unused-clock sweep disables every registered module clock that reads enabled in CLK_MON but has no enable count. It writes CLK_ON off (no MSTOP). WDT0 is affected if U-Boot left it running and Linux has not started it (§5). Unregistered clocks (SYC, CA55, CST, MHU, ... and, in G0 only, DRP) are never touched.
- G1 (rz-6.12-cip14) delta: G1 also registers the `stpai_*` clocks (§3), so the sweep can switch off CLK_ON 0x5E8 b0-b4 if firmware left them on with CLK_MON showing them. Same PM-domain code as G0.

## 5. Bits touched for the early consumers

| Consumer (DT) | Clock bits (CLK_ON / CLK_MON) | Reset bits (RST / RSTMON) | MSTOP (manual mapping; **not written by G0/G1**) | Manual reset | Expected post-firmware |
|---|---|---|---|---|---|
| SCIF0 `scif0_clk_pck` (r9a07g054.dtsi:380-397) | 0x584 b0 / 0x704 b0 (r9a07g044-cpg.c:334-335) | 0x884 b0 / 0xA04 b0 (:415) | 0xB68 (MCPU2) b1 | clock off, reset asserted, MSTOP 0 | on / released (INFERENCE: BL2 prints on SCIF0) |
| GIC `gic` (critical) | 0x514 b0 / 0x694 b0 (:206-207) | 0x814 b0-1 defined (:372-373) but not referenced: the GIC node has no `resets` (r9a07g054.dtsi:1049-1057) | 0xB80 (REG1) b7 | on / released | on / released |
| CPU `I` + OPP (r9a07g054.dtsi:45-69, :94, :104) | none | none | none | DIVPL1 = 0 (1200 MHz) | unknown; Linux reprograms |
| WDT0 `pclk`, `oscclk` (r9a07g054.dtsi:1249-1262; enabled at rzg2l-smarc-som.dtsi:384-387) | 0x548 b0,b1 / 0x6C8 b0,b1 (:234-237) | 0x848 b0 / 0x9C8 b0 (:386) | 0xB7C (REG0) b2 | on / released | on / released, WDT running (boot-chain-firmware.md §1) |
| SDHI0 (later; r9a07g054.dtsi:1059-1073) | 0x554 b0-3 / 0x6D4 b0-3 (:246-253) | 0x854 b0 / 0x9D4 b0 (:389) | 0xB6C (PERI_COM) b0 | off / asserted | on / released (INFERENCE: U-Boot mmc0) |
| Related early ones | GPIO 0x598 b0 (pinctrl, `devm_clk_get_enabled`, linux v6.12.59 drivers/pinctrl/renesas/pinctrl-rzg2l.c:2762); IA55 0x518 b0-1; OSTM1/2 0x534 b1-2 | GPIO 0x898 b0-2 are **never deasserted by Linux** (no reset calls in pinctrl-rzg2l.c); IA55 0x818 b0 (linux v6.12.59 drivers/irqchip/irq-renesas-rzg2l.c:565-569); OSTM 0x834 (linux v6.12.59 drivers/clocksource/renesas-ostm.c:172-178) | PERI_CPU b6/b13, REG0 b4-6 | GPIO off/asserted at reset | GPIO released (INFERENCE: firmware muxes SCIF0 pins) |

The MSTOP column is the manual's module-to-MSTOP mapping as the v6.18.55 tables encode it (see "Newer mainline"); it is kept for the model's register file and for a later v6.18 regression target, not because G0 or G1 writes it.

G1: no delta in these rows. `irq-renesas-rzg2l.c` and `renesas-ostm.c` are identical in G0 and G1. G1's pinctrl driver also takes the GPIO clock with `devm_clk_get_enabled` and makes no reset calls (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:2934).

**SCIF0 sequence (b-path, FACT):**
1. `sci_parse_dt` deasserts the reset **before** runtime PM (sh-sci.c:3358-3367): write 0x884 = 0x00010001, then poll 0xA04 b0 == 0.
2. Runtime resume (`sci_port_enable`, sh-sci.c:582-596) enables `fck` through the always-on genpd's pm_clk list and `clk_prepare_enable`: write 0x584 = 0x00010001, then poll 0x704 b0 within 10 us. No MSTOP write.
3. `uartclk = clk_get_rate(fck)` = P0 = 100 MHz (sh-sci.c:593-595).

Earlycon (`rzscifa_early_console_setup`, sh-sci.c:3742-3747, declared for `renesas,scif-r9a07g044` at :3775) touches no CPG register. **CPG is not needed for answer (a); it is required for (b).** INFERENCE.

**CPU frequency path:** `cpufreq-dt` sets the `I` clock to 150, 300, 600 or 1200 MHz. That is a single hiword-masked write to PL1_DDIV `[1:0]` with no busy poll (§2.6). The OPPs list `opp-microvolt`, but the CPUs have no `cpu-supply`. **ASSUMPTION:** cpufreq-dt instantiates for `renesas,r9a07g054` (cpufreq-dt-platdev is outside the checkout).

**WDT0 (FACT):** the driver reads both clock rates at probe (OSC 24 MHz, P0 100 MHz; linux v6.12.59 drivers/watchdog/rzg2l_wdt.c:267-284). On start or restart it does runtime resume plus a reset deassert of 0x848 b0 (:99-110, :164-199). G1: identical file.

## 6. Existing QEMU analogues (qemu v11.1.2, read-only survey)

- No Renesas CPG model exists. `hw/char/renesas_sci.c` and `hw/timer/renesas_{cmt,tmr}.c` belong to the RX62N and are unrelated.
- `hw/misc/imx8mp_ccm.c` (178 lines) is a plain register file with set/clr/toggle aliases: a structural precedent for a register-file CCM.
- `hw/misc/npcm_clk.c` models PLLs, selectors and dividers with the QEMU Clock API (`qdev_init_clock_out`, `clock_update_hz`): a precedent for later exporting P0 and SD0 rates to device models.
- `hw/misc/iotkit-sysctl.c` precedent: reset-vector registers that drive CPU start. Relevant to the CA55 PCH handshake at Stage B.

## 7. Minimal faithful model proposal

**Scope M1-M4 (FUNCTIONAL, faithful for what is modelled):**
1. **Register file** over 0x000-0xFFF, holding the manual reset values of Table 7.5. Writes go through per-register descriptors: field masks, the write-enable map (§2.1), read-only registers, and reserved bits fixed at their reset values. Offsets 0x1000-0xFFFF and undocumented holes log `-d guest_errors` and read 0. The file includes PL3C_SDIV (0x214 = 0x401) and the DRP CLK_ON/CLK_MON/RST/RSTMON registers, which G1 reads (§2.6, §3).
2. **Mirror semantics.** `CLK_MON(n) := CLK_ON(n)` and `RSTMON(n) := ~RST(n) & mask(n)`, computed on read so they update instantly. Linux's 10 us CLK_MON window and 200 us RSTMON window are satisfied because QEMU has no settle latency. `mask(n)` comes from the RSTMON field map, since RST and RSTMON widths can differ (for example RSTMON_DDR is 7 bits).
3. **PLL readbacks.** SAMPLL1_CLK1/CLK2 are R/W with the manual reset values, giving 1200 MHz. SAMPLLn_MON / SIPLLn_MON report LOCK|RESETB consistent with each PLL's STBY state. CLKSTATUS always reads 0 because every switch completes instantly. That is faithful for any timing Linux can observe.
4. **MSTOP.** R/W with the enable convention, no peripheral effect. G0 and G1 never write it (§2.4), so for the pinned guests this is a storage-only register set; only firmware (and the later v6.18 regression target) writes it.
5. **PCH handshake** (Stage B, BL31). Implement per the `boot-chain-firmware.md` contract.
6. **Start states.** Firmware mode starts at the Table 7.5 values. Direct mode adds an overlay with the measured post-firmware values (§5 column; to be measured, see the questions below). Keep it as a per-register table, not code. Because G0/G1 never clear MSTOP, a direct-mode overlay that sets MSTOP bits for a module Linux uses would leave that module stopped on silicon; record the measured MSTOP values but do not give them a peripheral effect until that behaviour is evidenced.

**Not supported, listed as gaps:** a peripheral seeing its clock off, reset asserted or MSTOP set (the silicon behaviour is unknown, spec §7); real PLL relock and lock timing; frequency effects on emulation speed; WDT overflow reset (CPG_WDTOVF_RST / WDTRST_SEL R/W only); OTP PLL selection. A later step can export per-module "operational" GPIO lines and P0/SD0 `Clock` outputs.

**Verification:** a qtest that asserts the manual reset values (Table 7.5 rows used above, including 0x214 = 0x401 and RSTMON_DRP 0xA68 = 0x1), the WEN semantics (a write without WEN is ignored), CLK_MON = CLK_ON, RSTMON = ~RST & mask (mutation: break the inversion and expect a red test), and the PLL1 readback 0x1901/0x180601.

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target (`docs/sources.md`). Citations are `linux v6.18.55 drivers/clk/renesas/<file>:N`. These are the places where the first draft of this note (written against v6.18.55) differs from v6.12.59:

- **MSTOP is driven per module clock.** Each module clock carries `MSTOP(reg, mask)` (rzg2l-cpg.h:86; r9a07g044-cpg.c:244-401, e.g. `gic` → `MSTOP(BUS_REG1, BIT(7))` at :244-245). Enabling a clock clears the bits when the shared use count rises from 0; disabling sets them when it drops to 0, but a stop shared only with critical clocks is never set (rzg2l-cpg.c:1238-1292). Enable order: CLK_ON write, MSTOP clear, CLK_MON poll (:1330-1375); disable order: MSTOP set, then CLK_ON off (:1356-1363). The CLK_ON write is under the spinlock.
- **MSTOP at probe and resume.** After all clocks are registered, `rzg2l_mod_clock_init_mstop()` sets MSTOP for every module clock whose CLK_MON bit reads 0 (rzg2l-cpg.c:1477-1496, called at :1924), and again on resume (:1946-1952). With v6.18 a model's CLK_MON values therefore decide which MSTOP bits Linux sets at boot.
- **Reset timeout revert.** `__rzg2l_cpg_assert` writes the opposite value back to RST when the RSTMON poll times out (rzg2l-cpg.c:1641-1679).
- **PM domain.** `rzg2l_cpg_add_clk_domain` sets the same three genpd flags directly (rzg2l-cpg.c:1851-1872); runtime PM therefore also produces MSTOP updates.
- **DRP_A** is present in mainline v6.18 (r9a07g044-cpg.c:232), as in G1.
- SCIF0 runtime resume in v6.18 is: write 0x584 = 0x00010001, write 0xB68 = 0x00020000 (clear MSTOP MCPU2 b1), poll 0x704 b0 within 10 us.

## Claims to verify

1. **RSTMON is inverted relative to RST** (1 = in reset). Evidence: HW manual Rev 1.50 §7.2.4.135, p.409 vs §7.2.4.173, p.450; Table 7.5 (3/6)-(5/6), p.248-250; rzg2l-cpg.c:1480-1481. `boot-chain-firmware.md` §2 uses the word "mirrors" and should be read as the inverted mirror. (TF-A side confirmed; see the Verification table.)
2. Linux enables a clock only if CLK_MON shows it within **10 us** (rzg2l-cpg.c:1239-1240). An asynchronous or timer-delayed mirror would break this.
3. **PL1_DDIV reset value conflict:** Table 7.5 (1/6), p.246 says `0x0000000x`, but §7.2.4.16, p.274 says 00b.
4. **The GPIO resets (0x898) are never deasserted by G0 or G1 Linux** (no reset calls in pinctrl-rzg2l.c in either tree), although DT lists them (r9a07g054.dtsi:910-912). The direct-mode overlay must therefore release them.
5. Critical clocks are enabled at registration and unused clocks are swept at `late_initcall`. These are clk-core behaviours outside the sparse checkout (drivers/clk/clk.c).
6. cpufreq-dt instantiates for r9a07g054 (drivers/cpufreq/cpufreq-dt-platdev.c, not in the checkout).
7. A read-as-zero PLL1 yields a 0 Hz CPU clock without a trap (rzg2l-cpg.c:974; arm64 UDIV-by-zero semantics).
8. **G1 only:** DRP_A with PL3C_SDIV = 0 produces a zero-divisor warning rather than a wrong rate (clk-core `divider_recalc_rate`, outside the checkout). The model avoids it by holding the manual reset value 0x401.
9. **MSTOP has no Linux writer on V2L in G0/G1.** Confirm on the EVK (question 6) that MSTOP values after Linux boot equal the post-firmware values.

## Questions for the EVK

All are read-only `md.l` reads at the **U-Boot prompt before `bootm`** (post-firmware state) unless stated otherwise.

1. `md.l 0x11010000 0x14` and `md.l 0x11010040 4`: SAMPLL1_STBY/CLK1/CLK2/MON, PLL1_SETTING, OTPPLL0-2_MON. Is PLL1 OTP-driven? Do CLK1/CLK2 still equal 0x1901/0x180601?
2. `md.l 0x11010200 0x8`, `md.l 0x11010280 1`, `md.l 0x11010408 5`: divider, selector and CLKSTATUS values left by firmware (P0 divider = 100 MHz? PL3C_SDIV still 0x401?).
3. `md.l 0x11010500 0xB8` and `md.l 0x11010680 0xB8`: all CLK_ON/CLK_MON, to confirm CLK_MON == CLK_ON bit for bit (including CLKON_DRP 0x5E8).
4. `md.l 0x11010800 0xB8` and `md.l 0x11010980 0xB8`: all RST/RSTMON, to confirm RSTMON == ~RST & mask (in particular SCIF 0x884/0xA04, GPIO 0x898/0xA18, SYC 0x828/0x9A8, SDHI 0x854/0x9D4, DRP 0x8E8/0xA68).
5. `md.l 0x11010b60 0xC`: MSTOP values left by firmware.
6. Repeat 3-5 **post-Linux** from the G1 image (with `/dev/mem`, or via `debugfs` `clk_summary`). This records what the unused-clock sweep changed and whether MSTOP is untouched by Linux, as G0/G1 source predicts. Label it post-Linux: it is neither the reset nor the post-firmware state. (The `mstop` debugfs file exists only in v6.18-era kernels.)

## Verification

| Claim | Result | Evidence |
|---|---|---|
| RSTMON is the inverse of RST | **Confirmed** | linux v6.12.59 `drivers/clk/renesas/rzg2l-cpg.c:1454-1482` `rzg2l_cpg_deassert`: writes the bit as 1, then polls until the RSTMON bit is 0 (same in G1 and in v6.18.55 `__rzg2l_cpg_assert`). TF-A `f59ed5a31` `plat/renesas/rz/common/plat_pm.c:56-62` polls the same way for `RST_CA55`. `docs/research/boot-chain-firmware.md` is corrected. |
| CLK_MON polled for 10 µs with no delay | **Confirmed** | linux v6.12.59 `rzg2l-cpg.c:1239-1240` `readl_poll_timeout_atomic(..., 0, 10)` in the module clock enable path (same in G1 and v6.18.55) |
| PCHMON semantics (PACCEPT/PDENY, not "0x08") | **Confirmed; the earlier doc was wrong** | TF-A `f59ed5a31` `plat_pm.c:30-70`: PSTATE `0x08` is written to PCHCTL[23:16] together with PREQ; PCHMON bit 0 (PACCEPT) follows PREQ in a four-phase handshake |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7`. Behaviour changes: no MSTOP writes on V2L in G0/G1 (§2.4), no reset-timeout revert (§2.3), DRP_A/PL3C_SDIV and DRP module clocks are G1-only (§2.6, §3). v6.18.55 behaviour kept under "Newer mainline". |

## EVK results (2026-10-29, U-Boot prompt, downstream firmware; `../evidence/EVK-2026-10-29-post-firmware.md`)

- **OBSERVED.** The PLL1 readback, the GIC600/IA55, SCIF, GPIO, SYC and DRP clock/reset pairs, MSTOP (all 0) and PL3C_SDIV `0x401` match (EVK-R10, R12-R14, R18, R19, R72).
- **OBSERVED, post-firmware state differs from the prediction** (direct-mode values for M3b): PL3A_DDIV `0x208` = `0x100` (DIVPL3C = 1); PL2SDHI_DSEL `0x218` = `0x22` (SEL_SDHI0 = SEL_SDHI1 = 2); PL3_SSEL `0x408` = `0x11` (b8 = 0, against the reset value `0x111`); GTM CLK_ON/CLK_MON `0` (OSTM clocks off); WDT CLK_ON `0xFF`, RST `0xF`, RSTMON 0; SDHI CLK_ON/CLK_MON `0xFF`, RST `0x3`, RSTMON 0 (EVK-R11, R15-R17).
- **OBSERVED.** RSTMON is the inverse of RST in every word of `0x800-0xAFF` (EVK-X02).
- **Conflict recorded (manual vs silicon).** CLK_MON equals CLK_ON for every implemented bit, but not for the WDT reserved bits 7:6: CLK_ON_WDT reads `0xFF` and CLK_MON_WDT reads `0x3F` (EVK-X01, R16). Table 7.5 gives both a reset value of `0xC3` (bits 7:6 = 1), so the manual says CLK_MON's reserved bits read 1, while silicon reads 0. The rule "CLK_MON = CLK_ON" therefore holds for implemented bits only.
