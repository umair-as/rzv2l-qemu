# Boot dependency graph: G0 kernel entry → earlycon → `sh-sci` console

Based on the pinned guest kernels (`docs/sources.md` "Pinned guest kernels"). **Status:** M0 research note. It answers the acceptance question in spec §20.

**Guest (G0):** linux v6.12.59, `arm64 defconfig` Image, upstream `r9a07g054l2-smarc.dtb` (unmodified), BusyBox initramfs. **Mode:** direct (QEMU loads Image, DTB and initrd; Stage A, QEMU PSCI over SMC).

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference), qemu v11.1.2, the RZ/V2L HW manual Rev 1.50, the per-block notes (`cpu-gic.md`, `scif.md`, `cpg-reset.md`, `pinctrl.md`, `sysc.md`) and the passive EVK boot log `docs/evidence/EVK-2026-10-08-boot-log.md`. The first draft of this note was written against linux v6.18.55; where that kernel differs, the difference is kept in "Newer mainline (v6.18.55)" near the end.

**Labels:** **FACT** means read directly from source, DT or the manual. **INFERENCE** means derived from code paths I traced but did not execute. **ASSUMPTION** means not yet backed by evidence. **OBSERVED** means seen on the EVK (post-Linux boot log unless stated otherwise).

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N`:

| Short | Full path |
|---|---|
| `r9a07g054.dtsi`, `r9a07g054l2-smarc.dts`, `rzg2l-smarc-som.dtsi`, `rzg2l-smarc-pinfunction.dtsi`, `rz-smarc-common.dtsi`, `rzg2l-smarc.dtsi` | `arch/arm64/boot/dts/renesas/` |
| `setup.c`, `acpi.c` | `arch/arm64/kernel/` |
| `main.c` | `init/` |
| `earlycon.c`, `sh-sci.c`, `serial_core.c` | `drivers/tty/serial/` |
| `fdt.c`, `base.c`, `property.c`, `platform.c` (OF) | `drivers/of/` |
| `dd.c`, `core.c`, `platform.c` (driver core) | `drivers/base/` |
| `rzg2l-cpg.c`, `r9a07g044-cpg.c` | `drivers/clk/renesas/` |
| `pinctrl-rzg2l.c` | `drivers/pinctrl/renesas/` |
| `devicetree.c` | `drivers/pinctrl/` |
| `irq-gic-v3.c`, `irq-renesas-rzg2l.c` | `drivers/irqchip/` |
| `arm_arch_timer.c`, `renesas-ostm.c`, `timer-probe.c` | `drivers/clocksource/` |
| `renesas-soc.c`, `Kconfig` (soc) | `drivers/soc/renesas/` |
| `psci.c` | `drivers/firmware/psci/` |
| `printk.c` | `kernel/printk/` |
| `defconfig` | `arch/arm64/configs/` |

Where two files share a basename (`platform.c`), the directory is written out. G1 citations are `rz_linux-cip 212f6e88b7 <path>:N`; QEMU citations are `qemu v11.1.2 <path>:N`.

Configuration assumptions used throughout, from the arm64 defconfig **source** (INFERENCE until the built G0 `.config` is read, per the effective-configuration rule; the whole graph is a source-derived hypothesis until a G0 boot confirms it):

| Option | G0 value | G0 line | G1 (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig) |
|---|---|---|---|
| `CONFIG_MODULES` | y | 120 | y (:67) |
| `CONFIG_ACPI` | y (so `ACPI_SPCR_TABLE` is selected on arm64, linux v6.12.59 arch/arm64/Kconfig:12) | 109 | **not set** |
| `CONFIG_ARCH_R9A07G054` | y | 1449 | y (:359) |
| `CONFIG_SERIAL_SH_SCI` | y | 488 | y (:169) |
| `CONFIG_RENESAS_OSTM` | y | 1372 | y (:346) |
| `CONFIG_RZ_DMAC` | y | 1244 | y (:328) |
| `CONFIG_RENESAS_RZG2LWDT` | y | 738 | y (:198) |
| `CONFIG_I2C_RIIC` | y | 535 | y (:175) |
| `CONFIG_RAVB` | y | 368 | y (:146) |
| `CONFIG_MMC_SDHI` | y | 1151 | y (:305) |
| `CONFIG_RZG2L_THERMAL` | y | 704 | y (:195) |
| `CONFIG_CPUFREQ_DT` | y | 96 | y (:52) |
| `CONFIG_IP_PNP` | y | 135 | y (:83) |

Also relevant:

- **FACT:** `ARCH_R9A07G054` selects `ARCH_RZG2L`, which selects `PM`, `PM_GENERIC_DOMAINS` and `RENESAS_RZG2L_IRQC` (Kconfig:50-54, 328-332). In v6.12.59 the symbol has no Kconfig default; the defconfig sets it.
- **FACT:** the CPG, PFC and IRQC drivers are built in (bool symbols; `pinctrl.md`, `cpg-reset.md`).
- **FACT (G0):** RSPI (defconfig:567), RPC-IF (:566, :1474), CAN-FD (:399), SSI (`SND_SOC_RZ`, :991), DU/DSI (:880-881), VSP/FCP (:842, :844), the ADC (:1484), USBHS (:1075) and the GPU (`DRM_PANFROST`, :938) are `=m`. With no modules in the initramfs they never load, so they are irrelevant to G0.
- **G1 (rz-6.12-cip14) delta:** G1's defconfig builds most of these in: RSPI, RPC-IF, CAN-FD, SSI, DU, DSI, VSP1, FCP, the ADC, USBHS, the CRU/CSI-2, MTU3, and the board's I2C clients (ADV7511, DA7213, WM8978, ISL1208, VC3, RAA215300) are all `=y` (rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:93, 181-182, 202, 210, 221-241, 258-265, 280, 322, 340, 367). It has no GPU driver. With the same DT (G1's DT differs from G0's only in QSPI partitions, `cpu-gic.md`), more enabled devices probe at boot under G1; see §4.

---

## 1. Short answers

**(a) First earlycon character.**

- **Required:**
  - The CPU at EL1 with a working MMU/TCG (OBSERVED on silicon: `CPU: All CPU(s) started at EL1`).
  - RAM covering the QEMU kernel, initrd and DTB placement, with QEMU's `/memory` rewrite producing the board value (`0x48000000` + `0x78000000`, rzg2l-smarc-som.dtsi:32-36).
  - The QEMU boot stub passing x0 = DTB.
  - **`earlycon` on the kernel command line** (bare form).
  - **SCIF0 @ 0x1004B800** in the RZ/SCIFA layout, offering four things:
    1. SCSCR (+0x04, 16-bit) read and write.
    2. SCxSR/FSR (+0x08, 16-bit) with **TDFE (bit 5)** set when the TX FIFO has room and **TEND (bit 6)** set once transmission completes, cleared by the guest's read-then-write-0 sequence; TEND must not complete inside the FTDR write (`scif.md` §3.1, §7).
    3. FTDR (+0x06, 8-bit) writes going to the chardev.
    4. A post-firmware state in which the line is already usable: earlycon programs neither baud rate nor framing.
- **Not required:** the GIC, the timer/CNTFRQ, PSCI, CPG, PFC, IRQC, SYSC, OSTM. Earlycon registers inside `setup_arch()` at `acpi_boot_table_init` (setup.c:340), before `psci_dt_init` (setup.c:354), `init_IRQ()` (main.c:1020) and `time_init()` (main.c:1028).
- **OBSERVED:** on silicon a bare `earlycon` resolves through `stdout-path` to SCIF0 (`earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')`).
- **Fidelity gap:** the stock DTB bootargs do not contain `earlycon`, so `-append` is needed (§5).

**(b) First character through the real `sh-sci` console (ttySC0).**

- **Everything in (a)**, except that the `earlycon` argument is not needed.
- **Core:**
  - The GIC (distributor plus two redistributors at 0x11940000/0x11960000) with the virtual-timer PPI (INTID 27) delivered.
  - `CNTFRQ` = 24 MHz (OBSERVED).
  - PSCI over SMC: PSCI_VERSION, FEATURES, MIGRATE_INFO_TYPE; CPU_ON is soft.
- **SYSC `SYS_LSI_DEVID`** (0x11020A04) mapped and reading the silicon value `0x18447447` at `early_initcall`. The DT node is disabled but the register is read anyway; unmapped means a panic, a wrong value means `SoC mismatch` (soft but guest-visible).
- **CPG** probing once (it uses `platform_driver_probe`, so there is no retry) as clock, reset and genpd provider:
  - PLL/divider reads giving the board rates (P0 = 100 MHz, OBSERVED through OSTM).
  - **CLK_MON as a same-polarity mirror of CLK_ON**, visible within the driver's 10 µs poll.
  - **RSTMON as an inverted mirror of RST** (RSTMON = ~RST; 1 = in reset), visible within the 200 µs poll.
  - **No MSTOP behaviour:** v6.12.59 never writes MSTOP on RZ/V2L; the registers keep their post-firmware values.
  - The GPIO resets (RST 0x898) already released in the direct-mode start state, because Linux never deasserts them.
- **IRQC (IA55)** mapped and probing. This needs only the CPG (IA55 clocks, reset, runtime PM); it touches no IA55 register at probe.
- **OSTM1/OSTM2** mapped at device_initcall (unmapped is a panic before (b)), with a counting OSTMnCNT at P0 and TE that clears on TT. A read-as-zero OSTM still reaches (b), but with a frozen `sched_clock` (silent-wrong); a TE that never clears hangs before (b). OBSERVED: OSTM1 owns `sched_clock` on silicon.
- **PFC** probing:
  - It needs the CPG GPIO clock and IRQC's IRQ domain.
  - **Without a probing PFC, SCIF0 defers forever.** The pinctrl lookup returns `-EPROBE_DEFER` with no timeout when `CONFIG_MODULES=y`.
  - The PWPR/PMC/PFC writes that select SCIF0's pin function (P38_0/P38_1, function 1) must be accepted.
  - GPIO hogs must be accepted.
- **SCIF0** probing: pinctrl state, genpd attach, reset deassert (RSTMON poll), `fck` = P0.
- `register_console(ttySC0)` then writes through the same polled TDFE/TEND path.
- **Not required for the first character:**
  - SCIF interrupts (the console write path polls).
  - The DMAC (`scif0` has no `dmas`).
  - The rest of the GIC SPI routing.
- **Must not crash before it:** every built-in driver whose device probes earlier (§4). Each must reach its own register window and fail softly.
- **OBSERVED:** on the EVK image the real console probes about 0.6 s into boot (`1004b800.serial: ttySC0 at MMIO 0x1004b800 … is a scif` at 0.594 s, then `printk: legacy console [ttySC0] enabled`).

---

## 2. Dependency graph

```mermaid
graph TD
  E0[QEMU direct boot: Image @0x48200000, DTB+initrd in RAM, x0=DTB, EL1 NS] --> E1[head.S: MMU on, ID regs]
  E1 --> E2[setup_arch: FDT scan, memblock from /memory]
  E2 -->|bootargs has 'earlycon'| EC[earlycon via stdout-path → renesas,scif-r9a07g044 → rzscifa]
  EC --> SCIFREG[SCIF0 MMIO: SCSCR r/w, FSR TDFE/TEND, FTDR]
  SCIFREG --> A((a) first earlycon char)
  E2 --> PSCI[psci_dt_init: SMC PSCI_VERSION/FEATURES]
  E2 --> GIC[init_IRQ: GICv3 dist+redist, PIDR2, GICR_TYPER aff]
  GIC --> TMR[time_init: arch timer, CNTFRQ=24MHz, virt PPI 27; OSTM attempt defers]
  TMR --> SMP[smp_init: PSCI CPU_ON 0x100 — soft]
  TMR --> SOCID[early_initcall renesas_soc_init: read SYSC 0x11020A04]
  SOCID --> CPG[subsys_initcall: CPG probe, one-shot — clocks, resets, always-on genpd, no MSTOP]
  CPG --> IRQC[device_initcall: IRQC probe — clk/reset/runtime PM only]
  CPG --> OSTM[device_initcall: OSTM1/2, one-shot — sched_clock takeover]
  CPG --> OTHERS[device_initcall: WDT, DMAC, TSU, usbphy-ctrl ... must not abort]
  CPG --> PFC[late_initcall deferred flush: PFC probe]
  IRQC --> PFC
  PFC --> SCIF[late_initcall deferred flush: sh-sci probe of serial@1004b800]
  CPG --> SCIF
  SCIF --> CON[uart_add_one_port → of_console_check → register_console ttySC0]
  CON --> B((b) first ttySC0 char)
```

---

## 3. Trace

### 3.1 Kernel entry to the first earlycon character

1. **Entry.**
   - **FACT:** QEMU loads the Image at loader_start + 2 MiB. Its stub sets x0 = DTB and jumps (qemu v11.1.2 hw/arm/boot.c:70-77,845-875). See `cpu-gic.md` §5.1.
   - **FACT:** Linux requires a DTB that is 8-byte aligned, ≤ 2 MiB and in RAM (linux v6.12.59 Documentation/arch/arm64/booting.rst:50-52,162).
   - **INFERENCE:** head.S at EL1 touches only system registers (SCTLR, TCR, MAIR, TTBRx, ID registers), no MMIO.
2. **`setup_arch`** (setup.c:282-377):
   - `kaslr_init` (288). No `kaslr-seed` in the DT, and QEMU adds none, so KASLR is off. On the board, U-Boot adds a seed only when the OP-TEE RNG works (boot-chain-firmware.md §4).
   - `setup_machine_fdt` (293). An invalid DTB makes the kernel spin forever with no output (setup.c:169-207, loop at :194-195).
   - `parse_early_param` (300).
   - `arm64_memblock_init` and `paging_init` (333, 335).
   - `acpi_boot_table_init` (340).
3. **How a bare `earlycon` resolves (G0).**
   - **FACT:** with `CONFIG_ACPI_SPCR_TABLE`, a bare `earlycon` only sets `earlycon_acpi_spcr_enable` (earlycon.c:230-249, branch at :235-238).
   - **FACT:** because ACPI is disabled on a DT boot, `acpi_boot_table_init` then calls `early_init_dt_scan_chosen_stdout()` (acpi.c:233-235).
   - **FACT:** that function reads `/chosen/stdout-path` = `"serial0:115200n8"` (rz-smarc-common.dtsi:31-33) and resolves alias `serial0 = &scif0` (rz-smarc-common.dtsi:25-26). It walks `__earlycon_table` for a compatible match against `"renesas,scif-r9a07g054", "renesas,scif-r9a07g044"` (r9a07g054.dtsi:380-382) (fdt.c:875-920).
   - **FACT:** the match is `OF_EARLYCON_DECLARE(scif, "renesas,scif-r9a07g044", rzscifa_early_console_setup)` (sh-sci.c:3775). It selects `SCIx_RZ_SCIFA_REGTYPE` (sh-sci.c:3742-3747; register layout sh-sci.c:312-336).
   - **FACT:** the console is registered with `CON_PRINTBUFFER | CON_BOOT` (earlycon.c:31), so it replays the log buffer from the first `Booting Linux…` line.
   - So the first earlycon character comes out at `setup.c:340`, after paging_init and before the GIC or timer exist.
   - **OBSERVED:** the same resolution happens on silicon (`earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')`).
   - **G1 (rz-6.12-cip14) delta:** G1's defconfig has no `CONFIG_ACPI`, so `ACPI_SPCR_TABLE` is off and `param_setup_earlycon` calls `early_init_dt_scan_chosen_stdout()` directly (earlycon.c:239-240; same file in G1). Earlycon then starts inside `parse_early_param` (setup.c:300), before `paging_init`, via the fixmap. The register traffic is identical. INFERENCE from source; confirm against the G1 `.config` (`/proc/config.gz`, `CONFIG_IKCONFIG_PROC=y` at rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig:425).
   - **Do not use `earlycon=scif,0x1004b800`.**
     - **FACT:** `setup_earlycon()` matches entries by name, preferring entries with no compatible first (earlycon.c:183-221).
     - **INFERENCE:** every `scif` entry has a compatible, so the first `scif` in table order wins: `"renesas,scif"` with the SH4-SCIF layout (sh-sci.c:3773). That layout has the wrong register offsets for the RZ SCIFA.
     - Use bare `earlycon`.
4. **Register traffic** (sh-sci.c:3711-3731, 3115-3150, 762-772).
   - **Setup** reads SCSCR and writes it back ORed with RE|TE (sh-sci.c:3723-3725).
   - **Per string** (`serial_console_write`):
     1. Write SCSCR.
     2. Per character (`sci_poll_put_char`), poll SCxSR until TDFE is set.
     3. Write FTDR.
     4. Clear TDFE while leaving TEND set.
     5. At the end, poll SCxSR until both TDFE and TEND are set (sh-sci.c:3141-3143), then restore SCSCR.
   - **There is no timeout anywhere** (FACT). A model that never sets TDFE or TEND hangs the kernel silently at (a).
   - **FACT:** earlycon never writes SCSMR, SCBRR or SCFCR. Direct mode must start SCIF0 with SCFCR.TFRST = 0 and framing as U-Boot left it (spec §9 post-firmware overlay; `scif.md` §6.2).
   - **FACT:** `of_setup_earlycon` maps 4 KiB at the `reg` address (earlycon.c:253-278). Only the SCIF0 window is touched.

### 3.2 From earlycon to the `sh-sci` probe

5. **`psci_dt_init`** (setup.c:354). SMC PSCI_VERSION, MIGRATE_INFO_TYPE, FEATURES(SMCCC_VERSION / CPU_SUSPEND / SYSTEM_SUSPEND / SYSTEM_RESET2) (psci.c:636-662). All are answered by QEMU (`cpu-gic.md` §4). If the conduit were not SMC, the SMC would UNDEF and the kernel would die with only earlycon output (EXP-001 conclusion 2). FACT. OBSERVED on silicon: `PSCIv1.1`, `SMC Calling Convention v1.4` (QEMU leads Linux to print v1.0: a guest-visible gap).
6. **`init_IRQ` → GICv3 `gic_of_init`** (main.c:1020; irq-gic-v3.c:2307-2377):
   - PIDR2 ArchRev, GICD_TYPER, IIDR quirks.
   - The redistributor walk matches GICR_TYPER.Aff to the MPIDR.
   - WAKER and RWP polls have 1 s timeouts.
   - Supported by stock `arm_gicv3` given the correct `mp-affinity` (`cpu-gic.md` §2.1). FACT. OBSERVED on silicon: 480 SPIs, redistributors at 0x11940000/0x11960000, `GICD_CTRL.DS=0, SCR_EL3.FIQ=1`.
7. **`time_init` → `arch_timer_of_init`** (main.c:1028; arm_arch_timer.c:1420-1481).
   - CNTFRQ is read with no DT override. The virtual timer is used, on INTID 27 (arm_arch_timer.c:1399-1406). OBSERVED: `24.00MHz (virt)`.
   - **FACT:** a wrong CNTFRQ (QEMU's default of 62.5 MHz) still boots, but makes every delay and timestamp wrong by a factor of 2.6. That is silent-wrong, so `cntfrq=24000000` is mandatory.
   - The timer IRQ must reach the CPU through the GIC for jiffies to advance. Every later `msleep`/`usleep_range`/workqueue timeout depends on it.
   - **ostm1/ostm2.** `ostm_init` also runs here via `TIMER_OF_DECLARE` (renesas-ostm.c:226). Its reset lookup returns `-EPROBE_DEFER` because the CPG reset controller is not registered yet (renesas-ostm.c:172-176; linux v6.12.59 drivers/reset/core.c:1045-1049), and `timer_probe` skips the node without a message (timer-probe.c:30-35). It touches no OSTM register on that path. FACT.
8. **`smp_init`** (main.c:1584). PSCI CPU_ON(0x100). If it fails, Linux continues on one CPU after a timeout (INFERENCE: soft for (b), required for the M3 exit). OBSERVED: CPU1 boots on silicon.
9. **`do_pre_smp_initcalls` → `renesas_soc_init`** (main.c:1581; early_initcall; renesas-soc.c:474-572).
   - **FACT:** it matches `renesas,r9a07g054-sysc` (renesas-soc.c:466) with `of_find_matching_node_and_match` (:497), which **ignores `status = "disabled"`** (the SYSC node is disabled, r9a07g054.dtsi:886-896, status at :895).
   - **FACT:** it maps the node (:500) and reads `base + 0xA04` (:443, :519), derives the revision from bits [31:28] (:534-538) and compares bits [27:0] with 0x8447447 (:189-192, :546-551).
   - **Unmapped:** a synchronous external abort in PID 1 context, so a panic before (b) (INFERENCE from spec §7's "unmapped → abort").
   - **Reads 0:** `SoC mismatch` and no `soc_device`. That is soft, but guest-visible: `/sys/devices/soc0` is missing.
   - **OBSERVED:** silicon reads `0x18447447` (BL2 output on every archived boot), and Linux prints `Detected Renesas RZ/V2L r9a07g054 Rev 1` (format at :554-555).
   - **Required:** SYSC LSI_DEVID = `0x18447447` (M1).
   - G1 (rz-6.12-cip14) delta: same contract (rz_linux-cip 212f6e88b7 drivers/soc/renesas/renesas-soc.c:466, :488, :517; see `sysc.md`).
10. **`do_initcalls`, in initcall order.** The order of these steps is code-derived; the EVK log so far confirms only the ttySC0 timestamp (Q-B1).
    - **core_initcall: `rzg2l_pinctrl_init`** registers the PFC driver (pinctrl-rzg2l.c:3211).
    - **arch_initcall_sync: `of_platform_default_populate_init`** creates the platform devices (linux v6.12.59 drivers/of/platform.c:503-600).
      - The PFC device is added and probed at once, but its fw_devlink supplier (CPG: `clocks`, `power-domains`, `resets`) has no driver yet, so it is deferred (core.c:1051-1100).
      - **FACT:** deferred probing is **not re-triggered until `late_initcall`**: `driver_deferred_probe_trigger` returns early until `deferred_probe_initcall` sets `driver_deferred_probe_enable` (dd.c:175-178, 344-375).
    - **subsys_initcall: `rzg2l_cpg_init`** uses `platform_driver_probe` (rzg2l-cpg.c:1944-1949).
      - The probe (rzg2l-cpg.c:1839-1901) registers the core clocks (reading the PLL/divider registers), the module clocks, the clock provider (:1884), a single always-on genpd with `GENPD_FLAG_PM_CLK` (:1701-1742, :1776-1782) and the reset controller (:1896, :1540-1549). **There is no MSTOP pass** (`cpg-reset.md` §2.4, §4).
      - **`platform_driver_probe` never retries** (linux v6.12.59 drivers/base/platform.c:913-942, :1410-1411). A CPG probe failure is permanent, and every consumer then defers forever (§3.4).
    - **device_initcall** (built-in drivers in link order):
      - **IRQC.** `IRQCHIP_PLATFORM_DRIVER` (irq-renesas-rzg2l.c:628-631). Its probe (:531-614) does `irq_find_host(GIC)` (:543-547), maps its window without touching it (:555), parses its DT interrupts (:559-563), deasserts its reset with an RSTMON poll (:565-573), runtime-resumes (genpd → IA55 clocks → CLK_MON poll, :575-580) and creates the hierarchy domain (:584-591). **FACT:** no IA55 register is read or written at probe.
      - **sh-sci registers** (`module_init`, sh-sci.c:3673-3677, 3782). `serial@1004b800` is attempted. Its CPG supplier is bound, but its pinctrl supplier is not, so it is deferred again.
      - **OSTM** (`builtin_platform_driver_probe`, renesas-ostm.c:228-249), WDT, DMAC, TSU, usbphy-ctrl and others probe now. See §4.
    - **late_initcall: `deferred_probe_initcall`** (dd.c:344-375). The deferred list is flushed:
      - **PFC probes.** `devm_clk_get_enabled` (GPIO_HCLK, pinctrl-rzg2l.c:2762), then pinctrl registration (:2638-2729), then `rzg2l_gpio_register()`, which **returns `-EPROBE_DEFER` if IRQC has no domain yet** (:2569-2636, check at :2580-2587). IRQC bound at device_initcall, so this succeeds. The GPIO hogs (`sd0-pwr-en`, `sd0-dev-sel`, `can0/1-stb`, `sd1-pwr-en`) are applied then (rzg2l-smarc-som.dtsi:240-271; rzg2l-smarc-pinfunction.dtsi:21-39,88-93). The driver makes no reset calls, so the GPIO resets must already be released (`cpg-reset.md` §5, claim 4).
      - **SCIF0 probes.** See §3.3.
      - **INFERENCE:** SCIF0 was deferred before RIIC, RAVB and SDHI (the tty driver registers earlier in link order), so it is reprobed ahead of them in the same flush. Confirm with Q-B1.
      - **OBSERVED (consistency):** the EVK image's ttySC0 probes at 0.594 s, well before the 10 s deferred-probe timeout, which fits a probe in the late_initcall flush (INFERENCE).

### 3.3 The `sh-sci` probe and console handover

11. **Before `sci_probe`** (`really_probe`, dd.c:603-640).
    - `device_links_check_suppliers` (dd.c:619) passes once CPG and PFC are bound.
    - `pinctrl_bind_pins` (dd.c:635) applies `pinctrl-0 = <&scif0_pins>`, which is P38_0 and P38_1 in function 1 (rz-smarc-common.dtsi:136-140; rzg2l-smarc-pinfunction.dtsi:76-79). This is a PFC write sequence; `pinctrl.md` owns the details.
    - `platform_probe` then attaches the genpd (linux v6.12.59 drivers/base/platform.c:1379-1399). `genpd_dev_pm_attach` finds the CPG provider, or returns `driver_deferred_probe_check_state()` (linux v6.12.59 drivers/pmdomain/core.c:2952-2972). `rzg2l_cpg_attach_dev` adds the SCIF0 module clock to the pm_clk list (rzg2l-cpg.c:1607-1645).
12. **`sci_probe`** (sh-sci.c:3483-3565):
    - `sci_parse_dt` gets the reset with `devm_reset_control_get_optional_exclusive` (optional in code, but the DT lists it) and deasserts it (sh-sci.c:3343-3374). The deassert writes RST 0x884 = `0x00010001` and polls RSTMON 0xA04 bit 0 until it reads **0**, for at most 200 µs (r9a07g044-cpg.c:415; rzg2l-cpg.c:1454-1481). A same-polarity RSTMON mirror would time out here and fail the probe.
    - It looks up alias `serial0`, giving index 0 (sh-sci.c:3381).
    - `sci_init_single` gets the IRQs: the first is required, the rest optional (sh-sci.c:3009-3014). They are GIC SPIs 380, 382, 383, 381, 384, 384 (eri, rxi, txi, bri, dri, tei; r9a07g054.dtsi:384-391) and need no IRQC.
    - `sci_init_clocks` gets `fck` (sh-sci.c:2903-2985).
    - Because earlycon owns `sci_ports[0]` at the same `mapbase`, the probe takes a runtime-PM reference instead of re-gating clocks (sh-sci.c:3456-3478). With earlycon at a *different* address it would fail with `-EBUSY` (sh-sci.c:3533-3534).
13. **Console registration.**
    - `uart_add_one_port` (sh-sci.c:3480) calls `of_console_check(np, "ttySC", 0)`. Since `scif0` is `of_stdout` and no `console=` was given, this adds the preferred console with options `115200n8` (serial_core.c:3179; base.c:1906-1915).
    - `register_console` (printk.c:3929) calls `serial_console_setup` (sh-sci.c:3152), then `uart_set_options`, then `sci_set_termios` (sh-sci.c:2507). `sci_set_termios` calls `sci_port_enable` (sh-sci.c:2621, body at :582-596): runtime-PM get → genpd → `clk_prepare_enable`, which writes CLK_ON 0x584 = `0x00010001` and polls CLK_MON 0x704 bit 0 until it reads **1**, for at most 10 µs (r9a07g044-cpg.c:334-335; rzg2l-cpg.c:1209-1246, poll at :1239-1240). No MSTOP register is written. It then reads the clock rate, runs `sci_reset` (SCSCR = 0, SCFCR with RFRST|TFRST, clears SCxSR/SCLSR; sh-sci.c:2472-2505) and programs SCSMR/SCBRR/SEMR from the fck rate.
    - The first `ttySC0` character uses the same polled path as earlycon.
    - **FACT:** the return value of `clk_prepare_enable` is ignored (sh-sci.c:592). A CLK_MON mismatch therefore only logs `Failed to enable CLK_ON…` (rzg2l-cpg.c:1242) and does not block output on QEMU. On silicon it would mean an unclocked SCIF, so the model must mirror the bit.
    - Handover:
      - **With earlycon:** the new console drops `CON_PRINTBUFFER`, so ttySC0 starts at the next record and nothing is printed twice. Then the boot console is unregistered unless `keep_bootcon` (printk.c:4008-4010, 4078-4085).
      - **Without earlycon:** ttySC0 replays the whole buffer, so the first ttySC0 character is the `B` of `Booting Linux`.
    - **OBSERVED:** `printk: legacy console [ttySC0] enabled` right after the ttySC0 probe line on the EVK image.
14. **Later, not needed for the first character.**
    - When init opens `/dev/console`, `sci_startup` requests the SCIF IRQs (sh-sci.c:2290-2307), so GIC SPI delivery and the SCIF interrupt sources become required for the shell (M3).
    - `scif0` has no `dmas` property (r9a07g054.dtsi:380-397), so the DMAC is never used for it. FACT.

G1 (rz-6.12-cip14) delta for §3.2-§3.3: none on this path. `sh-sci.c` differs by one line (a struct copy instead of `memcpy` in `early_console_setup`, rz_linux-cip 212f6e88b7 drivers/tty/serial/sh-sci.c:3718), `rzg2l-cpg.c` by a non-functional 5-line change, and `irq-renesas-rzg2l.c`, `renesas-ostm.c`, `dd.c`, `core.c`, `fdt.c`, `earlycon.c` and `devicetree.c` are identical. The PFC driver delta has no V2L register effect (`pinctrl.md` §10).

### 3.4 fw_devlink and deferral: which failures block SCIF0 forever

- **FACT:** SCIF0's fw_devlink suppliers are **CPG** (`clocks`, `resets`, `power-domains`) and **PFC** (`pinctrl-0`, which resolves to the pin controller's device). The interrupt parent is the GIC, an OF-declared irqchip, not a device (property.c:1210, 1217, 1223, 1233, 1286-1299, 1353-1391).
- **FACT:** a consumer waits on any supplier that has not bound (`supplier … not ready`). The only exception is "best effort" with an inferred link to a supplier that has **no matching driver** (core.c:1013-1017, 1051-1100).
- **FACT:** after the 10 s deferred-probe timeout (`CONFIG_MODULES=y`; dd.c:259-262, 304-310), `fw_devlink_drivers_done` relaxes only links whose supplier `!can_match`, i.e. no driver ever matched (core.c:1758-1775). A supplier whose driver matched but failed or keeps deferring keeps its consumers blocked **forever**. That applies to the CPG, the PFC, and IRQC through the PFC.
- **FACT:** the pinctrl DT-map path returns `-EPROBE_DEFER` with no timeout when `CONFIG_MODULES=y` and the controller is not registered (devicetree.c:123-136). It does not consult `driver_deferred_probe_check_state()`. **Without a probing PFC, SCIF0 never probes** (`pinctrl.md` Verification).
- **FACT:** genpd attach would turn into `-ETIMEDOUT` after the timeout (`driver_deferred_probe_check_state`, dd.c:288-301). That is a probe failure, not output.

| Supplier failure | Effect on SCIF0 |
|---|---|
| CPG probe fails (e.g. a CLK_MON poll fails for a critical clock, or a PLL read gives a zero rate) | blocked forever (fw_devlink, and `platform_driver_probe` does not retry), plus genpd/clock lookups fail |
| RSTMON not inverted (same-polarity mirror or stuck) for SCIF0 | reset deassert times out, probe error (sh-sci.c:3363-3367): no ttySC0 |
| CLK_MON not mirroring CLK_ON for SCIF0 | logged only on QEMU (return value ignored); silent-wrong if the model also keeps the SCIF running |
| PFC probe fails, PFC unmodelled, or IRQC never probes | blocked forever |
| PFC probes but the SCIF0 mux write is lost | probe succeeds. On silicon the pins would not carry TX; on QEMU output still appears. The model must not silently ignore it (`pinctrl.md`) |
| DMAC absent | no effect (no `dmas`) |
| GIC SPI routing wrong | no effect on the first character; breaks the interactive console |

---

## 4. Other devices that probe before or alongside SCIF0

**Rule (INFERENCE, from spec §7):** an access to an **unmapped** address is a synchronous external abort. During a built-in probe that runs in PID 1, that is an Oops, then a panic (`Attempted to kill init`), **before (b)**. Every enabled, built-in device in the list below therefore needs at least a mapped window (model or listed STUB) by M3b. Enabled nodes come from the flattened DT.

| Device (DT) | Probe stage | Hang risk if unmodelled? | Soft-fail behaviour | Needed by |
|---|---|---|---|---|
| SYSC `system-controller@11020000` (disabled, still read) | early_initcall | abort if unmapped | reads 0: `SoC mismatch`, no soc0 | **M1** (ID reg) |
| OSTM1/2 `timer@12801400/1800` (rzg2l-smarc-som.dtsi:167-173) | device_initcall, one-shot | `ostm_timer_stop` spins on TE **with no timeout** (renesas-ostm.c:46-59) | a counter frozen at 0 becomes sched_clock: **silent-wrong** (`cpu-gic.md` §3) | **M3b** (FUNCTIONAL counter at P0, TE/TS/TT) |
| WDT0/1 `watchdog@12800800/c00` (rzg2l-smarc-som.dtsi:384-392) | device_initcall | none at probe; needs non-zero oscclk/pclk rates or probe fails (linux v6.12.59 drivers/watchdog/rzg2l_wdt.c:251-284) | the watchdog is not started by Linux unless userspace opens it; WDT0 is not running in direct mode | M3b map; M4 functional (spec §11) |
| DMAC `dma-controller@11820000` | device_initcall | reset deassert plus register writes at probe; `read_poll_timeout` only on channel stop (linux v6.12.59 drivers/dma/sh/rz-dmac.c:645, 845-908) | probe OK with a write-retaining stub (INFERENCE) | M3b map |
| TSU `thermal@10059400` (no status, so enabled) | device_initcall | `readl_poll_timeout` on TSU_SS (bounded) (linux v6.12.59 drivers/thermal/renesas/rzg2l_thermal.c:139, 161-204) | `Failed to start TSU`, no thermal zone; a model returning garbage could trip the 125 °C critical trip and power off (r9a07g054.dtsi:1329-1333) | M3b map; leave failing honestly |
| IRQC `interrupt-controller@110a0000` | device_initcall | none at probe; IITSR/TSSR read-modify-writes at IRQ allocation (e.g. the Ethernet PHY IRQs, rzg2l-smarc-som.dtsi:105,132) (irq-renesas-rzg2l.c:285-400) | — | **M3b** (required supplier; STUB with reset values) |
| PFC `pinctrl@11030000` | late (deferred) | GPIO-hog and mux writes | — | **M3b** (FUNCTIONAL) |
| usbphy-ctrl `11c40000`, USB2 PHY, EHCI/OHCI `11c50000/11c70000` | device_initcall / deferred (PHY has pinctrl-0) | EHCI/OHCI reset handshakes are bounded (INFERENCE) | probe failures | map in M3b; USB out of scope (spec §18) |
| RIIC0/1/3 `i2c@10058000/400/c00` | deferred (pinctrl-0) | no poll in v6.12.59: a set bus-busy bit fails the transfer at once with `-EBUSY`; otherwise the transfer waits for completion with the adapter timeout (linux v6.12.59 drivers/i2c/busses/i2c-riic.c:149-152, 169) | client probes (PMIC `raa215300` @ i2c3, versa3 @ i2c3, codec) fail fast or time out, roughly 1 s each (INFERENCE) | map; "probe failure accepted early" (spec §11) |
| SDHI0/1 `mmc@11c00000/10000` | deferred (pinctrl-0) | bounded loops (e.g. reset-status poll, linux v6.12.59 drivers/mmc/host/renesas_sdhi_core.c:590) | eMMC/SD init errors (−110) | map; M5 |
| ravb eth0/1 `ethernet@11c20000/30000` | deferred (pinctrl-0) | `ravb_wait` is bounded (linux v6.12.59 drivers/net/ethernet/renesas/ravb_main.c:49-58) | probe fails. Then `ip=on` waits up to 12 s for a netdev (linux v6.12.59 net/ipv4/ipconfig.c:1438-1460) **after** (b) | map; M6 |
| SCIF2 `serial@1004c000` (ttySC1; alias `serial1`, rzg2l-smarc.dtsi:13, enabled at :170-176) | deferred (pinctrl-0) | as for SCIF0 | — | STUB/same model in M2/M3b. OBSERVED on the EVK image at 2.34 s (that image's DT is downstream) |
| cpufreq-dt (virtual device) | device_initcall | CPG divider status poll is bounded (rzg2l-cpg.c:169-175) | transition error | CPG M3b |
| `=m` drivers in G0 (RSPI, RPC-IF, CAN-FD, SSI, ADC, DU/DSI, VSP/FCP, USBHS, GPU) | never in G0 | — | — | windows still mapped for the G1/M4 profile |

**G1 (rz-6.12-cip14) delta:** with G1's defconfig, these enabled nodes also probe at boot, at device_initcall or (when they carry `pinctrl-0` or wait on another supplier) in the deferred flush, alongside SCIF0: RSPI `spi@1004b000`, RPC-IF `spi@10060000` (QSPI flash; G1 partitions), CAN-FD `can@10050000`, SSI `ssi@10049c00/1004a000`, ADC `adc@10059000`, DU `display@10890000`, DSI `dsi@10850000`, VSP `vsp@10870000`, FCP `fcp@10880000`, USBHS `usb@11c60000`, the simple-audio sound card and the I2C clients behind it. The GPU node `gpu@11840000` stays unbound (no driver). Each needs a mapped window and an honest soft failure before G1 can reach its console, so the "never in G0" row does not hold for G1. This changes no requirement for G0. INFERENCE from defconfig plus DT; the effective `.config` of the G1 build decides.

**Risk after (b), not before.**

- `clk_disable_unused` and genpd's unused power-off run at `late_initcall_sync`, after the deferred flush. OBSERVED: `clk: Disabling unused clocks` at 3.0 s on the EVK image, after ttySC0 (0.594 s).
- **INFERENCE:** if SCIF0 had **not** probed, then on silicon the CPG would gate the SCIF0 clock under a still-active earlycon. `sci_poll_put_char` would then spin forever (the sh-sci.c:3464-3469 comment describes exactly this).
- How a clock-stopped SCIF behaves under QEMU is the open §7 oracle question. A model that ignores clock gating would keep printing (silent-wrong).

---

## 5. Bootargs and the fidelity gap list

- **FACT:** stock DT `/chosen/bootargs` = `"ignore_loglevel rw root=/dev/nfs ip=on"` (rzg2l-smarc-som.dtsi:28-30). `stdout-path = "serial0:115200n8"` (rz-smarc-common.dtsi:31-33). G1: identical.
- **FACT:** QEMU leaves `bootargs` untouched unless `-append` is non-empty (qemu v11.1.2 hw/arm/boot.c:603-609).

Two runs:

- **M3b run, no gap:** no `-append`. ttySC0 is selected through `stdout-path` (no `console=` needed). `root=/dev/nfs` is ignored because the initramfs provides `/init` (main.c:162, 1603-1605; INFERENCE). `ip=on` causes a delay of up to about 12 s after the console is up (above).
- **M3a run, one gap:** `-append "ignore_loglevel rw root=/dev/nfs ip=on earlycon"`. This is the stock string plus `earlycon`. It is **QEMU-run-specific** and goes on the list. (OBSERVED: the EVK image's command line also carries a bare `earlycon`, added by its own boot chain; it is not in DTB-U.)

Fidelity-gap list contributed by this analysis (spec REQ-GUEST-004):

1. `earlycon` appended for M3a (bare form only; the `scif,<addr>` form selects the wrong layout).
2. QEMU replaces `/psci` (it adds the `arm,psci` compatible and function-ID properties) (qemu v11.1.2 hw/arm/boot.c:366-442).
3. `/memory` is rewritten by QEMU. The value is identical if `loader_start`/`ram_size` are set as in `cpu-gic.md` §5.1.
4. `linux,initrd-start/end` are added. On the board the initramfs comes through U-Boot instead (equivalent in kind).
5. No `kaslr-seed`, and no `u-boot,*` properties (boot-chain-firmware.md §4).
6. SMCCC v1.0 is reported where silicon reports v1.4 (OBSERVED), and MIGRATE_INFO_TYPE may differ (`cpu-gic.md` §4).
7. Direct mode: `SCR_EL3.FIQ=0` in the GIC banner where silicon prints `SCR_EL3.FIQ=1` (OBSERVED; `cpu-gic.md` §6 D2).

---

## 6. Component table

| Component | Required behaviour | Evidence | Milestone |
|---|---|---|---|
| Cortex-A55 ×2 | EL1 NS entry, MIDR r2p0, mp-affinity 0x0/0x100, cntfrq 24 MHz, cpu1 powered off | EXP-001; r9a07g054.dtsi:87-106; HW manual Rev 1.50 §2.1 p.83; OBSERVED MIDR 0x412FD050, EL1, CPU1 0x100 | M1 |
| DDR + loader | 2 GiB @ 0x40000000; `/memory` = 0x48000000 + 0x78000000; Image @ 0x48200000 | rzg2l-smarc-som.dtsi:32-36; HW manual Rev 1.50 §5.2.1 Table 5.1 (1/3) p.143; qemu v11.1.2 hw/arm/boot.c:530-579,845-875 | M1 |
| SCIF0 TX path | SCSCR r/w; FSR TDFE/TEND set appropriately, cleared by read-then-write-0, TEND not synchronous with FTDR; FTDR → chardev; usable post-firmware state | sh-sci.c:312-336,762-772,3115-3150,3711-3731; `scif.md` §3.1, §6.2, §7; OBSERVED earlycon on SCIF0 | **M2** (enables M3a) |
| `earlycon` bootarg | present on the command line (gap) | earlycon.c:230-249; acpi.c:233-235; fdt.c:875-920 | M3a |
| PSCI (SMC) | VERSION 1.x, FEATURES, MIGRATE_INFO_TYPE; CPU_ON(0x100) | psci.c:553-662; qemu v11.1.2 target/arm/tcg/psci.c:95-205; OBSERVED PSCI 1.1 / SMCCC 1.4 | M1 (built in) / M3 (SMP) |
| GIC-600 | GICv3 dist + 2 redists (0x11940000, stride 0x20000), PIDR2 = 3, GICR_TYPER aff, WAKER, 512 IRQs (480 SPIs), DS = 0 | irq-gic-v3.c:165-229,367-399,1033-1100,2307-2377; r9a07g054.dtsi:1049-1057; HW manual Rev 1.50 §8.1 p.530; OBSERVED 480 SPIs, redistributor frames, DS=0/FIQ=1 | M1 |
| Arch timer | CNTFRQ 24 MHz; virt timer → INTID 27 level | arm_arch_timer.c:1399-1406,1420-1481; r9a07g054.dtsi:1344-1353; OBSERVED `24.00MHz (virt)` | M1 |
| SYSC LSI_DEVID | 0x11020A04 reads `0x18447447` (bits [27:0] = 0x8447447, revision 1); PRR 0x11020A08 = 0 | renesas-soc.c:189-192,443,466,497-551; OBSERVED BL2 output and `Detected Renesas RZ/V2L r9a07g054 Rev 1`; `sysc.md` | **M1** (needed before (b)) |
| CPG | one-shot probe succeeds: PLL/divider reads give the board rates (P0 = 100 MHz); CLK_ON → CLK_MON same-polarity mirror (10 µs); RST → RSTMON **inverted** mirror (200 µs); single always-on genpd; **no MSTOP writes by v6.12.59** (keep post-firmware values); GPIO resets released in the start state; SCIF0, GPIO, IA55, OSTM, WDT, DMAC clocks/resets | rzg2l-cpg.c:169-175,1209-1246,1425-1481,1607-1645,1701-1782,1839-1901,1944-1949; r9a07g044-cpg.c:168,206-221,334-335,356,372-427,435-439; `cpg-reset.md` §2.2-§2.4, §5; OBSERVED P0 via OSTM | **M3b** |
| IRQC (IA55) | mapped; probe needs only CPG clocks/reset/runtime PM; IITSR/TSSR RMW-safe | irq-renesas-rzg2l.c:285-400,531-631 | **M3b** |
| PFC | must probe (else SCIF0 defers forever); PWPR/PMC/PFC writes for P38_0/1 fn1; GPIO hogs; provides the GPIO IRQ domain on IRQC | pinctrl-rzg2l.c:2569-2777,3211; devicetree.c:123-136; rzg2l-smarc-pinfunction.dtsi:76-79; `pinctrl.md` | **M3b** |
| SCIF0 driver path | reset deassert (RSTMON → 0), fck rate, `sci_reset` FIFO resets, SCSMR/SCBRR/SEMR accepted | sh-sci.c:582-596,2472-2505,2903-2985,3343-3403,3456-3480; OBSERVED ttySC0 at 0.594 s | **M3b** |
| OSTM1/2 | mapped by device_initcall; counting at the P0 rate; TE follows TS/TT | renesas-ostm.c:46-83,162-249; sched_clock.c (linux v6.12.59 kernel/time/sched_clock.c:164-172); HW manual Rev 1.50 §20.2.2.3 p.1229, §20.2.2.5 p.1230; OBSERVED OSTM1 sched_clock at 100 MHz | M3b (mapped: before (b); counting: honesty) |
| WDT0/1, DMAC, TSU, usbphy, EHCI/OHCI, RIIC, SDHI, ravb | mapped windows; bounded honest probe failure accepted | §4 | M3b (map), later milestones (function) |
| SCIF interrupts (SPI 380–384) | delivered for an interactive console | sh-sci.c:2290-2307; r9a07g054.dtsi:384-391 | M3 (shell) |

---

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target (`docs/sources.md`). Citations are `linux v6.18.55 <path>:N`. The dependency graph and the (a)/(b) answers are the same in v6.18.55, with these differences against the first draft of this note:

- **CPG MSTOP.** v6.18.55 clears/sets MSTOP on every module-clock enable/disable and runs an MSTOP pass at probe from the CLK_MON values (drivers/clk/renesas/rzg2l-cpg.c:1238-1292, 1477-1496, 1924). In v6.18 the CPG requirement for (b) therefore also includes an MSTOP register file that accepts these writes; see `cpg-reset.md` "Newer mainline". The CPG probe is `platform_driver_probe` there too (drivers/clk/renesas/rzg2l-cpg.c:2001-2006).
- **Kconfig and defconfig.** `ARCH_R9A07G054` is default-y under `ARCH_RENESAS` (drivers/soc/renesas/Kconfig:54-58, 376-381); defconfig line numbers differ (e.g. `CONFIG_SERIAL_SH_SCI` at arch/arm64/configs/defconfig:503, `CONFIG_RENESAS_OSTM` at :1466).
- **Line numbers of the same steps.** Earlycon at arch/arm64/kernel/setup.c:339 and arch/arm64/kernel/acpi.c:231-233; `renesas_soc_init` at drivers/soc/renesas/renesas-soc.c:455-553; deferred-probe enable at drivers/base/dd.c:176-179, 344-375; fw_devlink at drivers/base/core.c:1085-1089, 1145-1165, 1809-1840; pinctrl defer at drivers/pinctrl/devicetree.c:126-160; sh-sci probe at drivers/tty/serial/sh-sci.c:3674-3760; `OF_EARLYCON_DECLARE` at :3929-3931; genpd attach at drivers/pmdomain/core.c:3196-3200.
- **IRQC** uses `devm_reset_control_get_exclusive_deasserted` (drivers/irqchip/irq-renesas-rzg2l.c:561); same CPG effect.
- **RIIC** polls bus-busy with `readb_poll_timeout` (drivers/i2c/busses/i2c-riic.c:156) where v6.12.59 fails at once.
- **SCIF0 interrupts.** The v6.18 text listed SPIs 380–384; v6.12.59's node lists six entries (380, 382, 383, 381, 384, 384), same lines in substance.
- **OSTM** platform fallback no longer behind `CONFIG_ARCH_RZG2L || CONFIG_ARCH_R9A09G057`; same behaviour on V2L.
- **earlycon.c** adds a `console=` early-param alias; it has no effect for `console=ttySC0` (`scif.md` "Newer mainline").

## Claims to verify

1. PFC and SCIF0 probe only at `late_initcall`, after IRQC (device_initcall). Evidence: dd.c:175-178,344-375; pinctrl-rzg2l.c:2580-2587; EVK `dmesg` order of the pinctrl, IRQC and ttySC0 lines (Q-B1; the 2026-10-08 capture has only the ttySC0 line, at 0.594 s).
2. `earlycon=scif,0x1004b800` selects the SH4 `"renesas,scif"` entry. Evidence: earlycon.c:183-221 and sh-sci.c:3772-3779. Confirm by running it in M3a (expect garbage or a hang).
3. An unmapped MMIO access during a built-in probe panics the G0 kernel. Evidence: spec §7 mapping table; confirm with a deliberate M1 experiment (EXP record).
4. IRQC probe performs no IA55 register access. Evidence: irq-renesas-rzg2l.c:531-614; confirm with `-d unimp` / trace in M3b.
5. SCIF0 is reprobed before RIIC, ravb and SDHI in the deferred flush. Evidence: INFERENCE from link order; Q-B1.
6. With no `-append`, an initramfs `/init` overrides `root=/dev/nfs`. Evidence: main.c:162,1603-1605; confirm in the M3b run.
7. A CLK_MON mismatch on the SCIF0 clock does not stop ttySC0 output under QEMU (`clk_prepare_enable` result ignored). Evidence: sh-sci.c:592; rzg2l-cpg.c:1239-1242; mutation test in the M3b qtest/acceptance.
8. A same-polarity RSTMON mirror fails the SCIF0 probe with `failed to deassert reset`. Evidence: sh-sci.c:3363-3367; rzg2l-cpg.c:1480-1481; mutation test in the M3b CPG qtest.
9. **G1 only:** the bare `earlycon` path skips `acpi_boot_table_init` because ACPI is off. Evidence: rz_linux-cip 212f6e88b7 arch/arm64/configs/defconfig (no `CONFIG_ACPI`), earlycon.c:235-241; confirm against the G1 `.config`.

### Answered by the EVK boot log (2026-10-08, post-Linux, G1-based downstream image)

- **`renesas_soc_init` reads 0x11020A04 and the value matches.** `Detected Renesas RZ/V2L r9a07g054 Rev 1`, no `SoC mismatch`; BL2 prints `SYS_LSI_DEVID = 0x18447447` on every archived boot. (Was claim 3 and Q-B2.)
- **OSTM1 becomes `sched_clock`** at 100 MHz: `sched_clock: 32 bits at 100MHz`, `/soc/timer@12801400: used for clocksource`. (Was claim 5 and Q-B3.)
- **Bare `earlycon` resolves to SCIF0 via `stdout-path`** on silicon. (Was implied in §3.1.)
- **The real console probes early.** ttySC0 at 0.594 s, then `printk: legacy console [ttySC0] enabled`; the unused-clock sweep follows at 3.0 s. (Was Q-B1 in part.)
- **The EVK image's command line carries a bare `earlycon`.** (Was Q-B6 in part; the exact `/proc/cmdline` is still worth recording.)

## Questions for the EVK

All are read-only.

- **Q-B1** (post-Linux, remainder): full `dmesg` with `initcall_debug` *not* set. Record the relative order and timestamps of `rzg2l-cpg`, `rzg2l-irqc`, `pinctrl-rzg2l … support registered`, `bootconsole … disabled`, and the RIIC, ravb and SDHI lines, relative to the known `1004b800.serial: ttySC0` line. Also `cat /sys/kernel/debug/devices_deferred` if debugfs is mounted.
- **Q-B4** (U-Boot, immediately before `bootm`): the SCIF0 post-firmware state earlycon inherits. Run EVK-R20–R26 in `../evidence/requests.md` (documented widths; FTDR and FRDR are never read).
- **Q-B5** (U-Boot): CPG `CLK_ON`/`CLK_MON` for SCIF0, GPIO, IA55, OSTM1/2 and WDT0, and `RST`/`RSTMON` for the same modules, plus MSTOP. Shared with `cpg-reset.md` questions 3-5.
- **Q-B6** (post-Linux, remainder): `cat /proc/cmdline` and `zcat /proc/config.gz | grep -E 'CONFIG_ACPI=|SPCR'` on the EVK image, to record the exact boot arguments and which earlycon path that kernel takes.

## Verification

| Claim | Result | Evidence |
|---|---|---|
| OSTM1/2 are enabled in DTB-U, and the first one probed becomes clocksource and `sched_clock` | **Confirmed**; now also **OBSERVED** | linux v6.12.59 `rzg2l-smarc-som.dtsi:167-173` (`&ostm1`/`&ostm2` `status = "okay"`); `drivers/clocksource/renesas-ostm.c:198-204` (first device → `ostm_init_clksrc` + `ostm_init_sched_clock`), `:82` `sched_clock_register(..., 32, rate)`. EVK boot log: `sched_clock: 32 bits at 100MHz`, `/soc/timer@12801400: used for clocksource`, so OSTM beats the 24 MHz arch timer on silicon. |
| `ostm_timer_stop` spins on TE with no timeout | **Confirmed** | linux v6.12.59 `renesas-ostm.c:46-59`: `while (readb(... OSTM_TE) & TE);`. An OSTM model must clear TE when TT is written; a stub that latches TE hangs the boot. |
| A CPG probe failure is permanent | **Confirmed** | linux v6.12.59 `drivers/clk/renesas/rzg2l-cpg.c:1946` `platform_driver_probe(...)`; `drivers/base/platform.c:935, 1410-1411` (`prevent_deferred_probe`): no deferred retry. The same holds for the OSTM platform probe (`renesas-ostm.c:248`). |
| SCIF defers forever without pinctrl | **Confirmed** (see pinctrl.md verification) | linux v6.12.59 `drivers/pinctrl/devicetree.c:123-136` with `CONFIG_MODULES=y` (`arch/arm64/configs/defconfig:120`) |
| QEMU GIC identity is hard-coded | **Confirmed** | qemu v11.1.2 `hw/intc/gicv3_internal.h:749-757` `gicv3_iidr()` returns `0x43b`. The M1 "GIC ID equals EVK" check needs a new property or a recorded gap. |
| SYSC DEVID is read at early_initcall and matches on silicon | **Confirmed**; **OBSERVED** | linux v6.12.59 `drivers/soc/renesas/renesas-soc.c:497-551, 572`; EVK boot log `Detected Renesas RZ/V2L r9a07g054 Rev 1`, BL2 `SYS_LSI_DEVID = 0x18447447` |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7` (same DT apart from QSPI partitions; driver-core, earlycon, OSTM, IRQC files identical; one-line `sh-sci.c` and 5-line `rzg2l-cpg.c` deltas without effect; G1 defconfig has no ACPI and builds many more drivers in). Corrections against the first draft: no MSTOP in the CPG requirement; RSTMON stated as the inverted mirror and CLK_MON as the same-polarity mirror; `pinctrl_bind_pins` runs before the genpd attach; the OSTM `time_init` attempt defers silently and its platform probe is one-shot; SCIF0 has six interrupt entries; RIIC fails fast on bus-busy; `ARCH_R9A07G054` comes from the defconfig. EVK boot-log evidence folded into §1, §3, §4, §5 and §6; claims 3 and 5 and Q-B2/Q-B3 moved to "Answered". v6.18.55 differences kept under "Newer mainline". |
