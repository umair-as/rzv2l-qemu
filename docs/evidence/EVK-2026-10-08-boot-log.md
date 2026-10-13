# EVK boot log observations — 2026-10-08

**Board:** RZ/V2L SMARC EVK (2 GB variant).
**Firmware:** TF-A BL31 v2.10.5 (Renesas `rz_1.1.0`), U-Boot 2024.07, OP-TEE.
**Kernel:** 6.12.59-cip14, a downstream image built on the G1 base (`rz-6.12-cip14`) with additional downstream patches. SoC- and firmware-level facts transfer to G0 and G1; DT-level facts (which devices are enabled) belong to that image.
**Boot stage:** U-Boot console output + Linux dmesg (post-Linux).
**Method:** passive serial capture at 115200 8N1; no register access.
**Provenance:** the image was not built by this project. The raw captures and their SHA-256 are kept privately by the operator; every excerpt below was re-checked verbatim against its capture on 2026-10-13 (each excerpt searched for as a fixed string in the capture). To be replaced by measurements on a project-built image.

| Observation (verbatim excerpt) | Answers |
|---|---|
| `earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')`, with a bare `earlycon` on the kernel command line | A bare `earlycon` resolves via `stdout-path` to SCIF0 on silicon (scif.md, boot-dependency-graph.md) |
| `psci: PSCIv1.1 detected in firmware.` / `SMC Calling Convention v1.4` | The PSCI version a Stage B model must report (cpu-gic.md) |
| `GICv3: 480 SPIs implemented`, `16 PPIs`, `GICD_CTRL.DS=0, SCR_EL3.FIQ=1` | GIC sizing; security extensions on; TF-A sets SCR_EL3.FIQ=1, a known QEMU direct-boot gap (cpu-gic.md) |
| `CPU0: found redistributor 0 region 0:0x0000000011940000`, `CPU1: found redistributor 100 region 0:0x0000000011960000` | Redistributor base and 0x20000 stride; CPU1 MPIDR 0x100 |
| `arch_timer: cp15 timer(s) running at 24.00MHz (virt).` | CNTFRQ = 24 MHz; Linux uses the virtual timer (REQ-MACH-003) |
| `Booting Linux on physical CPU 0x0000000000 [0x412fd050]`, `CPU1: Booted secondary processor 0x0000000100 [0x412fd050]` | MIDR 0x412FD050 (Cortex-A55 r2p0), identical to QEMU's cortex-a55 default (EXP-001) |
| `CPU: All CPU(s) started at EL1` | NS-EL1 entry (REQ-MACH-004) |
| `Detected Renesas RZ/V2L r9a07g054 Rev 1` | SYS_LSI_DEVID bits [27:0] match `0x8447447` (no mismatch warning) and DEV_ID[31:28] = 1, so the register most likely reads `0x18447447`; confirm with `md.l 0x11020a04 1` (sysc.md) |
| `clocksource: timer@12801400 ...` / `sched_clock: 32 bits at 100MHz, resolution 10ns` / `/soc/timer@12801400: used for clocksource` / `/soc/timer@12801800: used for clock events` | OSTM1 takes over `sched_clock` from the 24 MHz arch timer, and the OSTM clock (P0) is 100 MHz. Confirms both boot-dependency-graph.md claims and the P0 rate in cpg-reset.md |
| `1004b800.serial: ttySC0 at MMIO 0x1004b800 (irq = 38, base_baud = 0) is a scif` at 0.594 s, then `printk: legacy console [ttySC0] enabled` | The real console probes about 0.6 s into boot; the log buffer is replayed on handover |
| `1004c000.serial: ttySC1 at MMIO 0x1004c000 (irq = 43, base_baud = 0) is a scif` at 2.34 s | A second SCIF (SCIF1) probes in this image; that image's DT is downstream, so this says nothing about which SCIFs DTB-U enables |
| `clk: Disabling unused clocks` at 3.0 s | The unused-clock sweep runs; clocks not claimed by a driver are gated (cpg-reset.md) |

## SYSC identification registers printed by BL2 (archived EVK boot logs, 150 BL2 printouts, June–October 2026)

TF-A BL2 prints three SYSC registers on every boot (TF-A `plat/renesas/rz/common/bl2_plat_setup.c:238-240` @ `f59ed5a31`). **Boot stage:** BL2, after DDR init.

| Register | Values seen | Decode (HW manual Rev 1.50) |
|---|---|---|
| `SYS_LSI_DEVID` (0x11020A04) | `0x18447447`, on every boot | DEV_ID[31:28] = 1 (revision 1); DEV_ID[27:0] = `0x8447447`. **Resolves the manual conflict:** §6.3.43 p.208 is correct, and Table 6.1 p.168 (`x841_C447`) is a copy of the RZ/G2L value. |
| `SYS_LSI_PRR` (0x11020A08) | `0x00000000`, on every boot | bit 0 CA55_1CPU = 0 → dual Cortex-A55 (§6.3.44 p.209) |
| `SYS_LSI_MODE` (0x11020A00) | `0x10203` (90×), `0x10000` (35×), `0x10001` (14×), `0x10200` (10×), `0x10201` (1×) | bit 16 STAT_SEC_EN = 1 on every boot (security function available). Bit 9 = DEBUGEN pin, bits [2:0] = MD_BOOT pins (§6.3.42 p.207). MD_BOOT per Table 4.1 (§4): 0 = eSD, 1 = 1.8 V eMMC, 3 = 1.8 V serial flash (QSPI). The values track the board's boot-mode switches between sessions. |
