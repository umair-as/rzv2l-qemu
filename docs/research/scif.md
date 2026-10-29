# SCIF (SCIFA) research: what QEMU must provide for the console

**Date:** 2026-10-08 (M0 research; re-based 2026-10-08 onto the pinned guest kernels, see `docs/sources.md` "Pinned guest kernels")
**Scope:** SCIF channel 0 (the EVK debug console), with notes on channels 1 to 4. Answers the SCIF parts of spec §20 (a) and (b).

**Method:** source reading of linux v6.12.59 (G0 reference), rz_linux-cip `212f6e88b7` (branch `rz-6.12-cip14`, G1 reference), the firmware sources below and the RZ/V2L HW manual Rev 1.50, plus the passive EVK boot log `docs/evidence/EVK-2026-10-08-boot-log.md`. The first draft of this note was written against linux v6.18.55; where that kernel differs, the difference is kept in "Newer mainline (v6.18.55)" near the end.

**Sources:**

| Source | Revision | Citation form |
|---|---|---|
| Linux (G0) | v6.12.59 (`d5dc97879`) | `linux v6.12.59 <path>:<line>`, or the short form below |
| Linux (G1) | https://github.com/renesas-rz/rz_linux-cip `212f6e88b7` | `rz_linux-cip 212f6e88b7 <path>:<line>` |
| RZ/V2L HW manual | Rev 1.50 (`r01uh0936ej0150`) | `HW manual Rev 1.50 §x, Table n, p.N` (printed page numbers) |
| SMARC module / carrier UM | `r01uh0964ej0200`, `r01uh0966ej0200` | `Module UM p.N`, `Carrier UM p.N` |
| TF-A | https://github.com/renesas-rz/rzg_trusted-firmware-a `f59ed5a31` | `TF-A <path>:<line>` |
| U-Boot | https://github.com/renesas-rz/renesas-u-boot-cip `4eebfbaa4e` | `U-Boot <path>:<line>` |
| OP-TEE | https://github.com/renesas-rz/rzg_optee-os `82a5cd3b` | `OP-TEE <path>:<line>` |
| QEMU | v11.1.2 (`rzv2l-base`) | `QEMU v11.1.2 <path>:<line>` |
| EVK boot log | `docs/evidence/EVK-2026-10-08-boot-log.md` | `EVK boot log` |

**Citation key:** a short kernel citation `file:N` abbreviates `linux v6.12.59 <path>:N`:

| Short | Full path |
|---|---|
| `sh-sci.c`, `sh-sci.h`, `earlycon.c` | `drivers/tty/serial/` |
| `r9a07g054.dtsi`, `rz-smarc-common.dtsi`, `rzg2l-smarc.dtsi`, `rzg2l-smarc-som.dtsi`, `r9a07g054l2-smarc.dts` | `arch/arm64/boot/dts/renesas/` |
| `r9a07g044-cpg.c` | `drivers/clk/renesas/` |
| `fdt.c` | `drivers/of/` |

**G1 (rz-6.12-cip14) delta, whole note:** `drivers/tty/serial/sh-sci.c` differs from v6.12.59 by one changed line. `early_console_setup` copies the earlycon `uart_port` by struct assignment instead of `memcpy` (rz_linux-cip 212f6e88b7 drivers/tty/serial/sh-sci.c:3718; v6.12.59 sh-sci.c:3718). The bytes copied are the same, and no register access changes. `earlycon.c`, `fdt.c`, `r9a07g054.dtsi`, `rz-smarc-common.dtsi`, `rzg2l-smarc.dtsi` and `r9a07g054l2-smarc.dts` are identical in G0 and G1. `rzg2l-smarc-som.dtsi` differs only in the QSPI flash partition layout. Every register-level statement below therefore holds for G1 as well.

Effective configuration (§5 rule): TF-A was compiled with `-DRZG2L=1 -DRZV2L=1` (TF-A compile log of the studied build); U-Boot `.config` has `CONFIG_R9A07G054L=y`, `CONFIG_DM_SERIAL=y`, `CONFIG_RCAR_64=y`, `CONFIG_BAUDRATE=115200`. None of the firmware files cited here carry downstream changes in the studied build. For G0 only the arm64 `defconfig` has been read, not a built `.config`; see Claims to verify.

Labels: **FACT** (documented or read directly in code), **INFERENCE** (derived from code), **ASSUMPTION**, **CONFLICT** (sources disagree), **OBSERVED** (hardware observation, EVK boot log).

---

## 1. Evidence record (spec §6)

| Field | Value | Label / evidence |
|---|---|---|
| MMIO | SCIF0 `0x1004B800`, size `0x400`. SCIF1 `0x1004BC00`, SCIF2 `0x1004C000`, SCIF3 `0x1004C400`, SCIF4 `0x1004C800`, each `0x400` | FACT: HW manual Rev 1.50 §22.2, Table 22.3, p.1271; r9a07g054.dtsi:380-473 |
| Registers used | 0x00 to 0x17 (13 registers); the rest of the 1 KiB window is undefined | FACT: HW manual Rev 1.50 §22.2, Table 22.4, p.1271 |
| IRQs (SCIF0) | GIC SPI 380 ERI0, 381 BRI0, 382 RXI0, 383 TXI0, 384 TEI0_DRI0 (shared); all level-high | FACT: HW manual Rev 1.50 §8.2, Table 8.2 (11/13), p.544; r9a07g054.dtsi:384-391 |
| IRQs (SCIF1-4) | 385-389, 390-394, 395-399, 400-404, same pattern | FACT: same table; r9a07g054.dtsi:403-467 |
| Clock | `CPG_MOD R9A07G054_SCIF0_CLK_PCK` ("fck"); parent P0; CLK_ON register offset 0x584 bit 0 | FACT: r9a07g054.dtsi:392-393; r9a07g044-cpg.c:334-335. The MSTOP bit (BUS_MCPU2 bit 1) is not written by G0 or G1 on V2L; see `cpg-reset.md` §2.4 |
| P0 rate | 100 MHz | FACT (firmware): TF-A `plat/renesas/rz/common/include/rz_soc_def.h:61`; U-Boot `arch/arm/dts/smarc-rzv2l.dts:73`. OBSERVED: OSTM, also clocked from P0, runs at 100 MHz (EVK boot log, `sched_clock: 32 bits at 100MHz`). The Linux-side rate is the CPG model's job (`cpg-reset.md`) |
| Reset | `R9A07G054_SCIF0_RST_SYSTEM_N`, CPG RST offset 0x884 bit 0 | FACT: r9a07g054.dtsi:395; r9a07g044-cpg.c:415 |
| Power domain | `power-domains = <&cpg>` (CPG clock domain, runtime PM) | FACT: r9a07g054.dtsi:394 |
| DMA | No `dmas` property on any SCIF node | FACT: r9a07g054.dtsi:380-473 |
| Board use | SCIF0 on P38_0 (TXD) / P38_1 (RXD), debug UART routed to the carrier as SER3 | FACT: Module UM p.23; Carrier UM p.19 |
| DT enablement (DTB-U) | `scif0` okay (alias serial0, `stdout-path = "serial0:115200n8"`); **`scif2` also okay** (alias serial1) with `uart-has-rtscts` (because `PMOD1_SER0` is 1) | FACT: rz-smarc-common.dtsi:26, 32, 136-140; rzg2l-smarc.dtsi:13, 169-176; r9a07g054l2-smarc.dts:11 |
| Silicon | `1004b800.serial: ttySC0 at MMIO 0x1004b800 (irq = 38, base_baud = 0) is a scif` at 0.594 s; `ttySC1` at MMIO `0x1004c000` also probes in the same image | OBSERVED: EVK boot log (G1-based downstream image; its DT is downstream, so which channels are enabled is a fact about that image, not about DTB-U). The ttySC1 line is from the same capture but not yet transcribed into the evidence table. `is a scif` is the `PORT_SCIF` type string, consistent with §2 |

## 2. Linux driver selection

- **FACT.** The compatible list is `"renesas,scif-r9a07g054", "renesas,scif-r9a07g044"`. Only the second string is in `of_sci_match`. Its match data is `SCI_OF_DATA(PORT_SCIF, SCIx_RZ_SCIFA_REGTYPE)` (sh-sci.c:3280, 3294-3297); `sci_parse_dt` unpacks it into `p->type` and `p->regtype` (sh-sci.c:3397-3398), and `sci_probe_regmap` returns the RZ_SCIFA parameter set because the regtype is explicit (sh-sci.c:2950-2951).
- **FACT.** The port type is `PORT_SCIF`, **not** `PORT_SCIFA`. So every `PORT_SCIFA` branch (SCPCR/SCPDR pin control, `SCSCR_TDRQE/RDRQE`, the 16/32/48 trigger table) is dead for this SoC. The manual calls the IP "SCIFA"; Linux treats it as a SCIF with a compressed map. U-Boot instead tags the same compatible `PORT_SCIFA` (U-Boot `drivers/serial/serial_sh.c:250`). The naming differs; the register layout is the same. OBSERVED: the EVK probe line ends in `is a scif`.
- **FACT.** The RZ_SCIFA register map (sh-sci.c:318-337): SMR 0x00/16, BRR 0x02/8, SCR 0x04/16, FTDR 0x06/8, FSR 0x08/16, FRDR 0x0A/8, FCR 0x0C/16, FDR 0x0E/16, SPTR 0x10/16, LSR 0x12/16, SEMR 0x14/8. `fifosize = 16`, overrun in LSR bit 0, sampling rate fixed at 32, error mask PER|FER|BRK|ER. **FTCR (0x16) and MDDR are not in the Linux map**; Linux never touches them.
- **FACT.** Accessors use `ioread8`/`ioread16` and `iowrite8`/`iowrite16` with the declared width (sh-sci.c:556-581). Firmware accesses are the same widths (`ldrh`/`strh`/`strb`).

## 3. Register map, reset values and guest usage

Reset values are from HW manual Rev 1.50 §22.2, Table 22.4, p.1271, plus the per-register pages listed. "Class" is the behaviour QEMU must model.

| Off | Reg | W | Reset | Class | Who uses it and how |
|---|---|---|---|---|---|
| 0x00 | SMR | 16 | 0x0000 | config | Linux `set_termios` writes CHR/PE/PM/STOP + CKS (sh-sci.c:2507-2760); TF-A/U-Boot write 0. Only CM=1 (clock-sync) matters to the model: unsupported (§7). §22.2.5, p.1274 |
| 0x02 | BRR | 8 | 0xFF | config, banked | Shares the address with MDDR; SEMR.MDDRS selects. Linux writes BRR with SCR=0 (sh-sci.c:2657-2659). The manual says BRR "should" be written with TE=RE=0 (advisory). §22.2.8, p.1282 |
| 0x02 | MDDR | 8 | 0xFF | config, banked | Visible when SEMR.MDDRS=1. **Writable only when TE=RE=0**; bit 7 fixed at 1. TF-A writes it (`scifa.S:155-156`). §22.2.9, p.1287 |
| 0x04 | SCR | 16 | 0x0000 | config + IRQ enables | TIE b7, RIE b6, TE b5, RE b4, REIE b3, TEIE b2, CKE b1:0. TE=0 forces TDFE=1. §22.2.6, p.1276 |
| 0x06 | FTDR | 8 | undefined | push | Write pushes into the 16-byte TX FIFO; writes to a full FIFO are discarded. Clears TDFE and TEND. §22.2.4, p.1273 |
| 0x08 | FSR | 16 | **0x0020** | status, read-1-then-write-0 | ER b7, TEND b6, TDFE b5, BRK b4, FER b3 (RO), PER b2 (RO), RDF b1, DR b0. Bits 15:8 reserved. §22.2.7, p.1278-1281 |
| 0x0A | FRDR | 8 | undefined | pop | Read pops the RX FIFO. Reading an empty FIFO returns undefined data. §22.2.2 |
| 0x0C | FCR | 16 | 0x0000 | config + level reset | RSTRG b10:8, RTRG b7:6, TTRG b5:4, MCE b3, TFRST b2, RFRST b1, LOOP b0. TFRST/RFRST are **not** self-clearing; software must write 0. §22.2.10, p.1290-1291 |
| 0x0E | FDR | 16 | 0x0000 | derived, RO | T[4:0] b12:8 = TX FIFO count, R[4:0] b4:0 = RX FIFO count. §22.2.11, p.1292 |
| 0x10 | SPTR | 16 | 0x00xx | config + pin state | RTS2IO/RTS2DT/CTS2IO/CTS2DT/SCKIO/SCKDT/SPB2IO/SPB2DT. Even bits read pin levels (undefined at reset). §22.2.12, p.1293 |
| 0x12 | LSR | 16 | 0x0000 | status | ORER b0 (read-1-then-write-0), FER[3:0] b5:2 and PER[3:0] b11:8 error counts (RO). §22.2.13, p.1296 |
| 0x14 | SEMR | 8 | 0x00 | config | BGDM b7, BRME b5, MDDRS b4, DIR b3, NFEN b2, ABCS0 b0. Linux writes 0 (sh-sci.c:2641-2642). §22.2.14, p.1297 |
| 0x16 | FTCR | 16 | 0x1F1F | config | RTRGS b15, RFTC b12:8, TTRGS b7, TFTC b4:0. When TTRGS/RTRGS=1 these override FCR triggers. TF-A clears both select bits (`scifa.S:164-167`). §22.2.15, p.1299 |

### 3.1 FSR flag semantics (load-bearing)

- **FACT.** Flags ER, TEND, TDFE, BRK, RDF and DR can only be cleared by writing 0 **after they have been read as 1**. Writing 1 has no effect. FER/PER are read-only and describe the *next* FRDR byte (HW manual Rev 1.50 §22.2.7, p.1278).
- **FACT.** TDFE is level-like. It is set while the TX FIFO count is at or below the TX trigger, or while SCR.TE=0. It is set again after a clear if that condition still holds (§22.2.7, p.1280; §22.8.1, p.1327). RDF behaves the same way with the RX trigger (§22.8.2, p.1327). An FRDR read also clears RDF.
- **FACT.** TEND is an event flag. It is set when the last bit of a character has gone out and the TX FIFO is empty. An FTDR write clears it, and so does a 0-write after a 1-read (§22.2.7, p.1281). Its reset value is 0. There is no level re-set.
- **FACT.** DR is set when the RX FIFO holds fewer bytes than the trigger and no new byte has arrived for 15 ETU (about 1.5 frames) after the last stop bit. It is cleared when the FIFO is drained, or by a 0-write after a 1-read (§22.2.7, p.1279).
- **FACT.** Linux clears flags with `sci_clear_SCxSR`. For RZ_SCIFA the overrun mask is LSR's (`SCLSR_ORER`), not `SCIFA_ORER`, so the function takes the third branch: a **blind store** of `mask & ~(SCIF_FERC | SCIF_PERC)` = `mask & 0x00FF`, with no read immediately before it (sh-sci.c:716-729; masks sh-sci.h:98-108). Examples: the TX path stores 0x00DF; `sci_poll_put_char` stores 0x009F; `sci_reset` stores 0x0060; RX stores 0x00FC; the error path stores 0x0073; the break path stores 0x00E3.

### 3.2 FIFO depth and triggers

- **FACT.** 16-stage TX and RX FIFOs (HW manual Rev 1.50 §22.1, Table 22.1, p.1269).
- **FACT.** TTRG: 00=8, 01=4, 10=2, 11=0 bytes remaining. RTRG (async): 00=1, 01=4, 10=8, 11=14. FTCR overrides: TFTC 0-15, RFTC 1-16 (§22.2.10, p.1290; §22.2.15, p.1299).
- **FACT.** Linux uses `rx_trigger = 8` for `PORT_SCIF` and sets `rx_fifo_timeout = 0` (sh-sci.c:3053-3057, 3063). `sci_reset` writes FCR=0x0006, then `scif_set_rtrg(port, 8)` read-modify-writes RTRG=10b (sh-sci.c:2480-2482, 2493-2504; 1094-1151). `set_termios` later drops the reset bits (sh-sci.c:2697-2719). The **final FCR is 0x0080** (RX trigger 8, TX trigger 8). With `rx_fifo_timeout` 0 there is no software timer, so input bursts shorter than 8 bytes reach Linux **only via DR/DRI**.

## 4. Linux paths, step by step

### 4.1 Probe (`sci_probe`, sh-sci.c:3483-3565; `sci_probe_single`, 3405-3481)

1. `sci_parse_dt` gets the optional reset and **deasserts** it (CPG reset), registering an assert action for removal (sh-sci.c:3358-3374). It reads the alias (serial0 gives index 0; serial1 gives index 1 for SCIF2) (sh-sci.c:3381-3395).
2. `sci_init_single`: platform IRQ 0 is mandatory and 1-5 optional (sh-sci.c:3009-3014). The array order is ERI, RXI, TXI, BRI, DRI, TEI (sh-sci.c:61-67), and the DT lists them in that order, so `irqs[] = {380, 382, 383, 381, 384, 384}` (r9a07g054.dtsi:384-391). They are not muxed (`SCIx_IRQ_IS_MUXED`, sh-sci.c:73-77). Clocks: only "fck" exists, and the optional clocks are absent (sh-sci.c:2903-2943).
3. The driver core applies `pinctrl-0` **before** probe. This is the pinctrl dependency (see `pinctrl.md`).
4. `sci_probe_single`: `devm_pm_runtime_enable`. **If earlycon is active on the same MMIO base**, it takes a runtime-PM reference without resuming (`pm_runtime_get_noresume`) so that the CPG clock and PM domain are never switched off under the boot console, and marks the slot as shared (sh-sci.c:3456-3478). Then `uart_add_one_port`, `serial_console_setup`, `uart_set_options`, **`sci_set_termios`**, console registration and log replay through `serial_console_write`. OBSERVED: `printk: legacy console [ttySC0] enabled` follows the ttySC0 probe line at 0.594 s.
- **FACT.** Probe performs no register reads that gate success. There is no ID register and no poll.

### 4.2 `set_termios` register sequence (sh-sci.c:2507-2760; `sci_reset` 2472-2505)

| # | Access | Value (8N1, 115200, P0 = 100 MHz) |
|---|---|---|
| 1 | SCR write | 0x0000 (TE=RE=0, so TDFE is forced to 1) (sh-sci.c:2478) |
| 2 | FCR write | 0x0006 (TFRST\|RFRST) (sh-sci.c:2480-2482) |
| 3 | FSR write | 0x0060 (blind; tries to clear DR/RDF/ER/BRK) (sh-sci.c:2484-2486) |
| 4 | LSR read, write | value & ~0x0005 (clears ORER; bit 2 is a read-only count on RZ) (sh-sci.c:2487-2491) |
| 5 | FCR read-modify-write | RTRG=10b, giving 0x0086 (sh-sci.c:2502; 1146-1148) |
| 6 | SEMR write | 0x00 (MDDRS=0, which unbanks BRR) (sh-sci.c:2641-2642) |
| 7 | SCR, SMR, BRR writes | 0x0000, 0x0000 (CKS=0), 0x1A (sh-sci.c:2657-2659), then a one-bit-time `udelay` (2685). INFERENCE: `sci_scbrr_calc` doubles the clock for non-HSCIF ports and with sr=32, cks=0 gives br=27, so BRR=26=0x1A, error +541 bps (sh-sci.c:2405-2470) |
| 8 | SPTR read-modify-write | sets RTS2IO (and RTS2DT while RTS is deasserted), clears CTS2IO and SCKIO (`sci_init_pins`, sh-sci.c:776-823, SPTR branch 811-822) |
| 9 | FCR read-modify-write | drops TFRST/RFRST, giving 0x0080 (sh-sci.c:2697-2719) |
| 10 | SCR write | 0x0030 (TE\|RE) (sh-sci.c:2730-2733); then 0x0070 (adds RIE, from `sci_start_rx`, sh-sci.c:690-700, 2751-2752) if CREAD |

If the port clock rate reads as 0, the baud computation is skipped and BRR/SMR clock bits are left alone (sh-sci.c:2541-2544, 2686-2693). TEIE is never set for `PORT_SCIF` (it is set only for `PORT_SCI`, sh-sci.c:917-925).

### 4.3 Console output (polled; no interrupts needed)

- **FACT.** `serial_console_write` saves SCR, writes `TE|RE|(SCR & CKE)` (0x0030), and for each character runs `sci_poll_put_char`: **poll FSR until TDFE=1**, write FTDR, then store 0x009F to FSR. It then **waits until TDFE and TEND are both 1**, and restores SCR (sh-sci.c:3115-3150, 762-772).
- **INFERENCE.** The first character printed by the real `sh-sci` console (spec §20 b) needs **no** interrupt delivery. It needs set_termios to complete, TDFE to be readable, and TEND to become 1 after transmission.

### 4.4 tty TX/RX paths (interrupt-driven; needed for a userspace shell)

- **FACT.** `sci_startup` calls `sci_request_dma` (which returns at once for the console port and for any node without `dmas`, sh-sci.c:1657-1670) and `sci_request_irq` when the tty opens (sh-sci.c:2290-2307). SPI 384 is requested once ("rx ready", `sci_rx_interrupt`); the TEI entry is skipped as a duplicate (sh-sci.c:2022-2079, dedup at 2031-2036; descriptors 1976-2020).
- **TX.** `sci_start_tx` sets TIE (sh-sci.c:623-665). TXI (SPI 383) fires while TIE & TDFE. `sci_transmit_chars` reads FSR (if TDFE is clear it only updates TIE and returns), writes up to `16 - FDR.T` bytes, stores 0x00DF, and clears TIE when the buffer is empty (sh-sci.c:869-928; room from FDR 825-846). `sci_tx_empty` uses TEND and FDR.T, guarded by `tx_occurred` because TEND resets to 0 (sh-sci.c:2116-2128).
- **RX.** RXI (SPI 382, RIE & RDF) or DRI (SPI 384, RIE & DR) runs `sci_rx_interrupt` and then `sci_receive_chars`. That returns at once unless FSR shows RDF or DR; otherwise it reads FDR.R, and for each byte reads FSR then FRDR (FER/PER per byte); then it does a dummy FSR read and stores 0x00FC (sh-sci.c:1787-1842, 930-1002).
- **Errors.** ERI (SPI 380) calls `sci_er_interrupt`. ERI and BRI are separate lines here, so the muxed-break branch is skipped. It runs `sci_handle_fifo_overrun` (LSR read; if ORER, write LSR & ~ORER), drains RX through `sci_receive_chars`, stores 0x0073, and then **kicks TX** by calling the TX handler (sh-sci.c:1889-1927, 1042-1067). BRI (SPI 381): `sci_handle_breaks` (FSR read, then the same LSR overrun handling), a dummy FRDR read, and a store of 0x00E3 (sh-sci.c:1874-1887, 1069-1092).

### 4.5 Interrupt line equations QEMU must implement

**FACT** (HW manual Rev 1.50 §22.5, Table 22.19, p.1323; all level):

| Line | Asserted while |
|---|---|
| TXI (383) | SCR.TIE & FSR.TDFE |
| RXI (382) | SCR.RIE & FSR.RDF |
| ERI (380) | (SCR.RIE \| SCR.REIE) & FSR.ER |
| BRI (381) | (SCR.RIE \| SCR.REIE) & (FSR.BRK \| LSR.ORER) |
| TEI0_DRI0 (384) | (SCR.TEIE & FSR.TEND) \| (SCR.RIE & FSR.DR) |

## 5. Earlycon (spec §20 a)

- **FACT.** The match is `OF_EARLYCON_DECLARE(scif, "renesas,scif-r9a07g044", rzscifa_early_console_setup)` (sh-sci.c:3775). `rzscifa_early_console_setup` sets the RZ_SCIFA regtype and calls `early_console_setup` with `PORT_SCIF` (sh-sci.c:3742-3747, 3711-3731).
- **FACT.** A bare `earlycon` argument reaches `param_setup_earlycon` with no value (earlycon.c:230-249). With `CONFIG_ACPI_SPCR_TABLE` (selected by `ACPI`, linux v6.12.59 arch/arm64/Kconfig:12; arm64 `defconfig:109` sets `CONFIG_ACPI=y`), it only sets `earlycon_acpi_spcr_enable`. On a DT boot ACPI is disabled, and `acpi_boot_table_init` then calls `early_init_dt_scan_chosen_stdout()` (linux v6.12.59 arch/arm64/kernel/acpi.c:232-235). Without ACPI the scan is called directly from `param_setup_earlycon`. Either way, the scan resolves `stdout-path = "serial0:115200n8"` to `scif0` and walks the earlycon table **matching by `fdt_node_check_compatible` and skipping entries with an empty compatible**; it does not check `status` (fdt.c:875-920). The generic `"renesas,scif"` entry does not match this node (its compatibles are SoC-specific), so the `r9a07g044` entry wins. `of_setup_earlycon` maps 4 KiB at the `reg` address (earlycon.c:253-330, map at 278).
- **OBSERVED.** On silicon a bare `earlycon` resolves to SCIF0: `earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')` (EVK boot log). The options string is the `stdout-path` suffix, so the DT stdout path was used. The image is G1-based downstream, but `earlycon.c`, `fdt.c` and the earlycon part of `sh-sci.c` are identical in G0 and G1.
- **FACT.** The DTB-U `bootargs` are `"ignore_loglevel rw root=/dev/nfs ip=on"`, with no `earlycon` (rzg2l-smarc-som.dtsi:29). **Earlycon output therefore needs an added boot argument**, which REQ-GUEST-004 lists as a fidelity gap. In direct mode, `-append` replaces the DTB `bootargs` entirely.
- **INFERENCE.** `earlycon=scif,0x1004b800` would be wrong. `setup_earlycon` matches by name; it prefers entries with an empty compatible, and because every `scif` entry has a compatible string, the second pass takes the first `scif` entry in table order: the generic `"renesas,scif"` with the SH4 layout (earlycon.c:183-221; sh-sci.c:3773). Its SCSCR (0x08) would hit FSR. Use plain `earlycon`.
- **FACT.** Registers touched: one SCR read and a write of `SCR | TE | RE` (sh-sci.c:3723-3725). Then `serial_console_write` as in §4.3. It does **not** touch clocks, BRR/SMR/FCR or pinctrl, and it relies entirely on firmware for the baud rate.
- **INFERENCE.** Earlycon works from the manual reset state too (SCR becomes 0x0030; TDFE=1 at reset), because the baud rate is not enforced.

## 6. Start states

### 6.1 Reset (firmware mode)

Table 22.4 values: SMR 0, BRR 0xFF, MDDR 0xFF, SCR 0, FSR 0x0020, FCR 0, FDR 0, SPTR 0x00xx, LSR 0, SEMR 0, FTCR 0x1F1F. Per §22.8.9 (p.1330), the module is in standby at reset; register access needs the module clock and MSTOP released. That is a CPG concern, and what silicon does on access while the module is stopped is an open question (spec §7, §14).

### 6.2 Post-firmware (direct mode), derived from code; OBSERVED on the EVK 2026-10-29

| Step | Writes |
|---|---|
| TF-A BL2 and BL31 `console_rz_init` (`TF-A plat/renesas/rz/common/drivers/scifa.S:123-176`; called from `bl2_plat_setup.c:181-185`, `bl31_plat_setup.c:41-45`) | SCR=0; FCR=0x0006; read FSR/LSR, write 0 to both; SMR=0; SEMR=0x00; BRR = (100 MHz/115200 >> 5) - 1 = **0x1A**; SEMR=**0x30** (MDDRS\|BRME); MDDR = **0xFE**; FTCR read-modify-write (stays 0x1F1F); FCR=0; SCR=**0x0030** |
| U-Boot `sh_serial_init_generic` and `setbrg` (`U-Boot drivers/serial/serial_sh.c:49-82`; `serial_sh.h:100`) | SCR=0x0030 (twice), SMR=0 (twice), FCR=0x0006, then 0; a "BRR" write of 100e6/115200/16-1 = 0x35 **at 0x02 while SEMR.MDDRS=1 and TE=RE=1** |
| OP-TEE (`OP-TEE core/arch/arm/plat-rz/common/drivers/scif.c:93`) | SCR \|= TE |

- **INFERENCE (load-bearing).** U-Boot never writes SEMR. TF-A leaves MDDRS=1, so U-Boot's divisor lands on **MDDR**, and MDDR writes are ignored while TE=RE=1 (§22.2.9, p.1287). BRR stays 0x1A and MDDR 0xFE. This explains the "wrong U-Boot divisor yet working console" observation in `boot-chain-firmware.md` §2. The model must bank 0x02 on SEMR.MDDRS and enforce the MDDR write condition, or a direct-mode read of 0x02 differs from silicon (silicon reads MDDR = 0xFE).
- **Expected direct-mode overlay:** SMR 0x0000, BRR 0x1A, MDDR 0xFE, SEMR 0x30, SCR 0x0030, FCR 0x0000, FTCR 0x1F1F, FSR 0x0060 (TDFE\|TEND after the last character drains), LSR 0, FDR 0. SPTR is untouched by the firmware.
- **OBSERVED (indirect).** The EVK kernel console works at 115200 with no `set_termios` before 0.594 s (earlycon only), so the firmware-left baud setting is correct on silicon. This supports, but does not prove, the BRR/MDDR/SEMR values above.

## 7. Firmware TX patterns: why TEND must not complete synchronously

- **FACT.** TF-A `console_rz_putc` waits on FDR.T<16, stores FTDR, then **reads FSR and writes it back with TEND cleared**; `console_rz_flush` polls TEND=1 (`scifa.S:188-222, 237-256`). U-Boot `serial_raw_putc` polls TEND, stores FTDR, then does the same read-and-clear of TEND (`serial_sh.c:104-124`). OP-TEE stores FTDR, read-modify-writes FSR to clear TEND\|TDFE, and its flush polls TEND (`scif.c:57-75`).
- **INFERENCE (load-bearing for M7/M8).** On silicon the FSR read happens while the character is still shifting out (about 87 µs at 115200). TEND reads 0, the 0-write does nothing, and TEND rises later. If QEMU completes TX inside the FTDR write handler, the read returns TEND=1, the guest clears it legitimately, and nothing sets it again. The next U-Boot putc or the TF-A/OP-TEE flush then **spins forever**. Required model behaviour:
  1. TX completion (FIFO drain, TEND set) happens **after** the FTDR write, on a timer of one character time at the programmed bit rate (or a documented fixed character time).
  2. Implement the read-armed clear rule (§3.1) per flag. A flag is cleared by a 0-write only if it was read as 1 since it was last set.
  3. TDFE is recomputed from FIFO count, trigger and TE after every state change.
- **INFERENCE (residual risk).** Under MTTCG, a host deschedule of the vCPU longer than one character time, between `strb FTDR` and `ldrh FSR`, could still let the timer win. Firmware runs with interrupts masked, so silicon has no such window. Stress-test this (§10).
- **FACT.** The Linux `sh-sci` paths have no read between the FTDR write and the clear (§4.3). They tolerate synchronous completion **only if** the read-armed rule is implemented.

## 8. DMA

- **FACT.** The SCIF nodes have no `dmas`. `sci_request_dma` returns before requesting any channel: first for the console port (`uart_console`), then for any node without a `dmas` property (sh-sci.c:1645-1670). `CONFIG_SERIAL_SH_SCI_DMA` defaults to `ARCH_RENESAS` (linux v6.12.59 drivers/tty/serial/Kconfig:669-672), so the DMA code is compiled in but unused. **DMAC is not needed** for SCIF in G0 or G1. The manual allows DMAC activation by RXI/TXI only (Table 22.19, p.1323). DREQ outputs are UNSUPPORTED initially.

## 9. Existing QEMU analogues and the reuse decision

| Model | Fit | Evidence |
|---|---|---|
| `hw/char/sh_serial.c` (SH7750 SCI/SCIF) | **Poor.** SH4 doubled offsets (SMR 0x00, BRR 0x04, SCR 0x08, FSR 0x10, …; region 0x28), 8-bit register storage, no SEMR/MDDR/FTCR/LSR counts/FDR.T. Reset flags TEND\|TDE (FSR 0x0060, not 0x0020). **Sets TDE\|TEND on every FSR read while TE=1**, which is invented status behaviour. Blocking `qemu_chr_fe_write_all` per byte. Depends on `hw/sh4/sh.h` | QEMU v11.1.2 hw/char/sh_serial.c:96-131, 135-158, 239-260, 391, 414 |
| `hw/char/renesas_sci.c` (RX62N SCI) | **Different IP** (non-FIFO SCI, 8-bit registers at 0-6, SSR flags TDRE/RDRF). Useful as a **template**: registerfields style and timer-based character-time TX (`trtime`) | QEMU v11.1.2 hw/char/renesas_sci.c:34-61, 105-120 |

**Proposal:** a new `TYPE_RENESAS_RZ_SCIFA` model (`hw/char/renesas_rz_scifa.c`), instantiated **5×** at the Table 22.3 bases. Borrow the chardev/DR-timeout ideas from `sh_serial.c` and the registerfields/TX-timer structure from `renesas_sci.c`. Do not extend `sh_serial.c`: its semantics conflict with the read-armed rule and the manual reset value. SCIF2 must exist because DTB-U enables it (OBSERVED: the EVK image also probes ttySC1 at `0x1004c000`). INFERENCE (serial core outside the reviewed files): adding a `uart-has-rtscts` port runs `sci_set_mctrl`, which read-modify-writes FCR (MCE) and SPTR (RTS) (sh-sci.c:2182-2226, 2130-2155). SCIF1/3/4 are disabled in DTB-U, but modelling them costs nothing and is the faithful choice.

## 10. Proposed fidelity class

**FUNCTIONAL / faithful** for asynchronous mode.

- **Modelled:** the full register file with banking and write conditions; 16-byte FIFOs; TTRG/RTRG/FTCR triggers; read-armed flags; TDFE level rule; deferred TEND; DR 15-ETU timeout; FER/PER per byte only if the backend injects errors; LSR.ORER on RX overflow; LOOP (FCR b0) internal loopback; the five IRQ lines in §4.5.
- **Not modelled (honest):** clock-synchronous mode (CM=1 is logged via `LOG_UNIMP`, no transfer); baud enforcement (BRR/MDDR/SEMR are stored and used only for character timing); noise filter; modem lines (MCE/RTS/CTS have no effect; SPTR stored); break transmit/receive; DMAC requests; CPG gating of register access (pending the oracle answer).
- **Verification:** qtests assert Table 22.4 reset values (including FSR=0x0020, FTCR=0x1F1F, BRR=MDDR=0xFF); banking via SEMR.MDDRS; MDDR write ignored with TE=1; the read-armed clear (write 0 without a prior read leaves TEND set); TDFE re-set; FDR counts; the TF-A putc/flush sequence terminating. Mutation check: make TEND synchronous and confirm the firmware-pattern test hangs, then fails on its timeout.

## 11. Conflicts recorded

1. **IRQ sharing.** §22.5 text (p.1323) says TEI, DRI, ERI and BRI share one vector. The Table 22.19 note says TEI+DRI share and ERI+BRI share. Table 8.2 (p.544) gives ERI and BRI **separate** SPIs (380/381) and only TEI0_DRI0 shared (384). DTB-U follows Table 8.2. The model wires per Table 8.2. Oracle: `/proc/interrupts`.
2. **FTDR.** Table 22.4 says W/undefined. The §22.2.4 text says "CPU can read … cannot write" and draws reset bits as 1 (p.1273). Treat it as write-only (read returns 0, logged) until the EVK says otherwise.
3. **FSR high byte.** Linux masks out `SCIF_PERC/FERC` (bits 15:8) when clearing, and clears `SCLSR_TO` (LSR bit 2) in `sci_reset`. On RZ, FSR 15:8 is reserved and LSR bit 2 is FER[0], a read-only count (p.1278, p.1296). Harmless, but recorded.
4. **FSR reset 0x0020 (TEND=0)** differs from the SH SCIF convention used by QEMU `sh_serial.c` (TEND=1). The manual is the authority for reset (spec §5). Linux copes via `tx_occurred`.

### Newer mainline (v6.18.55)

Kept for the later v6.18 LTS regression target (`docs/sources.md`). Citations are `linux v6.18.55 drivers/tty/serial/<file>:N`. The 890 diff lines in `sh-sci.c` are a refactor plus support for other SoCs; **no V2L register sequence changes**:

- The match data becomes a `struct sci_of_data` (`of_sci_scif_rz_scifa`: `PORT_SCIF`, RZ_SCIFA regtype, `sci_port_ops`), and register access goes through per-port ops (sh-sci.c:3398-3404, 3472-3475). The RZ_SCIFA map is unchanged and gains `param_bits`/`common_regs` pointers (sh-sci.c:257-279). A separate `rsci.c` driver for other RZ parts is added; it does not bind on V2L.
- Earlycon goes through `scix_early_console_setup` (sh-sci.c:3856-3888) with the same effect: one SCR read and a write of `SCR | TE | RE`. The `OF_EARLYCON_DECLARE` table is in the same order (sh-sci.c:3928-3935).
- `earlycon.c` adds a `console=` early-param alias that forwards a non-empty value to `param_setup_earlycon` (earlycon.c:251-273). For `console=ttySC0,…` no earlycon entry is named `ttySC0`, so it has no effect here.
- All line numbers of the first draft (for example `sci_reset` 2464-2497, `set_termios` 2499-2752, `serial_console_write` 3218-3255) refer to v6.18.55. The SCIF DT nodes are identical in content (r9a07g054.dtsi:495-587).

## Claims to verify

1. FSR resets to 0x0020 (TEND=0). Evidence: HW manual Rev 1.50 §22.2.7, p.1278; Table 22.4, p.1271.
2. MDDR ignores writes while TE=RE=1, and U-Boot's divisor therefore never reaches BRR. Evidence: HW manual Rev 1.50 §22.2.9, p.1287; TF-A `scifa.S:154-156, 171`; U-Boot `serial_sh.c:49-82`.
3. TF-A leaves SEMR=0x30. Evidence: TF-A `scifa.S:41-47, 154-155`.
4. The final Linux FCR is 0x0080 and RX bursts of fewer than 8 bytes arrive only via DR. Evidence: sh-sci.c:1094-1151, 2472-2505, 2697-2719, 3053-3057.
5. `earlycon=scif,…` selects the SH4 layout, not RZ_SCIFA. Evidence: earlycon.c:183-221; sh-sci.c:3772-3779. (The bare-`earlycon` half of the earlier claim is answered; see below.)
6. The **built** G0 kernel has `SERIAL_SH_SCI`, `_CONSOLE` and `_EARLYCON` as built-ins. Source defaults say yes: `defconfig:488` sets `CONFIG_SERIAL_SH_SCI=y`, and Kconfig defaults `_CONSOLE` to y and `_EARLYCON` to `ARCH_RENESAS` (linux v6.12.59 drivers/tty/serial/Kconfig:656-667). The effective `.config` of the G0 build still has to be read (effective-configuration rule).
7. SPI 384 is shared TEI/DRI and sh-sci registers only the "rx ready" handler on it. Evidence: sh-sci.c:2031-2036; r9a07g054.dtsi:388-389.
8. Synchronous TEND hangs TF-A/U-Boot/OP-TEE. Evidence: §7 citations. Proof would be a QEMU experiment (record under `docs/experiments/`).

### Answered by the EVK boot log (2026-10-08, post-Linux, G1-based downstream image)

- **Bare `earlycon` resolves to SCIF0 via `stdout-path`.** `earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')`. (Was claim 5, first half.)
- **The real console probes and takes over.** ttySC0 at `0x1004b800`, type `scif`, at 0.594 s; then `printk: legacy console [ttySC0] enabled`. This confirms the `PORT_SCIF` selection (§2) and the earlycon-to-console handover (§4.1).
- **SCIF2 probes as ttySC1 at `0x1004c000`** in that image. That image's DT is downstream, so this is consistent with DTB-U enabling `scif2` but is not proof of it.

## Questions for the EVK

All reads are 16-bit unless noted. FSR, LSR and FDR reads have no side effect. **Never read FRDR** (it pops the FIFO).

1. **U-Boot prompt (post-firmware):** run EVK-R20–R26 in `../evidence/requests.md`, which read each register at its documented width and skip FTDR and FRDR. (Superseded: an earlier single `md.w` sweep here crossed FRDR and read 8-bit registers as 16-bit.) Expect SMR 0, 0x02 = 0xFE (MDDR via MDDRS=1), SCR 0x30, FSR 0x60, FCR 0, FDR 0, LSR 0, SEMR 0x30, FTCR 0x1F1F. This tests claims 2 and 3 and fixes the direct-mode overlay.
2. **U-Boot:** is SCIF1 clocked? Read the CPG CLK_MON for SCIF (`cpg-reset.md` gives the offset). Only if it is clocked, read `md.w 0x1004bc08 1` (EVK-R27) for an untouched-channel FSR reset value (claim 1).
3. **Post-Linux (G1 debug image, `/dev/mem`):** read SCIF0 FCR/SCR/SEMR/BRR (expect 0x0080, 0x0070 or 0x00F0, 0x00, 0x1A) and `/proc/interrupts` for SPIs 380-384 (conflict 1). Record that this is post-Linux, not post-firmware.
4. **U-Boot:** read an undefined offset in the SCIF0 window (for example `md.w 0x1004b818 1`): zero, bus error, or alias? This decides the model's behaviour for undefined offsets.
5. **Post-Linux:** `zcat /proc/config.gz | grep -E 'SERIAL_SH_SCI|ACPI_SPCR'` (if `IKCONFIG_PROC` is on) on the G1 image, to record which earlycon path (§5) the reference kernel takes.

## Verification (main session, 2026-10-08)

| Claim | Result | Evidence |
|---|---|---|
| Firmware writes FTDR, then clears TEND by an FSR read-modify-write, then polls TEND | **Confirmed** for TF-A | TF-A `plat/renesas/rz/common/drivers/scifa.S`: putc writes `FTDR`, then reads `FSR` and writes it back with `FSR_TEND` cleared; flush polls `FSR_TEND`. The model must not complete TEND inside the FTDR write. |
| QEMU `sh_serial.c` sets TEND on FSR reads | **Confirmed** | qemu v11.1.2 `hw/char/sh_serial.c`: the read path sets `SH_SERIAL_FLAG_TDE \| SH_SERIAL_FLAG_TEND`; reset sets TEND\|TDE. It is unsuitable as-is. |
| Earlycon match | **Confirmed** | linux v6.12.59 `drivers/tty/serial/sh-sci.c:3775` `OF_EARLYCON_DECLARE(scif, "renesas,scif-r9a07g044", rzscifa_early_console_setup)`; same line in G1. OBSERVED on silicon: EVK boot log `earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')` |
| DTB-U has no `earlycon` in bootargs | **Confirmed** | linux v6.12.59 `rzg2l-smarc-som.dtsi:29` `bootargs = "ignore_loglevel rw root=/dev/nfs ip=on"`; `rz-smarc-common.dtsi:26,32` `serial0 = &scif0`, `stdout-path = "serial0:115200n8"`. M3a needs a bare `earlycon` on the command line, recorded as a REQ-GUEST-004 gap. |
| `CONFIG_SERIAL_SH_SCI` built in for G0 | **Confirmed (defconfig)** | linux v6.12.59 `arch/arm64/configs/defconfig:488`; the built `.config` is still to be checked (claim 6) |
| Note re-based from v6.18.55 to the pinned G0/G1 kernels | **Done (2026-10-08)** | All kernel citations moved to linux v6.12.59; G1 checked at rz_linux-cip `212f6e88b7` (one-line `sh-sci.c` delta, no register effect). Corrections against the first draft: the bare-`earlycon` path goes through `earlycon_acpi_spcr_enable` and `acpi_boot_table_init` when `ACPI_SPCR_TABLE` is set (§5); the `fdt.c` matching is now read, not inferred; DMA is skipped by an explicit `dmas` check rather than a failed channel request (§8); the error handler also kicks TX (§4.4). v6.18.55 differences kept under "Newer mainline". EVK boot-log evidence folded into §1, §2, §4.1, §5 and §6.2. |

## EVK results (2026-10-29, U-Boot prompt, downstream firmware; `../evidence/EVK-2026-10-29-post-firmware.md`)

- **OBSERVED.** The §6.2 overlay holds on silicon: SMR 0, MDDR `0xFE` (MDDRS = 1), SCR `0x0030`, FSR `0x0060` with the line idle, FCR/FDR/LSR 0, SEMR `0x30`, FTCR `0x1F1F`, SPTR `0x0001` (EVK-R20-R26). Claims 2 and 3: confirmed on this firmware. BRR is still seen only indirectly.
- **OBSERVED.** Right after U-Boot echoes a command, FSR reads `0x0020` (TEND = 0) and FDR.T = 1. After `sleep 1` it reads `0x0060`. TEND stays 0 while a character is in flight and rises when the line goes idle, as §7 requires (indirect: the read timing is U-Boot's).
- **OBSERVED.** Q4: the undefined offset `+0x18` reads `0x0000`, no bus error (EVK-R70).
- Q2: SCIF1 is not clocked after firmware (CLK_MON SCIF = `0x1`), so claim 1 stays unmeasured on silicon (EVK-R27 skipped).
