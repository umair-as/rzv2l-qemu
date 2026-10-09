# EVK measurement requests: post-firmware register state (M1-M3b)

**Date:** 2026-10-08. **Status:** open; no result recorded yet.
**Purpose:** fix the direct-mode start state (spec §9) and the ID registers M1 asserts (spec §17). Each row states its question before measuring (spec §14). Rows collect the "Questions for the EVK" in `docs/research/` that a read-only session can answer; `docs/device-map.md` §3 refers to these IDs.

**Session rules**
- **Board:** RZ/V2L SMARC EVK, 2 GB. Record the TF-A, U-Boot and OP-TEE build IDs (the BL2/U-Boot banners) and the boot-mode switch setting in the capture.
- **Boot stage:** U-Boot prompt, **post-firmware, before `bootm`**. Interrupt autoboot with a key press, then run the commands in table order. Do not run `boot`, `bootm`, `mmc` or any command that probes hardware before section 1 is finished.
- **Read-only.** Only `md.l` / `md.w` / `md.b`. No `mw`, `nm`, `mm`, `cp`, `i2c`, `sf` or `wdt` commands (AGENTS.md "Hardware oracle").
- **U-Boot counts are hexadecimal.** Every count below is written with `0x` or is a single digit, so it reads the same either way.
- **Excluded reads (side effects or no meaning):** SCIF `FRDR` (`+0x0A`, pops the RX FIFO) and `FTDR` (`+0x06`, write-only per §22.2.4); GIC `ICC_*`/IAR (acknowledge). Sections 1.1–1.6 read **only documented registers**, none with a documented read side effect. SCIF FSR/LSR flags are "read 1, then write 0" to clear: a read only arms the clear and changes nothing because nothing is written. Counters (WDTTIM, SYC CNTCV) change between reads; that is expected.
- **Abort risk and unknown effects.** Reads of undefined addresses, register holes and possibly secure-only blocks are grouped in section 1.7 and run last; their read effects are unknown. A synchronous abort makes U-Boot print a register dump and reset. That is still an answer: record it, and resume after the failing row.
- **Results:** paste the verbatim `md` output into the Result column (or attach the console log under `docs/evidence/` and reference it).

## 1. U-Boot prompt (post-firmware)

### 1.1 SYSC (`0x11020000`)

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R01 | `md.l 0x11020a00 3` | SYS_LSI_MODE, SYS_LSI_DEVID, SYS_LSI_PRR | Do the latched IDs read the same at the U-Boot stage as in BL2 output? | MODE `0x000102xx` or `0x000100xx` per switches (bit 16 = 1); DEVID `0x18447447`; PRR `0x00000000` | none | sysc.md Q1; cpu-gic.md §7 | |
| EVK-R02 | `md.l 0x11020858 4` | RVAL0, RVAH0, RVAL1, RVAH1 | Did firmware change the CA55 reset vectors before any CPU_ON? | `0x00000000`, `0`, `0x00020000`, `0` (reset values) | none | sysc.md Q2 | |
| EVK-R03 | `md.l 0x11020d04 2; md.l 0x11020d14 3; md.l 0x11020d24 1; md.l 0x11020d38 3; md.l 0x11020d50 1` | documented low-power registers only: LP_CTL1/2 (`0xD04/0xD08`), LP_CTL5/6/7 (`0xD14-0xD1C`), LP_CM33CTL0 (`0xD24`), LP_CA55CK_CTL1-3 (`0xD38-0xD40`), LP_GPU_CTL (`0xD50`) (Table 6.1 p.168) | Low-power and CA55 clock-control state left by firmware (CPU_OFF ack bit 8+core in LP_CTL5) | mostly reset values (Table 6.1); LP_CTL5 bits 8-9 `0` before any CPU_OFF | none documented | sysc.md Q3 | |
| EVK-R04 | `md.l 0x11020000 6` | SYS_MSTACCCTL0-5 | Bus-master security attributes as left by firmware | reset `0x00AAAA00`, `0xAAAAAAAA`, … unless BL2 changed them | none | sysc.md Q4 | |
| EVK-R05 | `md.l 0x11020100 0xf` | SYS_SLVACCCTL0-14 | Slave access-control as left by firmware (gap 9 of the device map) | reset `0x0AAAAAA0`, `0x0800C0AA`, `0x2`, `0` … unless changed | none | sysc.md Q4 | |

### 1.2 CPG (`0x11010000`)

The `CLK_ON; CLK_MON; RST; RSTMON` rows test the two mirror rules: CLK_MON = CLK_ON (same polarity) and RSTMON = ~RST & mask (inverted).

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R10 | `md.l 0x11010000 4; md.l 0x11010040 4` | SAMPLL1_STBY/CLK1/CLK2/MON; PLL1_SETTING, OTPPLL0-2_MON | Is PLL1 OTP-driven, and do CLK1/CLK2 still give 1200 MHz? | `0x5`, `0x00001901`, `0x00180601`, `0x11`; SEL_PLL1 `0x1`; OTPPLL undefined | none | cpg-reset.md Q1 | |
| EVK-R11 | `md.l 0x11010200 8; md.l 0x11010280 1; md.l 0x11010408 5` | PL1/PL2/PL3A/PL6 DDIV, PL3C_SDIV `0x214`, PL2SDHI_DSEL `0x218`; CLKSTATUS; PL3/PL6/PL6_ETH selectors | Divider and mux values left by firmware (P0 = 100 MHz? PL3C_SDIV still `0x401`?) | DDIVs `0`; `0x214` = `0x401`; `0x218` = `0x11`; CLKSTATUS `0`; `0x408` = `0x111`, `0x414` = `0x101`, `0x418` = `0x10` | none | cpg-reset.md Q2 | |
| EVK-R12 | `md.l 0x11010514 2; md.l 0x11010694 2; md.l 0x11010814 2; md.l 0x11010994 2` | GIC600 + IA55: CLK_ON, CLK_MON, RST, RSTMON | Are the GIC and IRQC clocks/resets at reset values? | `0x1 0x3` / `0x1 0x3` / `0x3 0x1` / `0x0 0x0` | none | cpg-reset.md §5; boot-dependency-graph.md Q-B5 | |
| EVK-R13 | `md.l 0x11010584 1; md.l 0x11010704 1; md.l 0x11010884 1; md.l 0x11010a04 1` | SCIF: CLK_ON, CLK_MON, RST, RSTMON | Is SCIF0 clocked and out of reset after firmware? Is SCIF1 clocked (gates EVK-R27)? | b0 = 1 / b0 = 1 / b0 = 1 / `0x1E` (if only SCIF0) | none | cpg-reset.md §5; scif.md Q2; boot-dependency-graph.md Q-B5 | |
| EVK-R14 | `md.l 0x11010598 1; md.l 0x11010718 1; md.l 0x11010898 1; md.l 0x11010a18 1` | GPIO: CLK_ON, CLK_MON, RST, RSTMON | Are the GPIO resets released (Linux never deasserts them)? | `0x1` / `0x1` / `0x7` / `0x0` | none | cpg-reset.md claim 4 | |
| EVK-R15 | `md.l 0x11010534 1; md.l 0x110106b4 1; md.l 0x11010834 1; md.l 0x110109b4 1` | GTM (OSTM0-2): CLK_ON, CLK_MON, RST, RSTMON | OSTM clock/reset state Linux inherits | reset: `0x1` / `0x1` / `0x1` / `0x6` | none | cpg-reset.md §5 | |
| EVK-R16 | `md.l 0x11010548 1; md.l 0x110106c8 1; md.l 0x11010848 1; md.l 0x110109c8 1` | WDT: CLK_ON, CLK_MON, RST, RSTMON | WDT0/1 clock and reset state (reserved read-as-1 bits) | `0xC3` / `0xC3` / `0x9` / `0x6` | none | cpg-reset.md §5 | |
| EVK-R17 | `md.l 0x11010554 1; md.l 0x110106d4 1; md.l 0x11010854 1; md.l 0x110109d4 1` | SDHI: CLK_ON, CLK_MON, RST, RSTMON | Did U-Boot's mmc0 leave SDHI0 clocked and released? | `0x0F` / `0x0F` / `0x1` / `0x2` (I) | none | cpg-reset.md §5 | |
| EVK-R18 | `md.l 0x11010528 1; md.l 0x110106a8 1; md.l 0x11010828 1; md.l 0x110109a8 1` | SYC: CLK_ON, CLK_MON, RST, RSTMON | Did firmware ungate SYC and release its reset? | `0x1` / `0x1` / `0x1` / `0x0` (I) | none | sysc.md Q6 | |
| EVK-R19 | `md.l 0x11010b60 0xb` | MSTOP `0xB60-0xB88` | MSTOP values left by firmware (G0/G1 never write them) | unknown; reset all `0` | none | cpg-reset.md Q5 | |
| EVK-R72 | `md.l 0x110105e8 1; md.l 0x11010768 1; md.l 0x110108e8 1; md.l 0x11010a68 1; md.l 0x11010214 1` | DRP-AI: CLK_ON, CLK_MON, RST, RSTMON; PL3C_SDIV (`0x214`) | G1-only clocks (cpg-reset.md G1 delta): the post-firmware state, the inverted RSTMON on a second module, and the `DRP_A` divider value G1 reads at probe | RSTMON_DRP reset `0x1`; PL3C_SDIV `0x401` unless changed | none documented | cpg-reset.md (G1 delta) | |

### 1.3 SCIF0 (`0x1004B800`) and SCIF1

Never read `0x1004b806` (FTDR) or `0x1004b80a` (FRDR). U-Boot keeps printing on SCIF0 while these run, so FSR may show TEND = 0 if the echo is still draining: repeat EVK-R23 once if so.

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R20 | `md.w 0x1004b800 1` | SMR | Framing left by firmware | `0x0000` | none | scif.md Q1; boot-dependency-graph.md Q-B4 | |
| EVK-R21 | `md.b 0x1004b802 1` | BRR/MDDR (MDDR visible while SEMR.MDDRS = 1) | Did U-Boot's divisor write land on MDDR and get ignored (claim 2)? | `0xFE` (MDDR); BRR `0x1A` stays hidden | none | scif.md Q1, claim 2 | |
| EVK-R22 | `md.w 0x1004b804 1` | SCR | TE/RE enabled, no interrupt enables | `0x0030` | none | scif.md Q1 | |
| EVK-R23 | `md.w 0x1004b808 1` | FSR | Idle status flags | `0x0060` (TDFE\|TEND) | arms a clear only; nothing written | scif.md Q1 | |
| EVK-R24 | `md.w 0x1004b80c 4` | FCR, FDR, SPTR, LSR | FIFO control, counts, pin-control state | `0x0000`, `0x0000`, `0x00xx`, `0x0000` | none (LSR as FSR) | scif.md Q1 | |
| EVK-R25 | `md.b 0x1004b814 1` | SEMR | TF-A leaves MDDRS\|BRME (claim 3) | `0x30` | none | scif.md Q1, claim 3 | |
| EVK-R26 | `md.w 0x1004b816 1` | FTCR | Trigger-control state | `0x1F1F` | none | scif.md Q1 | |
| EVK-R27 | `md.w 0x1004bc08 1` (**only if EVK-R13 shows CLK_MON SCIF b1 = 1**) | SCIF1 FSR | Reset value of an untouched channel (claim 1) | `0x0020` | none | scif.md Q2 | |

### 1.4 PFC (`0x11030000`)

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R30 | `md.b 0x11030236 1; md.l 0x110304d8 1; md.w 0x1103016c 1` | PMC36, PFC36, PM36 (P38 = SCIF0 TXD/RXD) | Is SCIF0's pin function selected exactly as TF-A's table says? | `0x03`, `0x00000011`, `0x0000` | none | pinctrl.md Q1 | |
| EVK-R31 | `md.b 0x11033014 1` | PWPR | Is the PFC write gate relocked? | `0x80` | none | pinctrl.md Q1 | |
| EVK-R32 | `md.b 0x1103023f 1; md.l 0x110304fc 1; md.b 0x11030223 1; md.l 0x1103048c 1` | PMC3F/PFC3F (P47, SD0), PMC23/PFC23 (P19, SD1) | Does the V2L TF-A build also mux P47 and P19 (claim 3)? | `0x03`, `0x00000011`, `0x03`, `0x00000011` | none | pinctrl.md Q1, claim 3 | |
| EVK-R33 | `md.b 0x11033000 1; md.b 0x11033004 1; md.b 0x11033008 1` | SD_ch0, SD_ch1, QSPI power-source registers | Anchor the TF-A SD/QSPI overlay values | `0x01`, `0x00`, unknown | none | pinctrl.md Q3 | |
| EVK-R34 | `md.b 0x11033018 1` | ETH MII/RGMII (OEN) | Does firmware leave it at reset? | `0x03` | none | pinctrl.md Q3, claim 6 | |
| EVK-R35 | `md.l 0x11031820 1` | IEN04 | Value before the Linux `sound_clk` hog | `0x00000000` | none | pinctrl.md Q2 | |
| EVK-R36 | `md.b 0x11030240 1; md.l 0x11030500 1` | PMC40, PFC40 (P48 = SCIF2 pins in DTB-U) | Are SCIF2's pins untouched by firmware (direct-mode overlay)? | `0x00`, `0x00000000` | none | pinctrl.md §4 | |

### 1.5 WDT0 (`0x12800800`)

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R40 | `md.l 0x12800800 4` | WDTCNT, WDTSET, WDTTIM, WDTINT (Table 21.4 p.1246) | Is WDT0 running at the U-Boot prompt (spec §9 "WDT0 running, if a U-Boot path is mimicked")? Repeat once to see WDTTIM move | WDTCNT b0 = 1 if U-Boot autostarted it; WDTSET for about 60 s | none (WDTTIM counts) | boot-chain-firmware.md §1; spec §11 | |

### 1.6 GIC-600

U-Boot runs at NS-EL1, so GICD_CTLR shows its non-secure view.

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-R60 | `md.l 0x11900000 4` | GICD_CTLR, GICD_TYPER, GICD_IIDR, GICD_TYPER2 | Silicon IIDR (decision D3), TYPER fields QEMU must match | CTLR (NS) `0x00000012` (I); TYPER ITLinesNumber `0xF`, SecurityExtn = 1, LPIS = 0; IIDR `0x0201643B` (A) | none | cpu-gic.md Q1, claims 1-2 | |
| EVK-R61 | `md.l 0x1190ffd0 0xc` | GICD PIDR4-7, PIDR0-3, CIDR0-3 | GIC-600 product ID and ArchRev | PIDR2 bits [7:4] = 3; CIDR `0x0D 0xF0 0x05 0xB1` | none | cpu-gic.md Q1 | |
| EVK-R62 | `md.l 0x11940000 4` | GICR0 CTLR, IIDR, TYPER (lo, hi) | Redistributor 0 identity and affinity | TYPER hi `0x00000000`, Last = 0 | none | cpu-gic.md Q1 | |
| EVK-R63 | `md.l 0x11960000 4` | GICR1 CTLR, IIDR, TYPER (lo, hi) | Redistributor 1 affinity and Last bit | TYPER hi `0x00000100`, Last (b4) = 1, processor number 1 (I) | none | cpu-gic.md Q1 | |
| EVK-R64 | `md.l 0x11940014 1; md.l 0x11960014 1` | GICR0/GICR1 WAKER | Redistributor power state with CPU1 still off | CPU0 `0x0` (awake); CPU1 `0x6` (asleep) (I) | none | cpu-gic.md Q1 | |
| EVK-R65 | `md.l 0x1194ffd0 0xc` | GICR0 PIDR4-7, PIDR0-3, CIDR0-3 (RD_base frame) | Redistributor 0 identity block for DR-0003 option A, incl. the PIDR2 ArchRev Linux checks | PIDR2 bits [7:4] = 3; CIDR `0x0D 0xF0 0x05 0xB1` | none | cpu-gic.md Q1; DR-0003 | |
| EVK-R66 | `md.l 0x1196ffd0 0xc` | GICR1 PIDR4-7, PIDR0-3, CIDR0-3 (RD_base frame) | Redistributor 1 identity block; asserted separately, not inferred from GICR0 | as EVK-R65 | none | DR-0003 | |

### 1.7 Last: experimental reads (undefined addresses, register holes, possibly secure-only blocks)

These rows deliberately touch addresses whose read behaviour is **not documented**: undefined offsets, sweeps across register holes, and blocks that may be secure-only. Their read effect is unknown. Run them only after sections 1.1–1.6 are captured, one at a time, and record any abort as a result. They answer questions about how the model should treat undefined accesses; they are not part of the documented-register capture.

| ID | Command | Register / meaning | Question it answers | Expected / predicted | Read effect | Source note | Result |
|---|---|---|---|---|---|---|---|
| EVK-X01 | `md.l 0x11010500 0x60; md.l 0x11010680 0x60` | all CLK_ON (`0x500-0x67F`) and CLK_MON (`0x680-0x7FF`); includes holes | Is CLK_MON equal to CLK_ON bit for bit for every module, including CLKON_DRP `0x5E8`? | CLK_MON word n == CLK_ON word n | **unknown** (undocumented holes) | the range includes undocumented holes | |
| EVK-X02 | `md.l 0x11010800 0x60; md.l 0x11010980 0x60` | all RST (`0x800-0x97F`) and RSTMON (`0x980-0xAFF`) | Is RSTMON = ~RST & implemented mask everywhere (SCIF, GPIO, SYC, SDHI, DRP `0x8E8/0xA68`)? | inverted pairs | **unknown** (undocumented holes) | the range includes undocumented holes | |
| EVK-R50 | `md.l 0x11000000 0x10` | SYC control frame: CNTCR, CNTSR, CNTCV, CNTFID0 (`+0x20`, inferred) | Where CNTFID0 lives and whether the counter is enabled. May abort if SYC is secure-only | CNTCR b0 = 1; `+0x20` = `0x016E3600` (24 MHz) (I) | **unknown** (block may be secure-only; CNTCV counts) | sysc.md Q5, claim 2 | |
| EVK-R51 | `md.l 0x11001000 4` | SYC read frame | Does the read-only frame mirror CNTCV? | CNTCV low/high, advancing | **unknown** (block may be secure-only) | sysc.md Q5 | |
| EVK-R70 | `md.w 0x1004b818 1` | SCIF0 undefined offset | Zero, bus error or alias? Decides the model's undefined-offset behaviour | `0x0000` or abort | unknown | scif.md Q4 | |
| EVK-R71 | `md.l 0x11033100 1` | PFC undefined offset | Same question for the PFC | `0x00000000` or abort | unknown | pinctrl.md Q4 | |

## 2. Optional: Linux side (post-Linux, read-only)

**Boot stage:** post-Linux. These values are neither the reset state nor the post-firmware state. Record the image and kernel build ID. A downstream image carries its own DT, so DT-level answers apply to that image only. Rows marked `/dev/mem` need a project-owned G1 debug image with `devmem`.

| ID | Command | Question it answers | Expected / predicted | Source note | Result |
|---|---|---|---|---|---|
| EVK-L01 | `dmesg \| grep -E 'rzg2l-cpg\|irqc\|pinctrl\|ttySC\|bootconsole\|riic\|ravb\|renesas_sdhi\|mmc'` | Probe order of CPG, IRQC, pinctrl and ttySC0 versus RIIC, ravb and SDHI (claim 1, claim 5) | IRQC before pinctrl before ttySC0 (`0.594 s`) | boot-dependency-graph.md Q-B1 | |
| EVK-L02 | `cat /sys/kernel/debug/devices_deferred` | Which devices are still deferred after boot | empty, or only devices without hardware | boot-dependency-graph.md Q-B1 | |
| EVK-L03 | `cat /proc/cmdline; zcat /proc/config.gz \| grep -E 'CONFIG_ACPI=\|SPCR\|SERIAL_SH_SCI'` | Exact boot arguments and which earlycon path the kernel takes | bare `earlycon` present; G1 has no `CONFIG_ACPI` | boot-dependency-graph.md Q-B6; scif.md Q5 | |
| EVK-L04 | `dmesg \| grep -E 'Detected Renesas\|SoC mismatch'` | DEVID decode by Linux | `Detected Renesas RZ/V2L r9a07g054 Rev 1` | sysc.md Q7 | |
| EVK-L05 | `grep . /sys/devices/system/cpu/cpu0/cache/index*/{level,type,size}; grep -m1 Features /proc/cpuinfo` | Cache topology on silicon (no L2, 256 KiB L3?) and crypto extension | L1 I/D 32K; L3 256K; `aes pmull sha1 sha2` (A) | cpu-gic.md Q2 | |
| EVK-L06 | `cat /sys/devices/system/clocksource/clocksource0/{current,available}_clocksource; grep -E 'arch_timer\|ostm' /proc/interrupts` | Which clocksource wins; timer IRQ counts | `arch_sys_counter` current (rating 400 > OSTM 300) | cpu-gic.md Q4 | |
| EVK-L07 | `dmesg \| grep -iE 'trusted os\|migrat\|smccc\|psci'; cat /sys/devices/system/cpu/vulnerabilities/*` | MIGRATE_INFO_TYPE with opteed (gap 5); SMCCC-dependent mitigations (gap 1) | open | cpu-gic.md Q5 | |
| EVK-L08 | `grep -E '1004b800\|1004c000\|sci' /proc/interrupts` | Which SCIF SPIs (380-384, 390-394) are requested and counting (IRQ-sharing conflict) | 380, 381, 382, 383, 384 (one handler on 384) | scif.md Q3, conflict 1 | |
| EVK-L09 | `grep -E 'P38\|P48' /sys/kernel/debug/pinctrl/11030000.pinctrl-pinctrl-rzg2l/pinmux-pins; ls /proc/device-tree/soc/serial@1004b800/` | SCIF0/SCIF2 pin ownership; does this image's `scif0` node have `pinctrl-0`? | P38_0/P38_1 owned by `1004b800.serial` | pinctrl.md Q5 | |
| EVK-L10 | `cat /sys/kernel/debug/clk/clk_summary` | What the unused-clock sweep left on | SCIF0, GPIO, IA55, GIC, DMAC on | cpg-reset.md Q6 | |
| EVK-L11 | `dtc -I fs /sys/firmware/devicetree/base > live.dts` | Live-DT baseline for the spec §8 diff against the QEMU guest | — | spec §8 | |
| EVK-L12 | `/dev/mem`: `devmem 0x1004b80c 16; devmem 0x1004b804 16; devmem 0x1004b814 8; devmem 0x11031820 32` | Post-Linux SCIF0 FCR/SCR/SEMR and IEN04 | FCR `0x0080`; SCR `0x0070` or `0x00F0`; SEMR `0x00`; IEN04 `0x00000101` | scif.md Q3; pinctrl.md Q2 | |
| EVK-L13 | `/dev/mem`: `devmem` reads of CPG `0x11010500-0x110107FF`, `0x11010800-0x11010AFF`, `0x11010B60-0x11010B88` | What Linux changed versus EVK-R08/R09/R19; is MSTOP untouched (claim 9)? (**ranges include undocumented holes: read effect unknown; optional, run last**) | MSTOP equals EVK-R19 | cpg-reset.md Q6 | |
