# PFC / pinctrl research: what QEMU must provide for SCIF0 to bind

**Date:** 2026-10-08 (M0 research; re-based 2026-10-08 onto the pinned guest kernels, see `docs/sources.md` "Pinned guest kernels")
**Scope:** the GPIO/PFC block at `0x11030000` as used by Linux `pinctrl-rzg2l`, TF-A and U-Boot, up to the point where `sh-sci` binds SCIF0. Answers the pinctrl part of spec §20 (b).

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference), the firmware sources below and the RZ/V2L HW manual Rev 1.50, plus the passive EVK boot log `docs/evidence/EVK-2026-10-08-boot-log.md`. The first draft of this note was written against linux v6.18.55; where that kernel differs, the difference is kept in "Newer mainline (v6.18.55)" near the end.

**Sources:** as in `scif.md` (linux v6.12.59; rz_linux-cip `212f6e88b7`; HW manual Rev 1.50, printed page numbers; TF-A `renesas-rz/rzg_trusted-firmware-a` `f59ed5a31`; U-Boot `renesas-rz/renesas-u-boot-cip` `4eebfbaa4e`). Effective configuration: TF-A was compiled with **`-DRZG2L=1 -DRZV2L=1`** (compile log); U-Boot `.config` has `CONFIG_PINCTRL_RZG2L=y`. None of the cited firmware files are modified downstream in the studied build.

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N`:

| Short | Full path |
|---|---|
| `pinctrl-rzg2l.c`, `Kconfig` (pinctrl) | `drivers/pinctrl/renesas/` |
| `devicetree.c` | `drivers/pinctrl/` |
| `irq-renesas-rzg2l.c` | `drivers/irqchip/` |
| `dd.c` | `drivers/base/` |
| `r9a07g044-cpg.c` | `drivers/clk/renesas/` |
| `r9a07g054.dtsi`, `rzg2l-smarc-pinfunction.dtsi`, `rzg2l-smarc-som.dtsi`, `rzg2l-smarc.dtsi` | `arch/arm64/boot/dts/renesas/` |
| `rzg2l-pinctrl.h` | `include/dt-bindings/pinctrl/` |
| `defconfig` | `arch/arm64/configs/` |

G1 citations are written out in full as `rz_linux-cip 212f6e88b7 <path>:N`. In G1, `irq-renesas-rzg2l.c`, `devicetree.c`, `r9a07g054.dtsi`, `rzg2l-smarc-pinfunction.dtsi`, `rzg2l-smarc.dtsi` and `rzg2l-pinctrl.h` are identical to v6.12.59; `rzg2l-smarc-som.dtsi` differs only in the QSPI flash partition layout. The 745-line `pinctrl-rzg2l.c` delta is analysed in §10.

Labels: **FACT**, **INFERENCE**, **ASSUMPTION**, **CONFLICT**, **OBSERVED** (hardware observation, EVK boot log).

---

## 1. Evidence record (spec §6)

| Field | Value | Label / evidence |
|---|---|---|
| MMIO | `0x11030000`, size `0x10000` | FACT: HW manual Rev 1.50 §41.2, p.3368; r9a07g054.dtsi:898-901 |
| Compatible | `"renesas,r9a07g054-pinctrl", "renesas,r9a07g044-pinctrl"`; the driver matches the second (`r9a07g044_data`) | FACT: r9a07g054.dtsi:899-900; pinctrl-rzg2l.c:3117-3133, 3179-3180 |
| IRQ | none of its own. It is `interrupt-controller` with `interrupt-parent = <&irqc>`; GPIO interrupts route via the IRQC TINT inputs | FACT: r9a07g054.dtsi:904-906 |
| GPIO | `gpio-ranges = <&pinctrl 0 0 392>` (49 ports × 8) | FACT: r9a07g054.dtsi:907; pinctrl-rzg2l.c:2589-2598 |
| Clock | `CPG_MOD R9A07G054_GPIO_HCLK` (OSCCLK parent, CLK_ON offset 0x598 bit 0) | FACT: r9a07g054.dtsi:908; r9a07g044-cpg.c:356-357 |
| Resets | GPIO_RSTN, GPIO_PORT_RESETN, GPIO_SPARE_RESETN (CPG offset 0x898 bits 0-2). **Neither the G0 nor the G1 driver requests them** | FACT: r9a07g054.dtsi:910-912; r9a07g044-cpg.c:427-429; no reset calls anywhere in pinctrl-rzg2l.c in either tree |
| Power domain | `<&cpg>` | FACT: r9a07g054.dtsi:909 |
| Init level | `core_initcall` | FACT: pinctrl-rzg2l.c:3211 |
| DMA | none | — |

## 2. Register layout used by the guests

**FACT** (pinctrl-rzg2l.c:132-158, 3045-3056; HW manual Rev 1.50 §41.2, p.3368-3385). Port offset `off = 0x10 + port`; for P38, `off = 0x36` (pinctrl-rzg2l.c:1841). The manual names registers by this hex index, so the P38 pins live in "PM36/PMC36/PFC36".

| Register | Offset formula | Width (manual) | Reset | P38 instance |
|---|---|---|---|---|
| Pn (output data) | 0x0000 + off | 8 | 0x00 | 0x036 |
| PMn (mode, 2 bits/pin) | 0x0100 + 2·off | 8/16 | 0x0000 | **0x16C** |
| PMCn (GPIO/peripheral select) | 0x0200 + off | 8 | 0x00 | **0x236** |
| PFCm (function, 4-bit nibble per pin, 3 bits used) | 0x0400 + 4·off | 8/16/32 | 0x00000000 | **0x4D8** |
| PINn (input data, RO) | 0x0800 + off | 8 | 0x00 | 0x836 |
| IOLH / SR / IEN / PUPD | 0x1000/0x1400/0x1800/0x1C00 + 8·off | 8/16/32 | see §41.3.7-41.3.9, 41.3.20 | 0x11B0 / 0x15B0 / 0x19B0 / 0x1DB0 |
| ISEL (GPIO interrupt enable) | 0x2C00 + 8·off | 8/16/32 | 0 | 0x2DB0 |
| SD_ch0 / SD_ch1 / QSPI / ETH_ch0 / ETH_ch1 | 0x3000 / 0x3004 / 0x3008 / 0x300C / 0x3010 | 8 | see p.3384-3385 | — |
| **PWPR** | **0x3014** | 8 | **0x80** | — |
| ETH MII/RGMII (Linux `ETH_MODE`; `regs.oen` in G1) | 0x3018 | 8 | **0x03** | — |

Reset values for P38: HW manual Rev 1.50 §41.2.2, p.3370 (PM36); §41.2.3, p.3371 (PMC36); §41.2.4, p.3373 (PFC36); §41.2.10, p.3379 (PWPR); ETH MII/RGMII §41.2.16, p.3384.

**PWPR semantics. FACT** (HW manual Rev 1.50 §41.3.10, p.3404): bit 7 B0WI=1 blocks writes to PFCWE; bit 6 PFCWE=1 allows writes to the **PFC registers only**; bits 5:0 are reserved and read the initial value. PMC is not protected. Linux's definitions agree (`PWPR_PFCWE` "PFC Register Write Enable"; PMC protection, `PWPR_REGWE_A`, and OEN protection, `PWPR_REGWE_B`, exist only on RZ/V2H, pinctrl-rzg2l.c:152-155), and U-Boot writes PMC after relocking (§5.2).

**ETH MII/RGMII. FACT** (HW manual Rev 1.50 §41.3.16, p.3416): bits 1:0 are ETH1_mode/ETH0_mode, 1 = MII (TXC is an input, reset), 0 = RGMII (TXC is an output); bits 7:2 reserved. Linux treats a cleared bit as "output enabled": the `output-enable` pinconf clears the bit (pinctrl-rzg2l.c:997-1049), and DTB-U sets `output-enable` on ET0_TXC (P20_0) and ET1_TXC (P29_0) (rzg2l-smarc-som.dtsi:181-185, 211-215). The register is also saved and restored across system suspend (pinctrl-rzg2l.c:2955-3012). It is not on the console path, but it is written when the Ethernet pin groups are applied.

**PM encoding. FACT** (§41.3.2, p.3388): 00 Hi-Z (reset), 01 input, 10 output, 11 output with input enabled. PMC (§41.3.3, p.3390): 0 GPIO, 1 peripheral. PFC (§41.3.4, p.3392): 000b-101b = Function0-5.

## 3. What `rzg2l_pinctrl_probe` does (G0 and G1)

Code: pinctrl-rzg2l.c:2731-2777 (probe), 2638-2729 (register), 2569-2636 (gpio_register).

1. `devm_platform_ioremap_resource`, then `devm_clk_get_enabled` (GPIO_HCLK on via the CPG) (pinctrl-rzg2l.c:2758-2766). **FACT.**
2. Builds the pin tables in software. The power-source scan is skipped because `rzg2l_hwcfg` has no `drive_strength_ua`, so **SD_ch/ETH/QSPI are not read at probe** (pinctrl-rzg2l.c:2700-2710, 3045-3056). **FACT.**
3. `devm_pinctrl_register_and_init` and `pinctrl_enable` apply the **pinctrl device's own default state (hog)**: `pinctrl-0 = <&sound_clk_pins>`, i.e. `AUDIO_CLK1/2` `input-enable` (rzg2l-smarc-pinfunction.dtsi:11-13, 127-130). This is a 32-bit read-modify-write of **IEN04 @ 0x1820**, setting bits 0 and 8 (pinctrl-rzg2l.c:2715-2722, 795-813, 1392-1397; pins 1968-1969). **FACT** for the code path; the exact value is an INFERENCE.
4. `rzg2l_gpio_register`: finds the IRQ parent. **If the IRQC irq domain is not registered yet, it returns `-EPROBE_DEFER`** (pinctrl-rzg2l.c:2580-2587). It then checks that `gpio-ranges` equals 0/0/392, or fails with `-EINVAL` (2589-2598), and adds the gpiochip (2629). **FACT.**
5. The gpiochip core processes the `gpio-hog` children (rzg2l-smarc-pinfunction.dtsi:21-26, 34-39, 88-93; rzg2l-smarc-som.dtsi:240-245, 266-271). The hogs are P42_2 and P42_3 output-low, and P39_2, P4_1 and P41_1 output-high. Each one runs `rzg2l_gpio_request` (PMC read-modify-write, clear bit), then `direction_output` (Pn read-modify-write, then PMn 16-bit read-modify-write to 10b) (pinctrl-rzg2l.c:1596-1626, 1628-1647, 1679-1711). **FACT** for the driver code. That gpiolib applies the hogs during `gpiochip_add_data`, and reads PMC/PM for every valid line via `get_direction` (1649-1667), is an **INFERENCE**: drivers/gpio is not in the reviewed files.

**Polls:** none. **ID/version registers:** none. **No register value is checked for success.** **FACT**, from the full probe path above.

## 4. Applying SCIF0 `pinctrl-0`

The DT is `scif0_pins: pinmux = <RZG2L_PORT_PINMUX(38, 0, 1)>, <RZG2L_PORT_PINMUX(38, 1, 1)>` (rzg2l-smarc-pinfunction.dtsi:76-79; macro in rzg2l-pinctrl.h:18). The driver core applies it before `sci_probe`. `rzg2l_pinctrl_set_mux` then calls `rzg2l_pinctrl_set_pfc_mode` per pin with `func = 1` (`func_base` is 0 for RZ/G2L) (pinctrl-rzg2l.c:484-519).

**FACT** (per pin, in order; pin 0 then pin 1, all read-modify-write, under the driver spinlock):

| # | Access | P38_0 result | after P38_1 |
|---|---|---|---|
| 1 | PM36 @0x16C, 16-bit: clear 2 bits | 0x0000 | 0x0000 |
| 2 | PWPR @0x3014, 32-bit writes: 0x00, then 0x40 | PFCWE=1 | — |
| 3 | PMC36 @0x236, 8-bit: clear the pin bit | 0x00 | 0x01 to 0x01 & ~0x02 |
| 4 | PFC36 @0x4D8, 32-bit: nibble = 1 | 0x00000001 | **0x00000011** |
| 5 | PMC36, 8-bit: set the pin bit | 0x01 | **0x03** |
| 6 | PWPR, 32-bit writes: 0x00, then 0x80 | relocked | — |

(pinctrl-rzg2l.c:451-482, 3014-3027.) The PMC writes in this path are plain `writeb`, not the `pmc_writeb` hook (pinctrl-rzg2l.c:467, 476). **INFERENCE:** the end state equals what TF-A leaves (§5), so on silicon this rewrite is idempotent apart from the transient GPIO-mode glitch in step 3.

DTB-U also enables **SCIF2** with `scif2_pins` P48_0/1/3/4 function 1 (rzg2l-smarc-pinfunction.dtsi:81-86; rzg2l-smarc.dtsi:169-176). That is the same sequence on PM40 @0x180, PMC40 @0x240 and PFC40 @0x500 (P48 is `off = 0x40`, pinctrl-rzg2l.c:1851).

## 5. Firmware: post-firmware vs reset

### 5.1 TF-A BL2 `pfc_setup()` (called from `TF-A plat/renesas/rz/common/bl2_plat_setup.c:157`)

`pfc_mux_setup` (`TF-A plat/renesas/rz/common/drivers/pfc.c:168-201`) does the following:

1. Writes PWPR 0x00 then 0x40 (32-bit).
2. For each active table entry, writes PMC (8-bit), then PFC (32-bit).
3. Relocks with PWPR 0x00 then 0x80.

With `RZG2L=1` the active entries are (pfc.c:44-63, 86-95; register addresses from `plat/renesas/rz/common/include/pfc_regs.h:148, 197, 318`):

| Entry | PMC | PFC |
|---|---|---|
| P47 ("sd0") | PMC3F @0x23F = 0x03 | PFC3F @0x4FC = 0x00000011 |
| P19 ("sd1") | PMC23 @0x223 = 0x03 | PFC23 @0x48C = 0x00000011 |
| **P38 ("scif0")** | **PMC36 @0x236 = 0x03** | **PFC36 @0x4D8 = 0x00000011** |

The IOLH/PUPD/SR flags are OFF for these three entries. PM36 is **not** written.

`pfc_qspi_setup` and `pfc_sd_setup` (pfc.c:203-257) write IOLH/PUPD/SR for QSPI (0x0A-0x0C) and SD (0x06-0x09), and IEN for SD, **using 64-bit stores** (`mmio_write_64`), plus SD_ch0 = 1 and SD_ch1 = 0 (32-bit stores).

### 5.2 U-Boot

U-Boot has `CONFIG_PINCTRL_RZG2L=y`, but its `scif0` node has **no** `pinctrl-0` (`U-Boot arch/arm/dts/smarc-rzv2l.dts:71-74`). **INFERENCE:** U-Boot does not touch P38. Its set-mux helper skips pins that are already configured and writes PMC after relocking PWPR (`U-Boot drivers/pinctrl/renesas/rzg2l-pfc.c:459-487`).

### 5.3 SCIF0 pins: summary

| Register | Reset (manual) | Post-firmware (INFERENCE from TF-A) | Post-Linux (INFERENCE) |
|---|---|---|---|
| PM36 @0x16C | 0x0000 | 0x0000 | 0x0000 |
| PMC36 @0x236 | 0x00 | **0x03** | 0x03 |
| PFC36 @0x4D8 | 0x00000000 | **0x00000011** | 0x00000011 |
| PWPR @0x3014 | 0x80 | 0x80 | 0x80 |

Spec §9 "SCIF0 pin function selected" therefore means PMC36=0x03 and PFC36=0x11 in the direct-mode overlay. TF-A also leaves the P47/P19/QSPI/SD values above.

**OBSERVED (indirect).** On the EVK, BL2, BL31, U-Boot and the earlycon all print on SCIF0 before Linux applies any pinmux (EVK boot log: earlycon at `0x1004b800`, ttySC0 probe only at 0.594 s). The P38 pins therefore already carry the SCIF0 function when the kernel starts, which fits the TF-A table but does not distinguish PMC36/PFC36 values bit by bit.

## 6. Dependencies: GPIO, IRQ and IRQC

- **FACT.** `pinctrl-rzg2l` binds only after the **IRQC** (`renesas,rzg2l-irqc` @ `0x110A0000`) has registered its hierarchical domain (pinctrl-rzg2l.c:2580-2587).
- **FACT.** IRQC probe does **no MMIO** (irq-renesas-rzg2l.c:531-614; the only register accesses are in the irq_chip callbacks and syscore suspend/resume). It needs the GIC parent domain (543-547), its DT `interrupts` (559-563), a CPG reset it deasserts with `devm_reset_control_get_exclusive` + `reset_control_deassert` (565-573), and runtime-PM resume, i.e. CPG clocks and the PM domain (575-580). It then adds the hierarchy domain (583-590). A mapped IRQC region (even RAZ/WI) plus a working CPG therefore lets the IRQC probe. `ARCH_RZG2L` selects the IRQC driver (linux v6.12.59 drivers/soc/renesas/Kconfig:50-54).
- **INFERENCE.** The resulting chain for spec §20 (b) is: GIC → CPG (clock + reset + RSTMON/CLK_MON) → IRQC probe → pinctrl probe → `sh-sci` probe.
- **OBSERVED (indirect).** On the EVK image the real console probes at 0.594 s (EVK boot log). If that image's `scif0` node carries `pinctrl-0` as DTB-U does, `pinctrl-rzg2l` and the IRQC had bound by then. The image's DT is downstream, so this is not yet proof for DTB-U (question 5).
- **FACT.** GPIO interrupts (ISEL, IRQC TINT) are exercised only by `adv7535` (`interrupt-parent = <&pinctrl>; interrupts = <RZG2L_GPIO(2, 1) …>`, rzg2l-smarc.dtsi:63-68). That device sits behind I2C1, and nothing on the console path uses GPIO interrupts. When such an interrupt is allocated, the driver sets the pin's ISEL bit and maps it to IRQC input `9 + TINT` (pinctrl-rzg2l.c:2355-2394; `RZG2L_TINT_IRQ_START_INDEX` 171).
- **FACT** (see Verification). If the pinctrl device **never binds**, `sh-sci` stays deferred: `dt_to_map_one_config` turns "no pin controller found" into `-EPROBE_DEFER` whenever `CONFIG_MODULES` is set and the node lacks `pinctrl-use-default`, without consulting the deferred-probe timeout (devicetree.c:123-136; dd.c:288-301; defconfig:120 `CONFIG_MODULES=y`). The spec §11 wording "defers forever" holds for the defconfig build.

## 7. If the PFC were a RAZ/WI stub (`create_unimplemented_device`)

- **Would probe succeed? Yes. FACT** (§3: no polls, no checks), provided the IRQC is bound.
- **Would SCIF bind? Yes. FACT.** `set_mux` only writes; it never verifies a read-back. TX/RX in QEMU do not depend on pin state.
- **Is it acceptable? No: silent-wrong** under spec §7, which allows RAZ only where the guest only writes or zero is a faithful value:
  - The driver read-modify-writes PFC/PMC/PM/Pn/IEN. A pin-1 update after pin 0 reads 0 and drops pin 0's function. Silicon would hold 0x11; the stub holds nothing.
  - `get_direction` and `gpio_get` read PMC/PM/PIN/Pn (pinctrl-rzg2l.c:1649-1667, 1713-1731). Hogged outputs would report "input", and `gpio_get` returns `-EINVAL` for PM=00 or PM=11.
  - In direct mode, PMC36/PFC36 must read 0x03/0x11, PWPR 0x80 and ETH MII/RGMII 0x03 (§5.3, §2); RAZ reads 0.
  - debugfs pinmux/pinconf output and G1/M7 firmware read-modify-writes would diverge.
- **Unmapped (no device): fatal. INFERENCE.** The first `readw(PM)` in a probe or hog would take a synchronous external abort in kernel context, which oopses and very likely panics the boot.

## 8. Minimal faithful model proposal

`TYPE_RZG2L_PFC` (RZ/G2L family; V2L reuses the G2L pin tables), **FUNCTIONAL / faithful** for configuration, **STUB-level** for pin I/O.

- **Backing store:** a byte-addressable register file over the defined offsets in §2, with manual reset values. Reserved bits are read-only at their reset value: PFC nibble bit 3, PM bits above the port's pin count, PWPR bits 5:0, ETH MII/RGMII bits 7:2, ports and pins absent per Table 41.x.
- **PWPR:** stores B0WI. PFCWE changes only while B0WI was 0 before the access (ASSUMPTION; the manual does not say whether the old or the new B0WI gates a single combined write, and no guest relies on it). PFC writes with PFCWE=0 are **dropped and logged** (`LOG_GUEST_ERROR`). PMC and ETH MII/RGMII are not gated.
- **Access sizes:** accept 8/16/32 everywhere the manual lists them, **32-bit at PWPR**, and **64-bit stores on the IOLH/SR/PUPD/IEN ranges** (TF-A). This conflicts with the manual (§9).
- **PIN:** for pins with PM=11 (output with input enabled), PIN mirrors Pn. For other modes it reads a per-pin board input level, default 0, exposed as qdev GPIO inputs for later board wiring. ASSUMPTION: the default level is not measured; it is listed as a gap.
- **Undefined offsets:** RAZ/WI with `LOG_GUEST_ERROR`, pending the EVK answer.
- **Post-firmware overlay (direct mode):** PMC36=0x03, PFC36=0x11, PMC3F=0x03, PFC3F=0x11, PMC23=0x03, PFC23=0x11, SD_ch0=1, SD_ch1=0, and the TF-A QSPI/SD IOLH/PUPD/SR/IEN values (pfc.c:99-166). PWPR stays 0x80.
- **Not modelled:** electrical effects (IOLH/SR/PUPD/NOD/SMT/filters are stored only); ETH MII/RGMII direction effects (stored only); ISEL → IRQC TINT routing (stored; no interrupt generation until a milestone needs `adv7535`), listed as UNSUPPORTED; peripheral-signal routing (the SCIF chardev is wired directly, independent of PMC/PFC). **ASSUMPTION:** muxing does not gate the UART in QEMU. Gating it would add no guest-observable fidelity on the console path, and the decision is recorded here.
- **qtests:** reset values (PWPR 0x80, ETH MII/RGMII 0x03, PM/PMC/PFC 0, IEN04 0); a PFC write with PWPR locked is dropped; the unlock, write, read-back sequence; PMC writable while locked; 64-bit IOLH store and read-back. Mutation: remove the PWPR gate and the locked-write test must fail.

## 9. Conflicts recorded

1. **PWPR width.** The manual gives 8-bit (§41.2.10, p.3379). Linux, TF-A and U-Boot all use 32-bit stores (pinctrl-rzg2l.c:3020-3025; TF-A pfc.c:173-174, 199-200; U-Boot rzg2l-pfc.c:474-483). Silicon evidently accepts them.
2. **64-bit stores.** The manual lists IOLH/SR/PUPD/IEN as 8/16/32 (p.3376, p.3385). TF-A uses `mmio_write_64` (pfc.c:187-195, 210-250).
3. **PFC field width.** The manual uses 3-bit fields with bit 3 reserved (p.3392). Linux uses `PFC_MASK = 0x0f` (pinctrl-rzg2l.c:158). Harmless.
4. **Sequence order.** Manual §41.4.2 (p.3421) sets PMC=1 then PFC. Linux sets PMC=0, then PFC, then PMC=1. TF-A sets PMC then PFC. A register-file model is order-independent.
5. **Function number for SCIF0 on P38.** The manual defers to an external "Pin function list" spreadsheet (§41.1.2, p.3354) that is not in our extracted text. Function 1 comes from DT and TF-A only.
6. **Suspend/resume of PUPD (guest quirk, G0 and G1).** For ports with four or more pins, `rzg2l_pinctrl_pm_setup_regs` saves and restores the second PUPD word through `PUPD(off)` instead of `PUPD(off) + 4` (pinctrl-rzg2l.c:2821-2825; rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:2993-2997). On resume the high-half value lands in the low word. This is guest behaviour, not a model concern; recorded so that a suspend/resume test is not misread as a model bug. Fixed in v6.18 (below).

## 10. G1 (rz-6.12-cip14) delta

`drivers/pinctrl/renesas/pinctrl-rzg2l.c` differs from v6.12.59 by 745 diff lines. Read hunk by hunk, it is upstream backports for other SoCs plus refactoring. For V2L (`r9a07g044_data`, `rzg2l_hwcfg`) **no register access changes at probe, at pinmux, at GPIO or at suspend/resume**:

- **G1 (rz-6.12-cip14) delta: OEN refactor, same register.** The per-SoC `oen_read`/`oen_write` hooks become one `rzg2l_read_oen`/`rzg2l_write_oen` pair driven by `pin_to_oen_bit` and a new `regs.oen` offset. For RZ/G2L-family `rzg2l_hwcfg`, `regs.oen = 0x3018`, the same register G0 hard-codes as `ETH_MODE` (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:1088-1133, 3228-3241, 3306-3317; v6.12.59 pinctrl-rzg2l.c:145, 1018-1049). The new `oen_pwpr_lock` flag (PWPR.REGWE_B around the OEN write) is set only for RZ/V2H (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:3278-3285), so on V2L the OEN write is still an unprotected 8-bit read-modify-write. Suspend/resume caches the same byte (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:3145, 3172-3181). Only error codes differ: reading `output-enable` on a pin whose bit is set now returns 0 instead of `-EINVAL`; there is no register effect.
- **G1 (rz-6.12-cip14) delta: NOD and SMT pinconf.** G1 adds `NOD(off) = 0x3000 + 8·off` and `SMT(off) = 0x3400 + 8·off` with `drive-open-drain`/`drive-push-pull`/`input-schmitt-enable` handling (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:144-145, 1374-1393, 1522-1536). Both are gated by `PIN_CFG_NOD`/`PIN_CFG_SMT`, which only the RZ/V2H-family tables carry; `RZG2L_MPXED_PIN_FUNCS` (used for every V2L port) has neither (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:75-76). **Unreachable on V2L.** On V2L, `0x3000 + 8·off` would land in SD_ch0 and beyond, so a model must not grow NOD/SMT registers for V2L on the strength of this code.
- **G1 (rz-6.12-cip14) delta: TINT index and parent fwspec.** The TINT base becomes `hwcfg->tint_start_index`, which is 9 for `rzg2l_hwcfg`, equal to G0's constant (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:2568, 3240; v6.12.59 pinctrl-rzg2l.c:171, 2384). The driver's own two-cell `populate_parent_alloc_arg` is replaced by the generic `gpiochip_populate_parent_fwspec_twocell` (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:2788), which builds the same two-cell fwspec for the IRQC. No register effect.
- **G1 (rz-6.12-cip14) delta: new SoC tables.** RZ/G3E (`r9a09g047`) and RZ/V2N (`r9a09g056`) data, pin names and variable-pin tables; the RZ/V2H dedicated-pin table is split to make PCIE1 optional (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:389-447, 1992-2057, 2218-2393, 3337-3379, 3418-3424). An `AUDIO_CLK1/2` entry is added at offset 0x2 in the **RZ/G3S** dedicated table (2182-2183); the RZ/G2L-family entry at offset 0x4 that the V2L hog uses is unchanged (2102-2103). None of these tables match `renesas,r9a07g044-pinctrl`.
- **Unchanged in G1 for V2L:** `set_pfc_mode` and the PWPR 0x00/0x40 … 0x00/0x80 sequence (rz_linux-cip 212f6e88b7 drivers/pinctrl/renesas/pinctrl-rzg2l.c:521-552, 3197-3210); the probe and its `-EPROBE_DEFER` on a missing IRQC domain (2900 onwards, 2753-2756); GPIO request/direction/get; the IEN hog path; the PUPD suspend quirk (conflict 6).

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target (`docs/sources.md`). Citations are `linux v6.18.55 <path>:N`. Probe, PWPR and set-mux register sequences are the same as in v6.12.59. The differences are:

- **All G1 deltas above are in v6.18** (OEN refactor, NOD/SMT, `tint_start_index`, generic fwspec, RZ/G3E and RZ/V2N tables) (drivers/pinctrl/renesas/pinctrl-rzg2l.c:3318, 3334 for `.oen = 0x3018`).
- **Pin validation in set-mux.** `rzg2l_validate_pin` now also runs before each pin in `set_mux` (drivers/pinctrl/renesas/pinctrl-rzg2l.c:525-540, 602). It reads no registers; a pin outside the port's pin map fails with `-EINVAL` instead of being written.
- **Locking.** The driver lock becomes a raw spinlock (drivers/pinctrl/renesas/pinctrl-rzg2l.c:2984). No register effect.
- **GPIO interrupt enable writes ISEL.** `irq_enable` sets the ISEL bit as well as allocation (drivers/pinctrl/renesas/pinctrl-rzg2l.c:2434-2495). Not on the console path.
- **Suspend/resume.** The PUPD high-word quirk is fixed (`PUPD(off) + 4`), SR is now saved and restored for ports and dedicated pins, and PMC restore goes through `pmc_writeb` (drivers/pinctrl/renesas/pinctrl-rzg2l.c:2999-3160, PUPD at 3053, SR at 3079, 3134, 3149).
- **IRQC** uses `devm_reset_control_get_exclusive_deasserted` (drivers/irqchip/irq-renesas-rzg2l.c:561), with the same effect on the CPG reset.
- **DT:** `adv7535` uses `interrupts-extended = <&pinctrl RZG2L_GPIO(2, 1) …>` (arch/arm64/boot/dts/renesas/rzg2l-smarc.dtsi:67); the pinctrl node and the SCIF pin groups are unchanged in content, with line numbers shifted (for example `scif0_pins` at rzg2l-smarc-pinfunction.dtsi:81-84, `sound_clk_pins` at 132-135).

## Claims to verify

1. The G0/G1 probe reads no register whose value affects success; the only blocking dependency is the IRQC domain. Evidence: pinctrl-rzg2l.c:2569-2636, 2638-2729, 2731-2777; G1 identical on this path (§10).
2. The probe-time IEN04 read-modify-write at 0x1820 comes from the pinctrl node's own `sound_clk` hog. Evidence: rzg2l-smarc-pinfunction.dtsi:11-13, 127-130; pinctrl-rzg2l.c:1968-1969, 1392-1397, 795-813.
3. The V2L TF-A build also muxes P47 and P19, not only P38. Evidence: TF-A pfc.c:44-63 with `-DRZG2L=1` in the compile log.
4. P38 function 1 = SCIF0 TXD/RXD. Evidence: DT rzg2l-smarc-pinfunction.dtsi:76-79; TF-A pfc.c:87-95; Module UM p.23 names the pins but not the function number. (Consistent with the EVK console working before Linux muxes anything, §5.3.)
5. gpiolib reads PMC/PM for all 392 lines at gpiochip registration. Evidence: drivers/gpio/gpiolib.c is not in the reviewed files.
6. ETH MII/RGMII resets to 0x03 and DTB-U's `output-enable` on ET0/ET1 TXC clears bits 0 and 1 when the Ethernet driver applies its pins. Evidence: HW manual Rev 1.50 §41.2.16, p.3384; §41.3.16, p.3416; pinctrl-rzg2l.c:997-1049; rzg2l-smarc-som.dtsi:181-185, 211-215.

## Questions for the EVK

1. **U-Boot (post-firmware):** `md.b 0x11030236 1; md.l 0x110304d8 1; md.w 0x1103016c 1; md.b 0x11033014 1`. Expect 0x03, 0x00000011, 0x0000, 0x80. Also `md.b 0x1103023f 1; md.l 0x110304fc 1; md.b 0x11030223 1; md.l 0x1103048c 1` for the P47/P19 claim.
2. **U-Boot:** `md.l 0x11031820 1` (IEN04). Expect 0 before Linux; post-Linux (G1 `/dev/mem`) expect 0x00000101.
3. **U-Boot:** read `0x11033000` (SD_ch0), `0x11033004` and `0x11033008` (QSPI) to anchor the overlay, and `md.b 0x11033018 1` (ETH MII/RGMII; expect 0x03 if the firmware leaves it alone).
4. **U-Boot:** read one undefined offset (for example `md.l 0x11033100 1`): zero, abort, or something else.
5. **Post-Linux (G1 debug image):** `cat /sys/kernel/debug/pinctrl/11030000.pinctrl-pinctrl-rzg2l/pinmux-pins | grep -E 'P38|P48'`, the boot log order of `pinctrl-rzg2l` vs `rzg2l-irqc` vs `sh-sci` (the 2026-10-08 capture records the ttySC0 probe at 0.594 s but not the pinctrl and IRQC lines), and whether that image's `scif0` node has `pinctrl-0` (`/proc/device-tree/soc/serial@1004b800/pinctrl-0`). Record it as post-Linux.

## Verification (main session, 2026-10-08)

| Claim | Result | Evidence |
|---|---|---|
| "sh-sci eventually probes without pinctrl after the deferred-probe timeout" | **Refuted for the G0 kernel.** The spec's "defers forever" holds. | linux v6.12.59 `drivers/pinctrl/devicetree.c:123-136`: when no registered pin controller is found up the tree, the result is `-ENODEV`, which is turned into `-EPROBE_DEFER` whenever `CONFIG_MODULES` is enabled and the node lacks `pinctrl-use-default`. That path does not consult `driver_deferred_probe_check_state()`, so the deferred-probe timeout in `drivers/base/dd.c:288-301` does not rescue it. arm64 `defconfig:120` sets `CONFIG_MODULES=y`. Same file in G1. **The PFC model must therefore let `rzg2l-pinctrl` probe.** |
| `PINCTRL_RZG2L` built in | **Confirmed (select)** | linux v6.12.59 `drivers/pinctrl/renesas/Kconfig:42` selects it for `ARCH_RZG2L`; it is a hidden bool (`Kconfig:192-193`); `PINCTRL_RENESAS` defaults to y under `ARCH_RENESAS` (`Kconfig:8-10`; `defconfig:64`) |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done (2026-10-08)** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7` (§10: no V2L register-level change). Additions against the first draft: the ETH MII/RGMII register at 0x3018 (§2), the PUPD suspend quirk (conflict 6), the IRQC probe details for v6.12.59 (§6). v6.18.55 differences kept under "Newer mainline". EVK boot-log evidence folded into §5.3 and §6 (indirect only: the log has no pinctrl lines). |

## EVK results (2026-10-29, U-Boot prompt, downstream firmware; `../evidence/EVK-2026-10-29-post-firmware.md`)

- **OBSERVED.** Q1: P38 (SCIF0), P47/P19 (SD), PWPR `0x80`, IEN04 0 and P48 match. Q3: SD_ch0 `0x01`, SD_ch1 `0x00`, QSPI `0x00` (EVK-R30-R33, R35, R36).
- **OBSERVED, differs from the reset value.** ETH MII/RGMII (`0x3018`) reads `0x00` against the reset value `0x03` (EVK-R34). INFERENCE: this firmware writes it. That is a direct-mode value for M3b.
- **OBSERVED.** Q4: the undefined offset `0x11033100` reads 0, no bus error (EVK-R71).
