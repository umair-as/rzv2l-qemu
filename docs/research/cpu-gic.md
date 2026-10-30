# CPU, GIC-600, generic timer and PSCI: what the RZ/V2L machine must provide

Based on the pinned guest kernels (`docs/sources.md` "Pinned guest kernels"). **Status:** M0 research note.

**Scope:** Cortex-A55 cluster, GIC-600, the architected timer, OSTM, PSCI, and direct-kernel boot under QEMU, for the G0 guest (linux v6.12.59 `arm64 defconfig` Image plus the upstream `r9a07g054l2-smarc.dtb`). It ends with a proposed M1 SoC skeleton.

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference), qemu v11.1.2 (the `qemu/` submodule, read-only), the RZ/V2L HW manual Rev 1.50, `docs/research/boot-chain-firmware.md`, EXP-001, and the passive EVK boot log `docs/evidence/EVK-2026-10-08-boot-log.md`. The first draft of this note was written against linux v6.18.55; where that kernel differs, the difference is kept in "Newer mainline (v6.18.55)" near the end.

**Labels:** **FACT** means read directly from source, DT or the manual. **INFERENCE** means derived from code paths I traced but did not run. **ASSUMPTION** means not yet backed by evidence. **OBSERVED** means seen on the EVK (boot log above; post-Linux unless stated otherwise).

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N` with these paths:

| Short | Full path |
|---|---|
| `r9a07g054.dtsi`, `r9a07g054l2-smarc.dts`, `rzg2l-smarc-som.dtsi`, `rz-smarc-common.dtsi`, `rzg2l-smarc.dtsi` | `arch/arm64/boot/dts/renesas/` |
| `irq-gic-v3.c`, `irq-renesas-rzg2l.c` | `drivers/irqchip/` |
| `arm_arch_timer.c`, `renesas-ostm.c`, `timer-probe.c` | `drivers/clocksource/` |
| `psci.c` | `drivers/firmware/psci/` |
| `rzg2l-cpg.c`, `r9a07g044-cpg.c` | `drivers/clk/renesas/` |
| `sched_clock.c` | `kernel/time/` |
| `booting.rst` | `Documentation/arch/arm64/` |
| `defconfig` | `arch/arm64/configs/` |

G1 citations are written out as `rz_linux-cip 212f6e88b7 <path>:N`. QEMU citations are `qemu v11.1.2 <path>:N`.

The DT for the board is assembled from `r9a07g054l2-smarc.dts`. It includes `r9a07g054l2.dtsi` (which includes `r9a07g054.dtsi`), `rzg2l-smarc-som.dtsi`, `rzg2l-smarc-pinfunction.dtsi`, `rz-smarc-common.dtsi` and `rzg2l-smarc.dtsi` (r9a07g054l2-smarc.dts:29-33). Every DT statement below was checked against a cpp+dtc flattening of that tree, for G0 and for G1.

**G1 (rz-6.12-cip14) delta, DT as a whole:** `r9a07g054.dtsi`, `r9a07g054l2.dtsi`, `rzg2l-smarc-pinfunction.dtsi`, `rz-smarc-common.dtsi`, `rzg2l-smarc.dtsi` and `r9a07g054l2-smarc.dts` are byte-identical to G0. The only difference is the QSPI flash partition table in `rzg2l-smarc-som.dtsi` (G0: `boot@0` read-only 32 MiB + `user`; G1: `bl2` / `fip` / `user`, rz_linux-cip 212f6e88b7 arch/arm64/boot/dts/renesas/rzg2l-smarc-som.dtsi:342-353). The flattened G0 and G1 DTs differ only in those lines. Nothing in this note depends on them. The EVK boot log comes from a downstream image whose DT is not G1's; its DT-level facts are not transferred here.

---

## 1. CPU nodes

| Item | Value | Evidence | Label |
|---|---|---|---|
| CPUs | `cpu@0` `reg = <0>`, `cpu@100` `reg = <0x100>`, both `arm,cortex-a55` | r9a07g054.dtsi:87-106 | FACT |
| MPIDR the guest expects | Aff1 = core number: 0x0 and 0x100 (Linux matches MPIDR against `reg`) | same; EVK log `CPU1: Booted secondary processor 0x0000000100` | FACT, OBSERVED |
| enable-method | `"psci"` on both | r9a07g054.dtsi:93,103 | FACT |
| cpu-map | one cluster, core0 and core1 | r9a07g054.dtsi:76-85 | FACT |
| clocks | `<&cpg CPG_CORE R9A07G054_CLK_I>`; CLK_I = PLL1 / DIVPL1A | r9a07g054.dtsi:94,104; r9a07g044-cpg.c:167 | FACT |
| OPP table | `opp-shared`; 150, 300, 600 and 1200 MHz, all 1.1 V; 1200 MHz is `opp-suspend` | r9a07g054.dtsi:45-70 | FACT |
| cpu-supply | none, so cpufreq-dt runs without a regulator | r9a07g054.dtsi:87-106 | FACT |
| `#cooling-cells` | `cpu@0` only; the thermal zone maps TSU to `cpu0` | r9a07g054.dtsi:91,1313-1342 (cooling map at :1323) | FACT |
| idle states | **none**: no `cpu-idle-states`, no `idle-states` node, no PSCI `power-domains` | grep of the flattened DT (G0 and G1) | FACT |
| Silicon core | Cortex-A55 **r2p0**, 1.2 GHz | HW manual Rev 1.50 §2.1, Table 2.1, p.83 | FACT |
| MIDR on silicon | `0x412FD050` on both CPUs (Cortex-A55 r2p0) | EVK log `Booting Linux on physical CPU 0x0000000000 [0x412fd050]` | OBSERVED |

**cpufreq.** `cpufreq-dt-platdev` (core_initcall) creates a `cpufreq-dt` device when the root compatible is on its allowlist, or when `cpu0` has `operating-points-v2` and the root is not on its blocklist (linux v6.12.59 drivers/cpufreq/cpufreq-dt-platdev.c:212-237). RZ/V2L is on neither list (allowlist :52-67 has only 32-bit Renesas parts; blocklist :105-199), and `CONFIG_CPUFREQ_DT=y` (defconfig:96). **FACT:** cpufreq-dt changes CLK_I through a plain generic divider: `DEF_DIV("I", …, DIVPL1A, dtable_1_8)` (linux v6.12.59 drivers/clk/renesas/r9a07g044-cpg.c:167), registered with `clk_hw_register_divider_table` (rzg2l-cpg.c:403-430). That is a single write to the PL1 divider field with **no busy poll**. The `rzg2l_cpg_wait_clk_update_done` poll (rzg2l-cpg.c:169-175) is used only by the SD clock mux (`:211`, `:478`) and the RZ/G3S dividers (`:257`, `:331`). This matches cpg-reset.md.

G1 (rz-6.12-cip14) delta: none. Same DT; `CONFIG_CPUFREQ_DT=y` (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:52).

### Cache node

- **FACT:** the DT has one `cache-controller-0`: `cache-unified`, `cache-level = 3`, `cache-size = 0x40000` (256 KiB). It is the `next-level-cache` of both CPUs (r9a07g054.dtsi:92,102,108-113).
- **FACT:** the manual gives L1 I/D of 32 KiB each, **L2 = none**, and an L3 of 256 KiB (ECC) shared by both cores (HW manual Rev 1.50 §1.2.1, p.71; §2.1, Tables 2.1/2.2, p.83).
- **FACT:** QEMU's `cortex-a55` reports CLIDR = 0x82000023 (L1 I+D, unified L2, no L3). Its CCSIDR describes a **512 KiB L2** (qemu v11.1.2 target/arm/tcg/cpu64.c:220,254-259).
- **INFERENCE:** guest-visible cache topology differs. Linux arm64 cacheinfo merges CLIDR levels with the DT's highest `cache-level`. It would report L1, an L2 of 512 KiB that does not exist, and the DT L3. This is a fidelity gap for `/sys/devices/system/cpu/cpu*/cache`; it does not block boot. Fixing it needs the SoC to override `CLIDR`/`CCSIDR` after CPU object init and before realize. QEMU has no property for this, so the override would be board-local code.
- **Open:** how silicon CLIDR encodes "no L2, DSU L3" (EVK question Q2).

### Other CPU properties

- **FACT:** QEMU's MIDR is 0x412FD050 (r2p0, qemu v11.1.2 target/arm/tcg/cpu64.c:248). It matches the manual and the value **OBSERVED** on both EVK CPUs.
- **FACT:** QEMU's ID_AA64ISAR0 advertises AES/PMULL/SHA1/SHA2 (cpu64.c:224). The manual lists the crypto extension as "Included (option)" (§2.1, Table 2.2, p.83).
- **ASSUMPTION:** the EVK part has the crypto extension. See Q2.
- REQ-MACH-005 IMPDEF sysregs (CPUPWRCTLR_EL1 etc.) are covered by EXP-001 and not repeated here.

---

## 2. GIC-600 from the DT and the manual

| Item | Value | Evidence | Label |
|---|---|---|---|
| compatible | `arm,gic-v3`, `#interrupt-cells = <3>` | r9a07g054.dtsi:1049-1053 | FACT |
| GICD | `0x11900000`, size `0x20000` | r9a07g054.dtsi:1054 | FACT |
| GICR | `0x11940000`, size `0x40000` (= 2 × 0x20000: two GICv3 redistributors of 2 × 64 KiB each) | r9a07g054.dtsi:1055 | FACT |
| Redistributors on silicon | CPU0 → `0x11940000`, CPU1 (MPIDR 0x100) → `0x11960000`, both in region 0: stride 0x20000 | EVK log `CPU0: found redistributor 0 region 0:0x0000000011940000`, `CPU1: found redistributor 100 region 0:0x0000000011960000` (printed by irq-gic-v3.c:1096-1099) | OBSERVED |
| `#redistributor-regions` | absent, so Linux uses 1 region | r9a07g054.dtsi:1049-1057; irq-gic-v3.c:2331-2332 | FACT |
| `redistributor-stride` | absent (stride from GICR_TYPER/PIDR2) | irq-gic-v3.c:2351-2352 | FACT |
| GICC/GICH/GICV regs | absent (no GICv2-compat or virtualization frames) | r9a07g054.dtsi:1054-1055 | FACT |
| ITS | **no ITS node**; the manual says "LPI: Not supported" | DT; HW manual Rev 1.50 §8.1, p.530 | FACT |
| `interrupts` of the GIC | `<GIC_PPI 9 IRQ_TYPE_LEVEL_LOW>`: the vGIC maintenance interrupt (INTID 25) | r9a07g054.dtsi:1056; HW manual Rev 1.50 §8.2, Table 8.2, p.534 (nVCPUMNTIRQ = PPI 9) | FACT |
| SPIs | 480 SPIs → `num-irq` = 512 | HW manual Rev 1.50 §8.1, p.530; EVK log `GICv3: 480 SPIs implemented` (irq-gic-v3.c:2088) | FACT, OBSERVED |
| PPIs | 16 | HW manual Rev 1.50 §8.1, p.530; EVK log `16 PPIs` | FACT, OBSERVED |
| Priority | 32 levels (5 priority bits); QEMU A55 has `gic_pribits = 5` | §8.1 p.530; qemu v11.1.2 target/arm/tcg/cpu64.c:265 | FACT |
| Security state on silicon | `GICD_CTRL.DS=0, SCR_EL3.FIQ=1` (security extensions on; TF-A routes FIQ to EL3) | EVK log; string printed by irq-gic-v3.c:226-228 | OBSERVED |
| GIC address area | 1 MiB `0x1190_0000`–`0x119F_FFFF` | HW manual Rev 1.50 §5.2.1, Table 5.1 (1/3), p.143 | FACT |
| IP revision | GIC-600 r1p6 (the manual defers to the Arm TRM for registers) | HW manual Rev 1.50 §8.1 p.530, §8.3–8.4 p.548 | FACT |
| CPG clock/reset | GIC600 GICCLK (CLK_ON 0x514 b0) is a **critical** module clock; resets are defined at CPG 0x814 bits 0/1 but the GIC node has no `resets` | r9a07g044-cpg.c:206-207,372-373,435-439; r9a07g054.dtsi:1049-1057 | FACT |

The other PPIs in the DT match the manual and QEMU's BSA numbering:

- PMU: PPI 7 = INTID 23 (r9a07g054.dtsi:160-163).
- Timer:
  - `sec-phys` PPI 13 = INTID 29
  - `phys` PPI 14 = INTID 30
  - `virt` PPI 11 = INTID 27
  - `hyp-phys` PPI 10 = INTID 26
  - `hyp-virt` PPI 12 = INTID 28

  All are `IRQ_TYPE_LEVEL_LOW` (r9a07g054.dtsi:1344-1353; HW manual Rev 1.50 §8.2, Table 8.2, p.534; qemu v11.1.2 include/hw/arm/bsa.h:25-33).

**FACT:** the QEMU INTID constants (`VIRTUAL_PMU_IRQ` 23, `ARCH_GIC_MAINT_IRQ` 25, timers 26–30) coincide exactly with the RZ/V2L map. The i.MX8MP wiring idiom can therefore be reused verbatim (qemu v11.1.2 hw/arm/fsl-imx8mp.c:351-371).

G1 (rz-6.12-cip14) delta: none. `irq-gic-v3.c` is identical (rz_linux-cip 212f6e88b7 drivers/irqchip/irq-gic-v3.c), and so is the GIC node.

### 2.1 What Linux reads versus what QEMU's arm_gicv3 offers

| Guest access | Linux use | QEMU arm_gicv3 | Match? |
|---|---|---|---|
| GICD_PIDR2 / GICR_PIDR2 ArchRev | must be 3 or 4, else "no distributor" or no redistributor (irq-gic-v3.c:2154-2159,2325-2328,1043-1047) | 0x3B with revision 3 (qemu v11.1.2 hw/intc/gicv3_internal.h:765-787) | yes (FACT) |
| GICD_IIDR | quirk table match (irq-gic-v3.c:1954-2028); no GIC-600 entry exists, and HIP06 0x0204043B is noted to clash with GIC-600 (irq-gic-v3.c:1866-1870) | fixed **0x0000043B** (gicv3_internal.h:749-758); `(0x43B & 0xff000fff)` matches the RK3399 entry (irq-gic-v3.c:2020-2025), but its init returns false unless the root is `rockchip,rk3399` (irq-gic-v3.c:1934-1944) | **no**: silicon has a GIC-600 ProductID (ASSUMPTION 0x0201643B for r1p6). Boot-harmless (INFERENCE), but it fails the M1 "GIC ID registers equal EVK values" check |
| GICD_TYPER | IDbits, ITLines, LPIS, ESPI, RSS; `%d SPIs implemented` (irq-gic-v3.c:2088-2089) | No1N, A3V, IDbits = 0xF, LPIS = `has-lpi`, SecurityExtn = !DS, ITLines from num-irq (qemu v11.1.2 hw/intc/arm_gicv3_dist.c:403-430) | ITLines: yes with `num-irq=512` (silicon prints 480 SPIs, OBSERVED); the other fields' silicon values are unknown (Q1) |
| GICR_TYPER | Aff value matched to MPIDR; Last; PLPIS/VLPIS (irq-gic-v3.c:1033-1100) | Aff taken from each CPU's `mp-affinity` **at GIC realize**; Last on the final redistributor (qemu v11.1.2 hw/intc/arm_gicv3_common.c:450-489) | yes, provided mp-affinity is set before the GIC is realized (FACT); silicon frame addresses OBSERVED (table above) |
| GICR_WAKER | Linux clears ProcessorSleep and polls ChildrenAsleep, 1 s timeout (irq-gic-v3.c:367-399, poll at :393-394) | resets to Sleep\|ChildrenAsleep; writes complete instantly (qemu v11.1.2 hw/intc/arm_gicv3_redist.c:509-526, arm_gicv3_common.c:510) | yes (FACT) |
| GICD/GICR_CTLR.RWP | polled, 1 s timeout (irq-gic-v3.c:344-365) | never set (synchronous) | yes |
| GICD_CTLR.DS, PMR group-0 probe | selects the priority scheme and prints `GICD_CTRL.DS=%d, SCR_EL3.FIQ=%d` (irq-gic-v3.c:165-229, print at :226-228; FIQ is reported as "group-0 priorities not visible", :169, :228) | DS = 1 if `has-security-extensions=false`; else DS = 0 with `irq_reset_nonsecure` making all IRQs Group 1 NS for a direct boot (arm_gicv3_common.c:546-551,574-602) | silicon: DS=0, FIQ=1 (OBSERVED). QEMU can give DS=0 but not FIQ=1 in direct mode; see §6 D2 |
| LPIs | `gic_dist_supports_lpis()` = ITS config && GICD_TYPER.LPIS && !nolpi (irq-gic-v3.c:1316-1321) | `has-lpi` default false (arm_gicv3_common.c:608) | yes with the default (manual: LPI not supported) |
| ICC_SRE_ELx | Linux requires SRE = 1 | constant SRE = 1 (qemu v11.1.2 hw/intc/arm_gicv3_cpuif.c:2599-2656) | yes; satisfies booting.rst:222-235 |
| Reserved GICR offsets (e.g. GIC-600 GICR_PWRR @ 0x24) | Linux: never. TF-A GIC-600 driver: yes (Stage B) | RAZ/WI with a guest-error log (arm_gicv3_redist.c:750-762) | **INFERENCE:** RAZ likely satisfies TF-A's power-on wait. Verify in M7 |
| GICD region size | Linux maps 0x20000 (irq-gic-v3.c:2317-2321) | QEMU GICD MR is 0x10000 (arm_gicv3_common.c:350-351); the upper 64 KiB of the DT window is unbacked | INFERENCE: Linux never touches it; the M1 machine should cover it with an unimplemented region so a stray access logs rather than aborts |
| Redistributor stride | 0x20000 (GICv3) | `GICV3_REDIST_SIZE` 0x20000 for revision 3 (qemu v11.1.2 include/hw/intc/arm_gicv3_common.h:46) | yes (FACT; silicon stride 0x20000 OBSERVED) |

**WakeRequest / cpuidle caveat.**

- Other SoC ports reportedly had to care about vendor wake logic (GPC-style) driving GICR_WAKER and wake requests when CPUs enter PSCI power-down states (ASSUMPTION; not verified here).
- For this DT the caveat does not bite:
  1. **FACT:** no idle states exist (§1), so `cpuidle-psci` (`CONFIG_ARM_PSCI_CPUIDLE=y`, defconfig:89) has no states. Idle is plain WFI.
  2. **FACT:** QEMU implements PSCI CPU_SUSPEND as WFI ("Powerdown is not supported", qemu v11.1.2 target/arm/tcg/psci.c:160-176).
  3. **FACT:** GICR_WAKER handshakes are instantaneous.
- G1 (rz-6.12-cip14) delta: none. The G1 DT also has no idle states (flattened-DT grep), so the earlier "re-check if the vendor DTB adds `idle-states`" is answered for G1. `CONFIG_ARM_PSCI_CPUIDLE=y` in G1 too (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:41). Re-check only for a downstream DT.

---

## 3. Architected timer and OSTM

**Arch timer node** (r9a07g054.dtsi:1344-1353).

- **FACT:** `arm,armv8-timer`, five PPIs via `interrupts-extended` (above), all level-low.
- **FACT:** no `clock-frequency`, no `always-on`, no `arm,no-tick-in-suspend`.
- **FACT:** the rate comes from `arch_timer_get_cntfrq()` unless the DT gives `clock-frequency` (arm_arch_timer.c:1446-1447,1064-1076). CNTFRQ_EL0 must therefore hold 24 MHz at entry; booting.rst:192 requires firmware to program it.
- **OBSERVED:** `arch_timer: cp15 timer(s) running at 24.00MHz (virt).` (format at arm_arch_timer.c:1078-1094). So CNTFRQ = 24 MHz and Linux uses the virtual timer on silicon.
- **FACT:** QEMU's A55 default is 62.5 MHz because of `BACKCOMPAT_CNTFRQ`. The `cntfrq` property sets both CNTFRQ_EL0 and the real tick rate (EXP-001 conclusion 10).
- **FACT:** `always-on` is absent, so `arch_timer_c3stop = true` and the clockevent carries `CLOCK_EVT_FEAT_C3STOP` (arm_arch_timer.c:1449,865). This is harmless without deep idle.
- **FACT:** at EL1 with no EL2 available, Linux picks the **virtual** timer, PPI 11 / INTID 27 (arm_arch_timer.c:1399-1406). QEMU must wire `GTIMER_VIRT` → INTID 27. The rating is 450 for the clockevent and 400 for the clocksource (arm_arch_timer.c:868,254).
- **FACT:** level-low PPIs are accepted. Only edge/invalid triggers would print "Invalid trigger" (arm_arch_timer.c:1014-1025).
- **FACT:** the arch counter also registers `sched_clock` at 24 MHz (arm_arch_timer.c:1123-1173, register at :1172).

**OSTM (GTM) nodes.**

- **FACT:** `ostm0/1/2` @ 0x12801000/1400/1800, SPI 46/47/48 edge, CPG clock and reset each (r9a07g054.dtsi:1279-1310; HW manual Rev 1.50 §5.2.1, Table 5.1 (1/3), p.143; §20.1.1, Table 20.2, p.1224; §8.2 p.536).
- **FACT:** the SoM enables **ostm1 and ostm2**; ostm0 stays disabled (rzg2l-smarc-som.dtsi:167-173). `CONFIG_RENESAS_OSTM=y` (defconfig:1372).
- **FACT:** `ostm_init()` first gets its CPG reset (renesas-ostm.c:172-176). At `time_init` (`TIMER_OF_DECLARE`, :226) no reset controller is registered yet, so the reset core returns `-EPROBE_DEFER` (linux v6.12.59 drivers/reset/core.c:1045-1049) and `timer_probe` skips the node silently (timer-probe.c:30-35). No OSTM register is touched on that path. The node is retried through `builtin_platform_driver_probe` at device_initcall (renesas-ostm.c:228-249), after the CPG has bound at subsys_initcall.
- **FACT:** `builtin_platform_driver_probe` uses `__platform_driver_probe`, which forbids deferral (`prevent_deferred_probe`, linux v6.12.59 drivers/base/platform.c:913-942, :1410-1411). The OSTM probe is therefore **one-shot**: if the CPG clock or reset fails at that moment, OSTM is lost for the whole boot.
- **FACT:** the first OSTM probed becomes a clocksource (rating 300, so it loses to the arch timer) **and calls `sched_clock_register(..., 32, rate)`** (renesas-ostm.c:198-204, 61-83). The second becomes a clockevent (rating 300, unused while the arch timer is present) (:205-211).
- **FACT:** `sched_clock_register` replaces the current sched_clock unless the new rate is lower (sched_clock.c:164-172).
- **FACT:** OSTM uses P0 = PLL2/16/DIVPL2A (r9a07g044-cpg.c:168, module clocks at :216-221, CLK_ON 0x534 b0-2; OSTM1 reset at 0x834 b1, :378).
- **OBSERVED (answers former claim 3 and Q4 in part):** `clocksource: timer@12801400 …`, `sched_clock: 32 bits at 100MHz, resolution 10ns`, `/soc/timer@12801400: used for clocksource`, `/soc/timer@12801800: used for clock events`. So P0 = 100 MHz and **OSTM1 takes over `sched_clock` on silicon**. The image is downstream, but `renesas-ostm.c` is identical in G0 and G1 and the OSTM nodes are SoC-level.
- **Consequence (INFERENCE):** OSTM is **not optional** for an honest M3b. An unmapped OSTM aborts the device_initcall probe (a panic before the console). An unimplemented, read-as-zero OSTM probes, but its counter freezes `sched_clock`, and with it printk timestamps and CFS accounting. That is a silent-wrong outcome.
- **Also:** `ostm_timer_stop()` spins on `OSTM_TE` **without a timeout** (renesas-ostm.c:46-59). The manual says TE is cleared by a write of 1 to TT (HW manual Rev 1.50 §20.2.2.3, p.1229; §20.2.2.5, p.1230). A model that never clears TE after a TT write would hang.
- Owner: `boot-dependency-graph.md` / M3b.

G1 (rz-6.12-cip14) delta: none. `arm_arch_timer.c` and `renesas-ostm.c` are identical (rz_linux-cip 212f6e88b7 drivers/clocksource/), as are the timer and OSTM nodes. `CONFIG_RENESAS_OSTM=y` (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:346).

---

## 4. PSCI and how Linux uses it

- **FACT:** the DT node is `compatible = "arm,psci-1.0", "arm,psci-0.2"`, `method = "smc"` (r9a07g054.dtsi:165-168).
- **FACT:** QEMU **replaces** any `/psci` node. It NOPs the guest node and writes its own with `"arm,psci-1.0", "arm,psci-0.2", "arm,psci"`, the method, and the `cpu_suspend`/`cpu_off`/`cpu_on`/`migrate` IDs (qemu v11.1.2 hw/arm/boot.c:366-442). This is a live-DT difference and must go on the gap list (§8 loader-fixup contract). Linux takes the `psci-1.0` path either way (psci.c:728-749, entry `psci_dt_init` at :753).
- **OBSERVED:** `psci: PSCIv1.1 detected in firmware.` and `SMC Calling Convention v1.4` (TF-A BL31 v2.10.5).

Linux probe sequence (psci.c:636-662) and QEMU's answers (qemu v11.1.2 target/arm/tcg/psci.c):

| Call | When | QEMU answer | Notes |
|---|---|---|---|
| PSCI_VERSION | `psci_dt_init`, setup_arch | 1.1 (psci.c:95-96) | silicon also reports 1.1 (OBSERVED). Match |
| MIGRATE_INFO_TYPE | `psci_init_migrate` (psci.c:553-587) | 2 = "TOS not present / migration not required" (psci.c:98-99); Linux prints `Trusted OS migration not required` (psci.c:560-562) | **gap (ASSUMPTION):** with OP-TEE (opteed), TF-A may report a resident TOS. Linux then refuses to offline the TOS CPU. The 2026-10-08 log excerpt does not include this line (Q5) |
| PSCI_FEATURES(SMCCC_VERSION) | `psci_init_smccc` (psci.c:589-612) | NOT_SUPPORTED (not in the list, psci.c:177-205) | Linux falls back to SMCCC v1.0, prints `SMC Calling Convention v1.0` and issues no ARCH_WORKAROUND calls. Silicon prints **v1.4** (OBSERVED), so this is a confirmed guest-visible gap; `/sys/.../vulnerabilities` may differ too (informational) |
| PSCI_FEATURES(CPU_SUSPEND) | `psci_init_cpu_suspend` | 0 (original power_state format) | used only by cpuidle; no states (§2) |
| PSCI_FEATURES(SYSTEM_SUSPEND), SYSTEM_RESET2 | probe (psci.c:655-657) | NOT_SUPPORTED | suspend-to-RAM not offered; matches the "no deep idle" scope. v6.12.59 does not probe SYSTEM_OFF2 (see "Newer mainline") |
| CPU_ON(0x100, entry) | `smp_init` | `arm_set_cpu_on` by MPIDR; enters at EL1 with no EL2 (EXP-001) | needs mp-affinity 0x100 on cpu1; silicon brings CPU1 up (OBSERVED) |
| SYSTEM_RESET | `reboot` (restart notifier, priority 129, psci.c:326-329) | `qemu_system_reset_request` (psci.c:122-) | outranks the WDT restart handler (default priority 128) on both silicon and QEMU, so the WDT path is not exercised (INFERENCE) |
| SYSTEM_OFF | `poweroff` | shutdown request | silicon: BL31 behaviour unmeasured |
| Any other SMC (OP-TEE, SiP) | optee probe | −1 NOT_SUPPORTED, no exception | EXP-001 conclusion 1 |

**FACT:** no idle states and no `power-domains` on the CPUs mean PSCI CPU_SUSPEND is never issued at boot. QEMU only needs to handle CPU_ON, SYSTEM_RESET and SYSTEM_OFF, which it does.

G1 (rz-6.12-cip14) delta: none. `psci.c` is identical (rz_linux-cip 212f6e88b7 drivers/firmware/psci/psci.c).

---

## 5. Direct-kernel boot under QEMU

Entry state (EXP-001 plus the trace below):

- **EL1 entry.** Create the CPUs with `has_el2=false`. Linux images boot at EL2 if the CPU has EL2, else EL1 (qemu v11.1.2 hw/arm/boot.c:1238-1249). This matches the board: FACT (boot-chain-firmware.md §1) and OBSERVED (`CPU: All CPU(s) started at EL1`).
- **Conduit.** Set `psci_conduit = QEMU_PSCI_CONDUIT_SMC`. boot.c keeps it unless boot_el == 3 (boot.c:1251-1254). It then sets `psci-conduit` on every CPU and **`start-powered-off` on every secondary** (boot.c:1256-1267). FACT.
- **mp-affinity.** Set 0x0 and 0x100 before realize. A custom machine is not overwritten the way `virt` is (EXP-001 conclusion 11). The GIC must be realized **after** the CPUs so GICR_TYPER picks this up (arm_gicv3_common.c:461-471). FACT.
- **cntfrq.** Set 24000000 on both CPUs (EXP-001 conclusion 10). FACT; the 24 MHz board value is OBSERVED.
- **start-powered-off.** Set on cpu1 explicitly in the SoC as well, following the i.MX8MP precedent (qemu v11.1.2 hw/arm/fsl-imx8mp.c:306-313). Stage B (real BL31, PSCI disabled) also needs cpu1 held off until CPU_ON via RVAL plus the CPG handshake. boot.c only does this when QEMU PSCI is active. INFERENCE.
- **reset-cbar.** The i.MX8MP precedent sets it to the GICD base (fsl-imx8mp.c:283-287). **INFERENCE:** neither Linux nor the RZ TF-A reads CBAR for GICv3, so the property is optional. Leave it at default unless evidence appears. Recording it as "not modelled" is honest.
- **GIC secure state for direct mode.** See §6, decision D2.
- **booting.rst requirements met by QEMU.** x0 = DTB in RAM (booting.rst:162; QEMU's bootloader stub, qemu v11.1.2 hw/arm/boot.c:70-77). DTB 8-byte aligned and ≤ 2 MiB (booting.rst:50-52). CNTFRQ programmed (booting.rst:192). ICC_SRE (booting.rst:222-235). FACT.

### 5.1 Memory placement and collisions

- **FACT:** the DT memory node is `memory@48000000`, `reg = <0x0 0x48000000 0x0 0x78000000>`, with the comment "first 128MB is reserved for secure area" (rzg2l-smarc-som.dtsi:32-36).
- **FACT:** the board DT has **no `/reserved-memory` node** (flattened-DT grep, G0 and G1).
- **FACT:** the manual places DDR from `0x0_4000_0000` (HW manual Rev 1.50 §5.2.1, Table 5.1 (1/3), p.143).
- **FACT:** `/chosen` = `bootargs = "ignore_loglevel rw root=/dev/nfs ip=on"` (rzg2l-smarc-som.dtsi:28-30) plus `stdout-path = "serial0:115200n8"` (rz-smarc-common.dtsi:31-33). No `kaslr-seed`, no `rng-seed`, no `linux,initrd-*` (flattened DT).

QEMU behaviour (qemu v11.1.2 hw/arm/boot.c):

- **`/memory`.** Every `/memory*` node is NOP'd and one `/memory@<loader_start>` is written with `binfo->ram_size` (boot.c:530-579). The machine must therefore set `loader_start = 0x48000000` and `binfo.ram_size = 0x78000000` while mapping 2 GiB of RAM at 0x40000000. The result is node-for-node identical to the DT and to U-Boot's rewrite. FACT for the mechanism; the values are a proposal.
- **Bootloader stub.** Written at `loader_start` = 0x48000000, at most 4 KiB (boot.c:1094, `BOOTLOADER_MAX_SIZE`).
- **Kernel.** Modern Images have text_offset 0, so the Image loads at **loader_start + 2 MiB = 0x48200000** (boot.c:845-875). This happens to equal U-Boot's FIT load address in boot-chain-firmware.md §1.
- **initrd.** At `loader_start + min(ram_size/2, 128 MiB)` = **0x50000000**, raised above the kernel end if necessary and page-aligned (boot.c:1000-1005).
- **DTB.** After the initrd, aligned to 2 MiB (boot.c:1051-1078).
- **`/chosen`.** `bootargs` is replaced **only if `-append` is non-empty** (boot.c:603-609). `linux,initrd-start/end` are added (boot.c:612-627). `rng-seed` is only re-randomized if present, and the DT has none (qemu v11.1.2 system/device_tree.c:661-679).

**Collision check (INFERENCE):**

- Every QEMU placement lies inside `[0x48000000, 0xC0000000)`.
- Nothing lands in 0x40000000–0x47FFFFFF, the secure area that Stage B uses for BL31/OP-TEE.
- With no reserved-memory node, nothing conflicts.
- The stub page at 0x48000000 is ordinary RAM to Linux, as on `virt`.
- On the board, U-Boot itself lives at 0x50000000 and the kernel DTB sits just below 0x58000000 (boot-chain-firmware.md §1). Direct mode places things differently, but Linux does not depend on those addresses.
- The kernel's CMA area (G0 defconfig `CONFIG_CMA_SIZE_MBYTES=32`, defconfig:1710) is carved from free memblock after the kernel, initrd and DTB are reserved, so it cannot overlap them.

G1 (rz-6.12-cip14) delta:

- **No reserved memory and no DRP-AI nodes.** G1's `r9a07g054.dtsi` is identical to G0's, and the board includes differ only in QSPI partitions (top of this note). G1 adds no `reserved-memory`, no DRP-AI/M33 carve-out and no OP-TEE node to this board's DT. The collision check above therefore holds for G1 unchanged. FACT.
- **CMA 128 MiB** instead of 32 MiB (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:411-413). This is still a dynamic memblock allocation inside `/memory`, not a DT carve-out. No collision (INFERENCE).
- **Watch item, moved:** a DRP-AI or OP-TEE `reserved-memory` node can only come from a downstream DT, such as the EVK image's. Re-run this check for any downstream DTB; it is not needed for G0 or G1.

---

## 6. Decisions proposed for M1

- **D1. GIC model.** Use `gicv3_class_name()` with `revision=3`, `num-cpu=2`, `num-irq=512`, `redist-region-count=[2]` and `has-lpi=false`. Map GICD at 0x11900000 and GICR at 0x11940000. Cover the rest of 0x11900000–0x119FFFFF with an unimplemented-device window. FACT-backed; the SPI count (480) and the two redistributor frames at 0x11940000/0x11960000 are now OBSERVED on silicon.
- **D2. Security state in direct mode.** Choose `has_el3=true`, `has_el2=false` and GIC `has-security-extensions=true`.
  - QEMU then sets every interrupt to Group 1 NS on a direct boot (arm_gicv3_common.c:587-602), and Linux sees **DS = 0** (INFERENCE), matching the board's `GICD_CTRL.DS=0` (OBSERVED).
  - The CPU configuration is the same as in Stage B, apart from the conduit.
  - EXP-001 t6 showed SMC PSCI and EL1 entry behave identically with `has_el3=true`.
  - **Residual gap, now confirmed:** QEMU's `arm_emulate_firmware_reset` does not set SCR_EL3.FIQ (qemu v11.1.2 target/arm/cpu.c:719-780). Linux will log `SCR_EL3.FIQ=0`; the board logs `SCR_EL3.FIQ=1` (OBSERVED). Record it on the REQ-GUEST-004 gap list for direct mode; Stage B (real BL31) should reproduce FIQ=1.
  - The alternative (`has_el3=false`, DS = 1) is simpler but diverges in two guest-visible values (DS and FIQ) and in priority handling.
- **D3. GIC identity.** QEMU's GICD_IIDR and PIDRs are hard-coded to GIC-500-like values (gicv3_internal.h:749-787). The M1 exit criterion asks for "GIC ID registers equal to EVK values". Either:
  - (a) add an upstreamable `hw/intc/arm_gicv3` property for IIDR/product ID, or
  - (b) record a fidelity gap and limit the M1 qtest to ArchRev / GICD_TYPER fields QEMU can represent.

  **Decided: (a), as DR-0003 option A** (`../decisions/DR-0003-gic-identity.md`). The options above are kept as the derivation.
- **D4. Timer wiring.** Wire PHYS→30, VIRT→27, HYP→26, SEC→29, HYPVIRT→28 (BSA constants), the maintenance interrupt → 25 and the PMU → 23, exactly as in fsl-imx8mp.c:351-371 plus `GTIMER_HYPVIRT`.

---

## 7. Proposed M1 SoC skeleton (`TYPE_R9A07G054`)

The structure follows `fsl-imx8mp.c` / `imx8mp-evk.c` (spec REQ-MACH-001). The contents are evidence-backed as above:

1. **CPUs:** 2 × `cortex-a55`.
   - `mp-affinity` 0x0 and 0x100; `cntfrq` 24000000.
   - `has_el2=false`, `has_el3=true` (D2); `start-powered-off` on cpu1.
   - Not in M1: the board-local A55 IMPDEF reginfo (CPUPWRCTLR_EL1 required; CLUSTERIDR/CLUSTERCFR precautionary, EXP-001) belongs to M7 (REQ-MACH-005), where BL31 first uses it.
   - Later: a CLIDR/CCSIDR override (§1, gap until measured).
2. **GIC-600:** per D1, D3 and D4, realized after the CPUs; IRQ/FIQ/VIRQ/VFIQ outputs wired to each CPU.
3. **DDR:** 2 GiB RAM at 0x40000000 (the board; REQ-MACH-006). `arm_boot_info` with `loader_start=0x48000000`, `ram_size=0x78000000`, `psci_conduit=SMC`.
4. **SYSC ID registers:** at least `SYS_LSI_DEVID` @ 0x11020A04 = `0x18447447`, `SYS_LSI_PRR` @ 0x11020A08 = `0x00000000` and `SYS_LSI_MODE` @ 0x11020A00 (bit 16 = 1; bits [2:0] = the selected boot mode, e.g. `0x10203`/`0x10001`/`0x10000`). All three are OBSERVED in BL2 output on every archived boot (EVK boot log; see `sysc.md`). Linux reads LSI_DEVID unconditionally at `early_initcall` even though the DT node is disabled (linux v6.12.59 drivers/soc/renesas/renesas-soc.c:474-572; `boot-dependency-graph.md` §3).
5. **SCIF0 placeholder** at 0x1004B800 for M2 (not M1).
6. **Everything else in 0x10000000–0x12FFFFFF:** honest UNSUPPORTED or listed unimplemented windows, per `device-map.md`.
7. **qtests:**
   - GICD_PIDR2 ArchRev = 3.
   - GICR_TYPER affinity = 0x0 / 0x100 and Last on the second redistributor (at 0x11960000).
   - GICD_TYPER.ITLinesNumber = 15 (512 IRQs, i.e. 480 SPIs) and LPIS = 0.
   - SYSC LSI_DEVID = 0x18447447, LSI_PRR = 0.
   - Each assertion must be mutation-checked.

What M1 deliberately does **not** do: CPG, PFC, OSTM, WDT, DMAC. Those belong to M2/M3b; see `boot-dependency-graph.md`.

---

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target (`docs/sources.md`). Citations are `linux v6.18.55 <path>:N`. These are the places where the first draft of this note (written against v6.18.55) differs from v6.12.59:

- **DT line numbers.** `r9a07g054.dtsi` gains a disabled `gpt: pwm@10048000` node, which shifts later nodes by about 115 lines: CPUs at arch/arm64/boot/dts/renesas/r9a07g054.dtsi:87-106, SYSC 1001-1011, GIC 1164-1172, OSTM 1394-1425, timer 1459-1468, thermal 1428-1457. The CPU, GIC, timer, OSTM and PSCI node contents are unchanged. `rzg2l-smarc-som.dtsi` has G1's QSPI partition layout.
- **GIC dmesg string.** v6.18.55 prints `GICD_CTLR.DS=%d, SCR_EL3.FIQ=%d` (drivers/irqchip/irq-gic-v3.c:226); v6.12.59 and G1 print `GICD_CTRL.DS=…` (the spelling the EVK log shows). Logic and line numbers in `irq-gic-v3.c` are otherwise close to v6.12.59.
- **PSCI.** v6.18.55 also probes and implements `SYSTEM_OFF2` (drivers/firmware/psci/psci.c:341-350, 398). QEMU answers NOT_SUPPORTED.
- **Arch timer.** The MMIO (`arm,armv7-timer-mem`) timer moved to a separate driver; the CP15 path (`arch_timer_of_init`, drivers/clocksource/arm_arch_timer.c:1129-1184; virtual-timer choice at :1108-1120; sched_clock at :907-949) behaves as in v6.12.59.
- **OSTM.** The platform-driver fallback is no longer guarded by `CONFIG_ARCH_RZG2L || CONFIG_ARCH_R9A09G057` (drivers/clocksource/renesas-ostm.c:162-247). Same behaviour on V2L.
- **Kconfig.** `ARCH_R9A07G054` is default-y under `ARCH_RENESAS` in v6.18.55; in v6.12.59 the arm64 defconfig selects it explicitly (defconfig:1449).
- **CPG.** v6.18.55 drives MSTOP on every module-clock change; see `cpg-reset.md` "Newer mainline". It does not change any GIC, timer or PSCI requirement here.

## Claims to verify

1. The Arm GIC-600 r1p6 TRM (100336_0106_00) encodes p6 as Revision `0x7` (Table 4-5, p.4-112), so GICD_IIDR = GICR_IIDR = `0x0201743B`, which differs from QEMU's 0x43B. The PIDR/CIDR blocks equal QEMU's (Tables 4-2, 4-21). Evidence for the QEMU value: qemu v11.1.2 hw/intc/gicv3_internal.h:749-758; silicon via Q1.
2. Silicon GICD_TYPER has LPIS = 0 and ESPI = 0, and its IDbits/RSS values are unknown. Evidence: HW manual Rev 1.50 §8.1 p.530 ("LPI: Not supported"); Q1. (ITLinesNumber is consistent with the observed 480 SPIs.)
3. With `has_el3=true` and GIC security extensions on, a QEMU direct boot gives Linux `GICD_CTRL.DS=0` and `SCR_EL3.FIQ=0` (board: DS=0, FIQ=1). Evidence: qemu v11.1.2 hw/intc/arm_gicv3_common.c:546-551,587-602, target/arm/cpu.c:719-780; irq-gic-v3.c:165-229. To be shown by an M1 run.
4. The RAZ/WI GICR_PWRR satisfies TF-A's GIC-600 power-on sequence in Stage B. Evidence: qemu v11.1.2 hw/intc/arm_gicv3_redist.c:750-762; the TF-A `drivers/arm/gic/v3/gic600.c` power-on loop (not read here).
5. Linux cacheinfo on QEMU reports a 512 KiB L2. Evidence: qemu v11.1.2 target/arm/tcg/cpu64.c:220,254-259; HW manual Rev 1.50 §2.1 p.83 says no L2. Run `ls /sys/devices/system/cpu/cpu0/cache` in an M3 guest.
6. TF-A with opteed reports MIGRATE_INFO_TYPE as a resident TOS, while QEMU reports 2. Evidence: qemu v11.1.2 target/arm/tcg/psci.c:98-99; psci.c:553-587; EVK dmesg `Trusted OS` line (Q5).
7. No QEMU placement in direct mode overlaps 0x40000000–0x47FFFFFF. Evidence: qemu v11.1.2 hw/arm/boot.c:845-875,1000-1005,1051-1078. Check `info roms` in an M1 run.
8. A read-as-zero OSTM lets the G0 boot reach the console with a frozen `sched_clock` (silent-wrong), and an OSTM whose TE never clears hangs it. Evidence: renesas-ostm.c:46-83,198-211; sched_clock.c:164-172. Mutation test in the M3b OSTM qtest.

### Answered by the EVK boot log (2026-10-08, post-Linux, G1-based downstream image)

- **OSTM1 replaces the arch timer as `sched_clock`** at P0 = 100 MHz: `sched_clock: 32 bits at 100MHz, resolution 10ns`, `/soc/timer@12801400: used for clocksource`, `/soc/timer@12801800: used for clock events`. (Was claim 3; was Q4 in part.)
- **Linux uses the virtual timer at 24 MHz:** `arch_timer: cp15 timer(s) running at 24.00MHz (virt).` (Was claim 4; CNTFRQ part of REQ-MACH-003.)
- **GIC security state:** `GICD_CTRL.DS=0, SCR_EL3.FIQ=1`. (Was Q3, first half.) This fixes the target for D2 and turns the FIQ difference into a confirmed gap.
- **GIC sizing and redistributors:** `GICv3: 480 SPIs implemented`, `16 PPIs`, CPU0 redistributor at `0x11940000`, CPU1 (MPIDR 0x100) at `0x11960000`. (Was Q3, second half.)
- **PSCI/SMCCC versions:** `PSCIv1.1`, `SMC Calling Convention v1.4`. (Was Q5 in part.) PSCI matches QEMU; SMCCC does not.
- **CPU identity and entry level:** MIDR `0x412FD050` on both CPUs; `CPU: All CPU(s) started at EL1`.
- **SYSC IDs (BL2 output, ~150 boots):** `SYS_LSI_DEVID = 0x18447447`, `SYS_LSI_PRR = 0x00000000`, `SYS_LSI_MODE` = `0x10203`/`0x10000`/`0x10001`/`0x10200`/`0x10201` depending on the boot-mode switches. (Was Q6.)

## Questions for the EVK

All are read-only.

- **Q1** (U-Boot, before `bootm`): `md.l 0x11900000 4` (GICD_CTLR, TYPER, IIDR, TYPER2), `md.l 0x1190ffd0 12` (GICD PIDR4..CIDR3), `md.l 0x11940000 4` and `md.l 0x11960000 4` (GICR_CTLR/IIDR/TYPER for both redistributors), `md.l 0x11940014 1` (GICR_WAKER), and the full GICR0 and GICR1 ID blocks. These are side-effect-free ID/config registers. The canonical commands are EVK-R60–R66 in `../evidence/requests.md`.
- **Q2** (post-Linux): `grep . /sys/devices/system/cpu/cpu0/cache/index*/{level,type,size}` and `/proc/cpuinfo` Features. This answers CLIDR encoding with no L2, and whether the crypto extension is present.
- **Q4** (post-Linux, remainder): `cat /sys/devices/system/clocksource/clocksource0/{current,available}_clocksource` and `grep -E 'arch_timer|ostm' /proc/interrupts`. Expect `arch_sys_counter` current (rating 400 beats OSTM's 300).
- **Q5** (post-Linux, remainder): `dmesg | grep -iE 'trusted os|migrat'` and `cat /sys/devices/system/cpu/vulnerabilities/*`.

## Verification

| Claim | Result | Evidence |
|---|---|---|
| QEMU GICD_IIDR/GICR_IIDR fixed at `0x43b` | **Confirmed** | qemu v11.1.2 `hw/intc/gicv3_internal.h:749-757` |
| EL1 entry with SMC conduit via `has_el2=false`; CNTFRQ default 62.5 MHz; `mp-affinity` settable | **Confirmed** | EXP-001 (rerun by the main session); EL1 on silicon OBSERVED (`CPU: All CPU(s) started at EL1`) |
| GIC sizing, redistributor layout and security state on silicon | **Confirmed (OBSERVED)** | EVK boot log: 480 SPIs, 16 PPIs, GICR frames at 0x11940000/0x11960000, `GICD_CTRL.DS=0, SCR_EL3.FIQ=1`; strings from linux v6.12.59 `drivers/irqchip/irq-gic-v3.c:226-228, 1096-1099, 2088` |
| OSTM1 owns `sched_clock` at 100 MHz; virtual arch timer at 24 MHz | **Confirmed (OBSERVED)** | EVK boot log; linux v6.12.59 `drivers/clocksource/renesas-ostm.c:198-204`, `kernel/time/sched_clock.c:164-172`, `drivers/clocksource/arm_arch_timer.c:1399-1406` |
| The assumed GIC-600 IIDR value and the cache topology (no L2, 256 KiB L3) | **Open** | needs EVK reads and the HW manual cross-check; listed under Questions for the EVK (Q1, Q2) |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7` (DT, `irq-gic-v3.c`, `arm_arch_timer.c`, `renesas-ostm.c`, `psci.c`, `irq-renesas-rzg2l.c` identical; DT differs only in QSPI partitions; no reserved memory or DRP-AI nodes; CMA 128 MiB). Corrections against the first draft: the GIC banner reads `GICD_CTRL.DS` in v6.12.59; no SYSTEM_OFF2 probe; the OSTM platform probe is one-shot (`platform_driver_probe`); the OSTM `time_init` attempt fails with a silent `-EPROBE_DEFER`; `ARCH_R9A07G054` comes from the defconfig, not a Kconfig default. EVK boot-log evidence folded into §1-§7; Q3 and Q6 removed as answered, Q4 and Q5 reduced. v6.18.55 differences kept under "Newer mainline". |

### Main-session spot verification of the re-base

- HW manual p.530 (GIC-600, 16 PPIs), p.534 (`nCNTVIRQ` = PPI 11 = ID 27, PMU PPI 7, maintenance PPI 9, `nCNTPNSIRQ` PPI 14) and p.83 (Cortex-A55 r2p0, no L2, 256 KB L3) confirmed against the manual text.
- The QEMU stage A SMCCC gap is confirmed: qemu v11.1.2 `target/arm/tcg/psci.c` has no `SMCCC_VERSION` handling, so the guest falls back to SMCCC v1.0 (board: v1.4).

## EVK results (2026-10-29, U-Boot prompt, downstream firmware; `../evidence/EVK-2026-10-29-post-firmware.md`)

- **OBSERVED.** Q1: GICD CTLR `0x12`, TYPER `0x0079040F`, IIDR `0x0201743B`, TYPER2 0; the GICD and both GICR identity blocks (`… 92 B4 3B …`, `… 93 B4 3B …`); GICR0/1 IIDR `0x0201743B`, TYPER `0x20`/`0x0` and `0x130`/`0x100`. These match the TRM values the model asserts (EVK-R60-R63, R65, R66). REQ-MACH-007 moves to V.
- **OBSERVED, conflicts with the prediction (I).** GICR1_WAKER reads `0x0` (awake) at the U-Boot prompt, before any CPU_ON for CPU1. The prediction was `0x6` (asleep), and QEMU resets GICR_WAKER to ProcessorSleep|ChildrenAsleep. INFERENCE: firmware wakes both redistributors. That matters for the direct-mode start state (rule 9), not for firmware mode.
