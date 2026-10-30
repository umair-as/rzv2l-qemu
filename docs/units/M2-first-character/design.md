# M2-first-character — design

Labels: (F) documented fact, (O) hardware observation, (I) code-derived inference, (A) assumption. Manual = HW manual Rev 1.50 §22 unless stated otherwise.

## 1. Structure

| Part | Where | What |
|---|---|---|
| `TYPE_RENESAS_RZ_SCIFA` | fork `hw/char/renesas_rz_scifa.c`, `include/hw/char/renesas_rz_scifa.h`, `hw/char/Kconfig` (`RENESAS_RZ_SCIFA`), `hw/char/meson.build`, `hw/char/trace-events` | one SysBusDevice per channel: an MMIO region of `0x400`, five `qemu_irq` outputs, one chardev, two virtual-clock timers (TX frame, RX DR timeout), property `direct-boot` (bool, default off). A `VMStateDescription` covers every register, the armed bits, both FIFOs, the shift-register state and both timers (`device-model` step 8) |
| SoC wiring | fork `hw/arm/r9a07g054.c`, `include/hw/arm/r9a07g054.h`, `hw/arm/Kconfig` (`R9A07G054` selects `RENESAS_RZ_SCIFA`) | five children `scif[0..4]` at the device-map bases, IRQs to GIC SPIs, chardev `serial_hd(i)` → SCIF*i* |
| Board | fork `hw/arm/rzv2l-smarc.c` | sets `scif[0].direct-boot` = true when `machine->kernel_filename` is set, before realize |
| qtests | fork `tests/qtest/rzv2l-scifa-test.c` + `meson.build` | one test path per check S01-S13 (§8), on `-M rzv2l-smarc`, using `qtest_irq_intercept_out` on the SCIF0 QOM path for S09 |
| Hello image | project, path per spec decision (a): `tests/probes/hello-rzv2l/` | started from `tests/probes/m1-skeleton/`: an arm64 `Image`, semihosting exit status |
| G0 kernel | project `tests/guests/g0/build-kernel.sh` (next to `build-dtb.sh`) | v6.12.59 arm64 `defconfig` `Image` plus a static BusyBox initramfs; outputs untracked |
| Acceptance | project `tests/acceptance/m2/run.sh`, `expected/` | the hello run, mtree/qtree against expected files, log gate, earlycon run |
| Eval harness | project `tests/eval/m2/checks.yaml`, `tests/eval/m2/mutations/*.patch`, `scripts/eval.py` | §8 |

## 2. Consumer evidence (register-evidence)

**Consumers at M2/M3a.** Each `file:line` below was checked at the pin.
1. The hello image, which copies TF-A's putc/flush.
2. G0 Linux earlycon: `rzscifa_early_console_setup` → `early_console_setup`, then `serial_console_write` → `sci_poll_put_char` (linux v6.12.59 `drivers/tty/serial/sh-sci.c:3742-3747, 3711-3731, 3115-3150, 762-772`).
3. The firmware that leaves the direct-mode state. It is not run in M2, but its writes define the overlay: TF-A `f59ed5a31` `plat/renesas/rz/common/drivers/scifa.S`, U-Boot `4eebfbaa4e` `drivers/serial/serial_sh.c`, OP-TEE `82a5cd3b` `core/arch/arm/plat-rz/common/drivers/scif.c`.

The `sh-sci` driver probe (the tty and IRQ paths) is M3b and out of scope here. Effective configuration: DTB-U SCIF0 `status = "okay"` (read on the built DTB-U). `CONFIG_SERIAL_SH_SCI_EARLYCON` in the *built* G0 kernel is still open (claim 6, check L01).

| Off | Register | Width | Reset (manual) | Direct-mode start | Fields used | Class | Guest `file:line` | Cite |
|---|---|---|---|---|---|---|---|---|
| 0x00 | SMR | 16 | `0x0000` | `0x0000` (O) | whole register written 0 | config | TF-A `scifa.S:140-141`; U-Boot `serial_sh.c:53-54` | §22.2.5 p.1274 |
| 0x02 | BRR | 8 | `0xFF` | `0x1A` (I) | written with SEMR.MDDRS = 0 | config, banked | TF-A `scifa.S:143-148`; U-Boot `serial_sh.c:80` (lands on MDDR, ignored) | §22.2.8 p.1282 |
| 0x02 | MDDR | 8 | `0xFF` | `0xFE` (O) | written with MDDRS = 1, TE = RE = 0 | config, banked, write-conditional | TF-A `scifa.S:150-156` | §22.2.9 p.1287 |
| 0x04 | SCR | 16 | `0x0000` | `0x0030` (O) | TE, RE, CKE (RMW) | config + IRQ enables | TF-A `scifa.S:124-125, 136-138, 171-172`; U-Boot `serial_sh.c:51-52`; OP-TEE `scif.c:93`; earlycon `sh-sci.c:3723-3725` (read, write \| RE \| TE), `:3132-3136` (save, set), `:3146` (restore) | §22.2.6 p.1276 |
| 0x06 | FTDR | 8 | undefined | — | byte push | push (side effect: FIFO, TEND clear, the wire) | TF-A `scifa.S:199-200, 207`; U-Boot `serial_sh.c:116`; OP-TEE `scif.c:73`; earlycon `sh-sci.c:770` | §22.2.4 p.1273, §22.2.7 p.1281 |
| 0x08 | FSR | 16 | `0x0020` | `0x0060` (O) | TEND polled; TEND (and TDFE) cleared by read-and-write-back; TDFE polled | status: TEND event, TDFE level; read-armed clears | TF-A `scifa.S:130-133` (read, write 0), `:210-212` (read, write back \& ~TEND), `:248-251` (poll TEND, **no timeout**); U-Boot `serial_sh.c:111, 120`; OP-TEE `scif.c:61-62, 74`; earlycon `sh-sci.c:766-768` (poll TDFE), `:771` (blind store `0x009F`, no read in between), `:3141-3143` (wait TDFE \| TEND, **no timeout**) | §22.2.7 p.1278-1281 |
| 0x0C | FCR | 16 | `0x0000` | `0x0000` (O) | TFRST/RFRST pulse, then 0 | config + level reset | TF-A `scifa.S:127-128, 168-169`; U-Boot `serial_sh.c:55-57` | §22.2.10 p.1290 |
| 0x0E | FDR | 16 | `0x0000` | `0x0000` (O) | T[4:0] polled (< 16) | derived, RO | TF-A `scifa.S:195-198, 203-206`; OP-TEE `scif.c:70-72` | §22.2.11 p.1292 |
| 0x12 | LSR | 16 | `0x0000` | `0x0000` (O) | read, then written 0 | status (ORER read-armed) | TF-A `scifa.S:131, 134` | §22.2.13 p.1296 |
| 0x14 | SEMR | 8 | `0x00` | `0x30` (O) | MDDRS, BRME | config | TF-A `scifa.S:143-144, 154-155` | §22.2.14 p.1297 |
| 0x16 | FTCR | 16 | `0x1F1F` | `0x1F1F` (O) | TTRGS, RTRGS cleared (RMW) | config | TF-A `scifa.S:164-167` | §22.2.15 p.1299 |
| 0x0A, 0x10, other | FRDR, SPTR, undefined | — | — | — | not touched by the M2/M3a consumers | — | — (FRDR and SPTR are M3b `sh-sci` paths; the hello image reads `+0x18` only to check S10) | — |

**What the consumers require of the model.** Two of the loops above (TF-A's flush and Linux's console write) wait for TEND with no timeout. After each character TEND reads 0: the FTDR write clears it (p.1281), and every path writes 0 to it again afterwards, either by reading FSR and writing it back with TEND = 0 (TF-A, U-Boot, OP-TEE) or by a blind store after a TDFE poll (Linux). TEND must therefore rise again on its own once the last frame is out (§4). It must not rise in the FTDR write handler; it must not stay set; and a 0-write must not clear it unless TEND was read as 1. Each of those behaviours makes one of these loops spin forever (`scif.md` §7).

**Spec §6 evidence check.**

| Item | Status |
|---|---|
| MMIO range | `0x1004B800` + `0x400`, five channels (device map; Table 22.3 p.1271) |
| IRQs and trigger | SPIs 380-404 (Table 8.2 p.544; DTB-U `interrupts`, flags 4), level-high (Table 22.19 p.1323) |
| clocks/resets | `CLK_ON 0x584` b0-4, `RST 0x884` b0-4. Not modelled in M2 (gap §7); post-firmware SCIF0 on, SCIF1-4 off (EVK-R13) |
| DMA | none: no `dmas` in DTB-U; DREQ UNSUPPORTED (`scif.md` §8) |
| both start states | §6, measured except BRR (I) |
| guest consumers | the table above |
| manual reference | §22, Rev 1.50 |
| fidelity and honesty | FUNCTIONAL / faithful (async); §7 lists the gaps and their honesty |
| unsupported behaviour | §7 |
| verification | qtests S01-S13, the hello image A01-A03, earlycon L02, all mutation-checked (§8) |
| open | `.config` claim 6 (L01, T11); the read effect of a 32-bit access on silicon (A); the undefined-offset range beyond `+0x18` (I) |

## 3. Register behaviour

Offsets are from each channel's base. "Post-firmware" is the direct-mode start state of SCIF0 (EVK-R20-R26, (O) for this firmware); SCIF1-4 start at reset in both modes.

| Off | Reg | W | Reset (Table 22.4 p.1271) | Post-firmware | Class | Behaviour |
|---|---|---|---|---|---|---|
| 0x00 | SMR | 16 | `0x0000` | `0x0000` | config | stores b7:0 (b2 reads 0). CM (b7) = 1 → `LOG_UNIMP` once and no transfer while set (§7). CHR/PE/STOP/CKS feed the frame time |
| 0x02 | BRR | 8 | `0xFF` | `0x1A` (I: TF-A `scifa.S:154-156`; hidden behind MDDR, EVK indirect) | config, banked | visible while SEMR.MDDRS = 0; always writable (the TE=RE=0 rule in §22.2.8 is advisory) |
| 0x02 | MDDR | 8 | `0xFF` | `0xFE` (O, EVK-R21) | config, banked | visible while MDDRS = 1; writable **only while SCR.TE = RE = 0**, so a write is ignored when TE or RE is 1 (§22.2.9 p.1287; review R1); b7 reads 1 |
| 0x04 | SCR | 16 | `0x0000` | `0x0030` (O) | config + IRQ enables | stores TIE b7, RIE b6, TE b5, RE b4, REIE b3, TEIE b2, CKE b1:0. TE = 0 forces TDFE = 1; TE 0→1 starts sending a non-empty FIFO |
| 0x06 | FTDR | 8 | — | — | push | write pushes into the 16-byte TX FIFO; a write to a full FIFO is discarded and logged under `guest_errors` (§22.2.4 p.1273). Clears TEND (§22.2.7 p.1281). A read returns 0 and logs `guest_errors` (A: write-only per §22.2.4) |
| 0x08 | FSR | 16 | `0x0020` | `0x0060` (O, EVK-R23 with the line idle) | status | ER b7, TEND b6, TDFE b5, BRK b4, FER b3 (RO), PER b2 (RO), RDF b1, DR b0. ER/TEND/TDFE/BRK/RDF/DR clear only by a 0-write after a 1-read; writing 1 has no effect (p.1278). TDFE and RDF are re-computed after every change (§4) |
| 0x0A | FRDR | 8 | — | — | pop | read pops the RX FIFO and clears RDF (p.1279: any FRDR read clears RDF); RDF then follows the re-set rule in §4. Draining the FIFO clears DR. An empty FIFO reads 0 (manual: undefined; A). A write is ignored and logged |
| 0x0C | FCR | 16 | `0x0000` | `0x0000` (O) | config + level reset | RSTRG b10:8 (stored only: no RTS), RTRG b7:6, TTRG b5:4, MCE b3 (stored), TFRST b2, RFRST b1 (each holds its FIFO empty while 1; not self-clearing), LOOP b0 (§4) |
| 0x0E | FDR | 16 | `0x0000` | `0x0000` (O) | derived, RO | T[4:0] b12:8 = TX FIFO count, R[4:0] b4:0 = RX FIFO count (§22.2.11 p.1292). The shift register is not counted |
| 0x10 | SPTR | 16 | `0x00xx` | `0x0001` (O) | config + pin state | stores the odd (control) bits. The even bits read pin levels: SPB2DT b0 reads RxD, idle mark = 1; SCKDT, CTS2DT and RTS2DT read 0 (A: pins not modelled). The model reads `0x0001` in both states, which matches the EVK value |
| 0x12 | LSR | 16 | `0x0000` | `0x0000` (O) | status | ORER b0 (read-armed clear); FER[3:0] b5:2 and PER[3:0] b11:8 count errors in the RX FIFO (RO, stay 0: the backend injects no errors) |
| 0x14 | SEMR | 8 | `0x00` | `0x30` (O) | config | BGDM b7, BRME b5, MDDRS b4, DIR b3, NFEN b2, ABCS0 b0; stored. MDDRS banks `0x02`; BGDM/ABCS0/BRME feed the frame time; DIR and NFEN have no effect (§7) |
| 0x16 | FTCR | 16 | `0x1F1F` | `0x1F1F` (O) | config | RTRGS b15, RFTC b12:8, TTRGS b7, TFTC b4:0. With TTRGS/RTRGS = 1, TFTC/RFTC override FCR's triggers (§22.2.15 p.1299) |
| other | — | — | — | — | undefined | reads 0, writes ignored, `guest_errors` log. Only one 16-bit read at `+0x18` was measured (EVK-R70: 0, no bus error, O). Reads at other undefined offsets and all writes are unmeasured (A). This overrides the `device-model` default (reference §7: `LOG_UNIMP` + decode error), because the silicon measurement says zero |

**Access widths (A).** Each register accepts only its documented width: 8-bit accesses to the 8-bit registers, 16-bit accesses to the 16-bit ones. Any other access that touches a register's bytes (a wrong width, or a byte inside a 16-bit register) gets a decode error plus a `guest_errors` log line, so the guest takes a bus error. What silicon does is not known, and failing visibly is the honest choice. A 32-bit access is refused by QEMU itself (`.valid.max_access_size = 2`). All three consumers (Linux, TF-A, U-Boot) use the documented widths (`scif.md` §4, §7).

## 4. TX, RX and flags

**Read-armed clears (F, p.1278).** Each clearable flag (FSR ER/TEND/TDFE/BRK/RDF/DR, LSR ORER) has an *armed* bit. An FSR or LSR read arms every flag that reads 1. A write of 0 to an armed flag clears it; the arm drops when the flag next sets, or after it has been cleared. A 0-write to an unarmed flag does nothing. Linux's blind stores of `mask & 0x00FF` (`scif.md` §3.1) clear only what it has seen, which is the hardware rule.

**TDFE (F, p.1280; §22.8.1 p.1327).** TDFE = 1 while SCR.TE = 0 or the TX count ≤ the TX trigger (FCR.TTRG: 00 = 8, 01 = 4, 10 = 2, 11 = 0, or FTCR.TFTC when TTRGS = 1). TDFE clears on an armed 0-write and on an FTDR write (p.1280). After either clear, the model re-checks the condition at once and sets TDFE again while it holds. **Wording conflict:** §22.2.7 and the second sentence of §22.8.1 say "equal to or less than"; the first sentence of §22.8.1 says "fallen below". The model uses ≤ (two of three statements, and the Linux and TF-A paths do not depend on the boundary); S07 asserts the boundary value so a change is visible.

**RDF (F, p.1279; §22.8.2 p.1327).** RDF sets when a received byte makes the RX count ≥ the RX trigger (RTRG 00 = 1, 01 = 4, 10 = 8, 11 = 14, or RFTC when RTRGS = 1). RDF clears on an armed 0-write and on any FRDR read (p.1279). After a clear, RDF sets again at once only while the count *exceeds* the trigger (§22.8.2). **Wording conflict:** the first set uses "equal to or greater", the set-again rule "exceeds"; the model follows each statement where it applies (A), and S08 asserts both boundaries (count = trigger after a clear stays 0; count = trigger + 1 sets again).

**Transmit.** When SCR.TE = 1 and the shift register is idle, the model takes the head byte from the TX FIFO into the shift register, writes it to the chardev (`qemu_chr_fe_write`, non-blocking; a short write retries on `qemu_chr_fe_add_watch`), and arms the TX timer for one frame time. When the timer fires, the next byte is shifted. If the FIFO is empty, TEND sets (a fresh set, so not armed); if TE was cleared while bytes are still queued, nothing is shifted and TEND stays 0, because its setting condition is an empty FTDR at the last bit (§22.2.7 p.1281; review R1). In 7-bit mode (SMR.CHR) the shift register takes bits 6..0 of the byte (p.1274 note 3; review R3); the receive side of 7-bit mode is not modelled, host bytes pass through unchanged. With FCR.LOOP = 1 the byte goes to the RX path instead of the chardev. TFRST = 1 empties the FIFO and holds it empty; the byte already in the shift register finishes.

**Frame time (F formulas, A for use).** bit rate B = P0 / (K × 2^(2n−1) × (N + 1)) × (BRME ? MDDR/256 : 1). P0 = 100 MHz (device map, SCIF row). n = SMR.CKS. N = BRR. K = 64 (BGDM = 0, ABCS0 = 0), 32 (exactly one of BGDM or ABCS0 set) or 16 (both set) (p.1282, p.1287). Frame = 1 start + 8 or 7 data (CHR) + 1 parity (PE) + 1 or 2 stop (STOP) bits. The rate is used only for timing; nothing checks it against the host (device map §4 row 13). TF-A's settings (BRR `0x1A`, MDDR `0xFE`, SEMR `0x30`, SMR 0) give 114 836 bit/s and an 87.1 µs frame.

**Receive.** The chardev's `can_receive` reports the free RX FIFO space. With RE = 0, incoming bytes are discarded; DR keeps its value (p.1279 note). Each byte enters the FIFO, FDR.R increments, RDF follows its rule, and the DR timer is armed for **15 bit times** (15 ETU), counted from the byte's arrival (that is, the end of its stop bit) (§22.2.7 p.1279). "1.5 frames" is true only for 8N1 (p.1279 note 1), so the timeout does not use the frame time. If the timer expires with 0 < count < RX trigger, DR sets. Draining the FIFO clears DR. RFRST = 1 empties and holds the RX FIFO. **Overrun:** from the chardev the FIFO cannot overflow, because `can_receive` gives the host flow control. With FCR.LOOP = 1 the TX side feeds the RX side with no flow control, so a byte that arrives with 16 bytes in the RX FIFO is lost and sets LSR.ORER (§22.2.13 p.1296; that loopback reception follows the normal receive rules is I). While ORER is set the receiver is stopped: every further byte, looped or from the chardev, is consumed and dropped (as with RE = 0; the host is not held off, so a byte typed then is lost, as on the real line) until ORER is cleared (§22.2.13 "cannot continue subsequent serial reception"; §22.4.2 overrun check; review R2). FER, PER and BRK stay 0, because no backend produces line errors.

## 5. Interrupts (F, Table 22.19 p.1323, all level-high)

| Output | SPI (SCIF0) | INTID | Asserted while |
|---|---|---|---|
| ERI | 380 | 412 | (RIE \| REIE) & ER |
| BRI | 381 | 413 | (RIE \| REIE) & (BRK \| ORER) |
| RXI | 382 | 414 | RIE & RDF |
| TXI | 383 | 415 | TIE & TDFE |
| TEI/DRI | 384 | 416 | (TEIE & TEND) \| (RIE & DR) |

SCIF*n* uses SPIs 380 + 5*n* .. 384 + 5*n*, in the same order (device map; DTB-U `interrupts` read on the built DTB: SCIF0 `0x17c 0x17e 0x17f 0x17d 0x180 0x180` = eri, rxi, txi, bri, dri, tei). The outputs are re-evaluated after every register access and every timer event.

## 6. Start states (spec §9)

- **Firmware mode** (`direct-boot` off): Table 22.4, FIFOs empty, no flag armed.
- **Direct mode** (`direct-boot` on; the board sets it on SCIF0 only, when `-kernel` is given): SMR 0, BRR `0x1A`, MDDR `0xFE`, SCR `0x0030`, FSR `0x0060`, FCR 0, FDR 0, SPTR `0x0001`, LSR 0, SEMR `0x30`, FTCR `0x1F1F`, FIFOs empty, no flag armed. These are the measured values (EVK-R20-R26, O), except BRR, which is code-derived (I). They belong to the firmware recorded in `../../evidence/EVK-2026-10-29-post-firmware.md`.
- Both are applied in the device's reset handler, so a system reset in direct mode returns to the post-firmware values. That is what the guest saw before reset (A); a firmware-mode run starts from Table 22.4.

## 7. Fidelity

**SCIFA: FUNCTIONAL / faithful** for asynchronous mode, as described above.

| Not modelled | Guest sees | Honesty |
|---|---|---|
| clock-synchronous mode (SMR.CM = 1) | per spec decision (c): **A** `LOG_UNIMP`, no transfer, TEND never sets; or **B** the SMR write that sets CM returns a decode error (`device-model` reference §7) | honest-fault either way: under A the guest notices only when its TEND wait times out, under B at once |
| baud-rate enforcement | bytes reach the host at any divisor | gap (device map §4 row 13); the frame time still follows the divisor |
| module clock and MSTOP gating | registers accessible with the clock off | gap until M3b (CPG); what silicon does on access while stopped is open (`scif.md` §6.1) |
| modem lines (MCE, RTS/CTS, SPTR control bits) | stored, no effect | gap; SCIF2's `uart-has-rtscts` path in M3b writes them |
| framing/parity errors (ER, FER, PER), break (BRK); ORER from the chardev | never set | gap: no backend produces them. ORER is reachable through loopback (§4). The ERI line and BRI's BRK term are verified only as low (S09d), not as rising |
| noise filter (NFEN), DIR (LSB-first) | stored, no effect | gap (A) |
| DMAC requests (RXI/TXI as DREQ) | none | UNSUPPORTED; no DT node has `dmas` (`scif.md` §8) |
| pin mux | the chardev is wired whatever PFC selects | documented decision (device map §4 row 12) |
| TE cleared mid-frame; TEND after TFRST with TE = 0 | the frame in flight finishes (the manual says clearing TE initializes TSR, p.1276); with TE = 0, an empty FIFO after TFRST and an idle shift register, TEND stays 0 until a transmission completes (the manual gives no setting condition for this case) | gap (recheck N3): code reading, not tested; none of the pinned firmware or sh-sci sequences clears TE mid-transmission; an EVK measurement would be needed to model it honestly (`requests.md`) |

## 8. Checks and the eval harness

Each check in `tests/eval/m2/checks.yaml` has: `id`, `proves`, `golden` + `citation` (manual page, scif.md line or EVK row; never model output), `command`, `pass` (the expected pass output), `mutation` (patch file), `red_line` (a regex for the expected failure line).

| ID | Proves | Golden source | Mutation |
|---|---|---|---|
| S01 | Table 22.4 resets | p.1271 | FSR reset `0x0060` |
| S02 | `0x02` banking on MDDRS | p.1282, p.1287 | ignore MDDRS |
| S03 | MDDR write accepted only with TE = RE = 0: all four TE/RE combinations | p.1287; EVK-R21 | `TE && RE` instead of `TE \|\| RE` |
| S04 | read-armed clear | p.1278 | clear without arming |
| S05 | TDFE set again after a clear while count ≤ trigger | p.1280 | store TDFE, do not compute |
| S06 | TEND = 0 until one frame time after the FTDR write | p.1281; `scif.md` §7; EVK-R23 | set TEND in the write handler |
| S07 | TX trigger at two TTRG values | p.1290 | TTRG hard-wired to 8 |
| S08a | RX: FDR.R counts, FRDR pops, RDF set at the trigger and cleared by an FRDR read; RDF set-again boundary | p.1279, p.1327 | FRDR does not pop |
| S08b | DR after exactly 15 bit times, also in 7E2 (11-bit frames) | p.1279 | DR timeout = 1.5 × frame time |
| S09a | TXI = TIE & TDFE, rises and falls | p.1323 | TXI ignores TIE |
| S09b | RXI = RIE & RDF | p.1323 | RXI ignores RIE |
| S09c | TEI/DRI = (TEIE & TEND) \| (RIE & DR), each term alone | p.1323 | DR term dropped |
| S09d | BRI = (RIE \| REIE) & ORER through a loopback overrun; ERI stays low (ER unreachable) | p.1323, p.1296 | BRI ignores REIE |
| S10 | undefined offset reads 0 + `guest_errors` log | EVK-R70 | abort instead (MEMTX error) |
| S11 | CM = 1 handled as spec decision (c) chooses; for B also the CPU-side abort in the hello image (A06) | §22.2.5 p.1274 | A: transmit anyway; B: accept the write |
| S12 | start states by property | p.1271; EVK-R20-R26 | property ignored |
| S13 | an FTDR write clears TEND | p.1281 | FTDR write leaves TEND |
| A01-A05, L01-L03 | Ticket 2 checks (spec AC12-AC17) | spec | spec / Ticket 2 |

`scripts/eval.py m2 [--fork <sha>]`:
1. Creates a fresh `git worktree` of the fork at `<sha>` (default: the `qemu/` submodule commit) under `build/eval/m2/src`, never in `qemu/`, and builds it out of tree in `build/eval/m2/build` (`--target-list=aarch64-softmmu`).
2. Runs every check and requires its `pass` output.
3. For each mutation: applies the patch with `git apply`, rebuilds, and asserts that `qemu-system-aarch64` was relinked (mtime and SHA-256 changed) and that the check runs that binary (`QTEST_QEMU_BINARY` points at it). The qtest client binary is built from test sources only, so a model mutation does not change it, and the harness does not require that (review R2). Then it runs only that check, requires the `red_line` match, and reverts with `git apply -R`. After the last mutation it checks that the worktree is clean again.
4. Writes `build/eval/m2/report.md`: `id | green | mutation red | red line matched`.

The harness never runs `git checkout --`, never uses `pkill -f`, and stops processes by PID.

## 9. Decisions

- DR-0005 applied: the windows this machine leaves unmapped are recorded gaps under its two conditions. Task T10 adds the device-map §4 row that condition 2 requires.
- Device-map change for review: SCIF1-4 move from M3b to M2 (wired now, in their reset state).
- No new DR for the SCIFA model: the reuse decision (a new model, not an extension of `sh_serial.c`) is already argued in `scif.md` §9.
