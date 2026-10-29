# M2-first-character — design

Labels: (F) documented fact, (O) hardware observation, (I) code-derived inference, (A) assumption. Manual = HW manual Rev 1.50 §22 unless stated otherwise.

## 1. Structure

| Part | Where | What |
|---|---|---|
| `TYPE_RENESAS_RZ_SCIFA` | fork `hw/char/renesas_rz_scifa.c`, `include/hw/char/renesas_rz_scifa.h`, `hw/char/Kconfig` (`RENESAS_RZ_SCIFA`), `hw/char/meson.build`, `hw/char/trace-events` | one SysBusDevice per channel: an MMIO region of `0x400`, five `qemu_irq` outputs, one chardev, two virtual-clock timers (TX frame, RX DR timeout), property `direct-boot` (bool, default off) |
| SoC wiring | fork `hw/arm/r9a07g054.c`, `include/hw/arm/r9a07g054.h`, `hw/arm/Kconfig` (`R9A07G054` selects `RENESAS_RZ_SCIFA`) | five children `scif[0..4]` at the device-map bases, IRQs to GIC SPIs, chardev `serial_hd(i)` → SCIF*i* |
| Board | fork `hw/arm/rzv2l-smarc.c` | sets `scif[0].direct-boot` = true when `machine->kernel_filename` is set, before realize |
| qtests | fork `tests/qtest/rzv2l-scifa-test.c` + `meson.build` | one test path per check S01-S13 (§7), on `-M rzv2l-smarc`, using `qtest_irq_intercept_out` on the SCIF0 QOM path for S09 |
| Hello image | project, path per spec decision (a): `tests/probes/hello-rzv2l/` | started from `tests/probes/m1-skeleton/`: an arm64 `Image`, semihosting exit status |
| G0 kernel | project `tests/guests/g0/build-kernel.sh` (next to `build-dtb.sh`) | v6.12.59 arm64 `defconfig` `Image` plus a static BusyBox initramfs; outputs untracked |
| Acceptance | project `tests/acceptance/m2/run.sh`, `expected/` | the hello run, mtree/qtree against expected files, log gate, earlycon run |
| Eval harness | project `tests/eval/m2/checks.yaml`, `tests/eval/m2/mutations/*.patch`, `scripts/eval.py` | §7 |

## 2. Register behaviour

Offsets are from each channel's base. "Post-firmware" is the direct-mode start state of SCIF0 (EVK-R20-R26, (O) for this firmware); SCIF1-4 start at reset in both modes.

| Off | Reg | W | Reset (Table 22.4 p.1271) | Post-firmware | Class | Behaviour |
|---|---|---|---|---|---|---|
| 0x00 | SMR | 16 | `0x0000` | `0x0000` | config | stores b7:0 (b2 reads 0). CM (b7) = 1 → `LOG_UNIMP` once and no transfer while set (§5). CHR/PE/STOP/CKS feed the frame time |
| 0x02 | BRR | 8 | `0xFF` | `0x1A` (I: TF-A `scifa.S:154-156`; hidden behind MDDR, EVK indirect) | config, banked | visible while SEMR.MDDRS = 0; always writable (the TE=RE=0 rule in §22.2.8 is advisory) |
| 0x02 | MDDR | 8 | `0xFF` | `0xFE` (O, EVK-R21) | config, banked | visible while MDDRS = 1; a write is ignored while SCR.TE = RE = 1 (§22.2.9 p.1287); b7 reads 1 |
| 0x04 | SCR | 16 | `0x0000` | `0x0030` (O) | config + IRQ enables | stores TIE b7, RIE b6, TE b5, RE b4, REIE b3, TEIE b2, CKE b1:0. TE = 0 forces TDFE = 1; TE 0→1 starts sending a non-empty FIFO |
| 0x06 | FTDR | 8 | — | — | push | write pushes into the 16-byte TX FIFO; a write to a full FIFO is discarded and logged under `guest_errors` (§22.2.4 p.1273). Clears TEND (§22.2.7 p.1281). A read returns 0 and logs `guest_errors` (A: write-only per §22.2.4) |
| 0x08 | FSR | 16 | `0x0020` | `0x0060` (O, EVK-R23 with the line idle) | status | ER b7, TEND b6, TDFE b5, BRK b4, FER b3 (RO), PER b2 (RO), RDF b1, DR b0. ER/TEND/TDFE/BRK/RDF/DR clear only by a 0-write after a 1-read; writing 1 has no effect (p.1278). TDFE and RDF are re-computed after every change (§3) |
| 0x0A | FRDR | 8 | — | — | pop | read pops the RX FIFO and clears RDF if the count drops below the trigger; an empty FIFO reads 0 (manual: undefined; A). A write is ignored and logged |
| 0x0C | FCR | 16 | `0x0000` | `0x0000` (O) | config + level reset | RSTRG b10:8 (stored only: no RTS), RTRG b7:6, TTRG b5:4, MCE b3 (stored), TFRST b2, RFRST b1 (each holds its FIFO empty while 1; not self-clearing), LOOP b0 (§3) |
| 0x0E | FDR | 16 | `0x0000` | `0x0000` (O) | derived, RO | T[4:0] b12:8 = TX FIFO count, R[4:0] b4:0 = RX FIFO count (§22.2.11 p.1292). The shift register is not counted |
| 0x10 | SPTR | 16 | `0x00xx` | `0x0001` (O) | config + pin state | stores the odd (control) bits. The even bits read pin levels: SPB2DT b0 reads RxD, idle mark = 1; SCKDT, CTS2DT and RTS2DT read 0 (A: pins not modelled). The model reads `0x0001` in both states, which matches the EVK value |
| 0x12 | LSR | 16 | `0x0000` | `0x0000` (O) | status | ORER b0 (read-armed clear); FER[3:0] b5:2 and PER[3:0] b11:8 count errors in the RX FIFO (RO, stay 0: the backend injects no errors) |
| 0x14 | SEMR | 8 | `0x00` | `0x30` (O) | config | BGDM b7, BRME b5, MDDRS b4, DIR b3, NFEN b2, ABCS0 b0; stored. MDDRS banks `0x02`; BGDM/ABCS0/BRME feed the frame time; DIR and NFEN have no effect (§5) |
| 0x16 | FTCR | 16 | `0x1F1F` | `0x1F1F` (O) | config | RTRGS b15, RFTC b12:8, TTRGS b7, TFTC b4:0. With TTRGS/RTRGS = 1, TFTC/RFTC override FCR's triggers (§22.2.15 p.1299) |
| other | — | — | — | — | undefined | reads 0, writes ignored, `guest_errors` log. EVK-R70: `+0x18` = 0, no bus error (O); the rest of `0x18-0x3FF` is extrapolated (I) |

**Access widths (A).** The 8-bit registers accept 8-bit accesses and the 16-bit registers 16-bit ones; an 8-bit access to a 16-bit register uses QEMU's partial-access path. A 32-bit access is refused (`.valid.max_access_size = 2`), so the guest takes a bus error. All three consumers (Linux, TF-A, U-Boot) use the documented widths (`scif.md` §4, §7).

## 3. TX, RX and flags

**Read-armed clears (F, p.1278).** Each clearable flag (FSR ER/TEND/TDFE/BRK/RDF/DR, LSR ORER) has an *armed* bit. An FSR or LSR read arms every flag that reads 1. A write of 0 to an armed flag clears it; the arm drops when the flag next sets, or after it has been cleared. A 0-write to an unarmed flag does nothing. Linux's blind stores of `mask & 0x00FF` (`scif.md` §3.1) clear only what it has seen, which is the hardware rule.

**TDFE (F, p.1280; §22.8.1 p.1327).** After every TX-side change, TDFE = 1 if SCR.TE = 0 or the TX count ≤ the TX trigger (FCR.TTRG: 00 = 8, 01 = 4, 10 = 2, 11 = 0, or FTCR.TFTC when TTRGS = 1). A clear is accepted (armed), and the level rule then sets TDFE again immediately while the condition holds. RDF follows the same rule with the RX trigger (RTRG 00 = 1, 01 = 4, 10 = 8, 11 = 14, or RFTC when RTRGS = 1).

**Transmit.** When SCR.TE = 1 and the shift register is idle, the model takes the head byte from the TX FIFO into the shift register, writes it to the chardev (`qemu_chr_fe_write`, non-blocking; a short write retries on `qemu_chr_fe_add_watch`), and arms the TX timer for one frame time. When the timer fires, the next byte is shifted. If the FIFO is empty, TEND sets (a fresh set, so not armed). With FCR.LOOP = 1 the byte goes to the RX path instead of the chardev. TFRST = 1 empties the FIFO and holds it empty; the byte already in the shift register finishes.

**Frame time (F formulas, A for use).** bit rate B = P0 / (K × 2^(2n−1) × (N + 1)) × (BRME ? MDDR/256 : 1). P0 = 100 MHz (device map, SCIF row). n = SMR.CKS. N = BRR. K = 64 (BGDM = 0, ABCS0 = 0), 32 (exactly one of BGDM or ABCS0 set) or 16 (both set) (p.1282, p.1287). Frame = 1 start + 8 or 7 data (CHR) + 1 parity (PE) + 1 or 2 stop (STOP) bits. The rate is used only for timing; nothing checks it against the host (device map §4 row 13). TF-A's settings (BRR `0x1A`, MDDR `0xFE`, SEMR `0x30`, SMR 0) give 114 836 bit/s and an 87.1 µs frame.

**Receive.** The chardev's `can_receive` reports the free RX FIFO space. With RE = 0, incoming bytes are discarded. Each byte enters the FIFO, FDR.R increments, RDF is re-computed, and the DR timer is armed for 15 ETU (1.5 frames) (§22.2.7 p.1279). If the timer expires with 0 < count < RX trigger, DR sets. Draining the FIFO clears DR. RFRST = 1 empties and holds the RX FIFO. The model does not generate ORER: `can_receive` gives the host flow control, so the FIFO cannot overflow (gap, §6). FER, PER and BRK stay 0, because the backend injects no line errors.

## 4. Interrupts (F, Table 22.19 p.1323, all level-high)

| Output | SPI (SCIF0) | INTID | Asserted while |
|---|---|---|---|
| ERI | 380 | 412 | (RIE \| REIE) & ER |
| BRI | 381 | 413 | (RIE \| REIE) & (BRK \| ORER) |
| RXI | 382 | 414 | RIE & RDF |
| TXI | 383 | 415 | TIE & TDFE |
| TEI/DRI | 384 | 416 | (TEIE & TEND) \| (RIE & DR) |

SCIF*n* uses SPIs 380 + 5*n* .. 384 + 5*n*, in the same order (device map; DTB-U `interrupts` read on the built DTB: SCIF0 `0x17c 0x17e 0x17f 0x17d 0x180 0x180` = eri, rxi, txi, bri, tei, dri). The outputs are re-evaluated after every register access and every timer event.

## 5. Start states (spec §9)

- **Firmware mode** (`direct-boot` off): Table 22.4, FIFOs empty, no flag armed.
- **Direct mode** (`direct-boot` on; the board sets it on SCIF0 only, when `-kernel` is given): SMR 0, BRR `0x1A`, MDDR `0xFE`, SCR `0x0030`, FSR `0x0060`, FCR 0, FDR 0, SPTR `0x0001`, LSR 0, SEMR `0x30`, FTCR `0x1F1F`, FIFOs empty, no flag armed. These are the measured values (EVK-R20-R26, O), except BRR, which is code-derived (I). They belong to the firmware recorded in `../../evidence/EVK-2026-10-29-post-firmware.md`.
- Both are applied in the device's reset handler, so a system reset in direct mode returns to the post-firmware values. That is what the guest saw before reset (A); a firmware-mode run starts from Table 22.4.

## 6. Fidelity

**SCIFA: FUNCTIONAL / faithful** for asynchronous mode, as described above.

| Not modelled | Guest sees | Honesty |
|---|---|---|
| clock-synchronous mode (SMR.CM = 1) | `LOG_UNIMP`, no transfer, no TEND | honest-fault: a guest waiting for TEND times out |
| baud-rate enforcement | bytes reach the host at any divisor | gap (device map §4 row 13); the frame time still follows the divisor |
| module clock and MSTOP gating | registers accessible with the clock off | gap until M3b (CPG); what silicon does on access while stopped is open (`scif.md` §6.1) |
| modem lines (MCE, RTS/CTS, SPTR control bits) | stored, no effect | gap; SCIF2's `uart-has-rtscts` path in M3b writes them |
| overrun (ORER), framing/parity errors, break | never set by the backend | gap: the host side cannot produce them |
| noise filter (NFEN), DIR (LSB-first) | stored, no effect | gap (A) |
| DMAC requests (RXI/TXI as DREQ) | none | UNSUPPORTED; no DT node has `dmas` (`scif.md` §8) |
| pin mux | the chardev is wired whatever PFC selects | documented decision (device map §4 row 12) |

## 7. Checks and the eval harness

Each check in `tests/eval/m2/checks.yaml` has: `id`, `proves`, `golden` + `citation` (manual page, scif.md line or EVK row; never model output), `command`, `pass` (the expected pass output), `mutation` (patch file), `red_line` (a regex for the expected failure line).

| ID | Proves | Golden source | Mutation |
|---|---|---|---|
| S01 | Table 22.4 resets | p.1271 | FSR reset `0x0060` |
| S02 | `0x02` banking on MDDRS | p.1282, p.1287 | ignore MDDRS |
| S03 | MDDR write ignored with TE = RE = 1 | p.1287; EVK-R21 | accept the write |
| S04 | read-armed clear | p.1278 | clear without arming |
| S05 | TDFE set again after a clear while count ≤ trigger | p.1280 | store TDFE, do not compute |
| S06 | TEND = 0 until one frame time after the FTDR write | p.1281; `scif.md` §7; EVK-R23 | set TEND in the write handler |
| S07 | TX trigger at two TTRG values | p.1290 | TTRG hard-wired to 8 |
| S08 | RX: FDR.R, RDF at the trigger, FRDR pops, DR after 15 ETU | p.1279, p.1327 | FRDR does not pop |
| S09 | the five IRQ equations | p.1323 | TXI ignores TIE |
| S10 | undefined offset reads 0 + `guest_errors` log | EVK-R70 | abort instead (MEMTX error) |
| S11 | CM = 1 → `LOG_UNIMP`, nothing sent | §22.2.5 p.1274 | transmit anyway |
| S12 | start states by property | p.1271; EVK-R20-R26 | property ignored |
| S13 | an FTDR write clears TEND | p.1281 | FTDR write leaves TEND |
| A01-A05, L01-L03 | Ticket 2 checks (spec AC12-AC17) | spec | spec / Ticket 2 |

`scripts/eval.py m2 [--fork <sha>]`:
1. Creates a fresh `git worktree` of the fork at `<sha>` (default: the `qemu/` submodule commit) under `build/eval/m2/src`, never in `qemu/`, and builds it out of tree in `build/eval/m2/build` (`--target-list=aarch64-softmmu`).
2. Runs every check and requires its `pass` output.
3. For each mutation: applies the patch with `git apply`, rebuilds, and asserts that `qemu-system-aarch64` and the qtest binary were relinked (both mtime and SHA-256 changed). Then it runs only that check, requires the `red_line` match, and reverts with `git apply -R`. After the last mutation it checks that the worktree is clean again.
4. Writes `build/eval/m2/report.md`: `id | green | mutation red | red line matched`.

The harness never runs `git checkout --`, never uses `pkill -f`, and stops processes by PID.

## 8. Decisions

- DR-0005 applied: the windows this machine leaves unmapped are recorded gaps under its two conditions. Task T10 adds the device-map §4 row that condition 2 requires.
- Device-map change for review: SCIF1-4 move from M3b to M2 (wired now, in their reset state).
- No new DR for the SCIFA model: the reuse decision (a new model, not an extension of `sh_serial.c`) is already argued in `scif.md` §9.
