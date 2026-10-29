# M2: the first character

> **Context.** Milestone M2 (spec [§17](../spec/project.md#17-milestones)): the board prints its first characters through SCIF0. Unit files: [spec](../units/M2-first-character/spec.md), [design](../units/M2-first-character/design.md), [tasks](../units/M2-first-character/tasks.md). The SCIF facts are in [`scif.md`](../research/scif.md). The EVK values are in [`EVK-2026-10-29-post-firmware.md`](../evidence/EVK-2026-10-29-post-firmware.md).

## 1. Reading registers on the EVK

This section shows what happened when the EVK registers were read at the U-Boot prompt on 2026-10-29. Each point changes how the next read session is done, or what a value means.

### 1.1 Stopping autoboot

The EVK U-Boot uses a keyed autoboot. It prints this line and waits 3 seconds:

```
Type 'edge' within 3 seconds to stop autoboot
```

Only that exact string stops autoboot. Enter and other keys do not. If the string does not arrive within 3 seconds, U-Boot loads Linux. The image's boot command then writes the U-Boot environment to eMMC (`Saving Environment to MMC... Writing to redundant MMC(0)... OK`). The 3-second window is short for a tool that sends one command at a time. On 2026-10-29 the operator stopped autoboot by hand, and the tools continued from the `=>` prompt.

### 1.2 An empty line repeats the last command

At the `=>` prompt, an empty line runs the previous command again. On 2026-10-29 one Enter ran the operator's `printenv` again. After an `md` command, an empty line reads the *next* block of addresses. That block can contain a register with a read side effect, for example the SCIF receive FIFO `FRDR` at `0x1004b80a`. For this reason, send each `md` as a complete command and never send an empty line.

### 1.3 A read that aborts resets the board

Some reads abort from the U-Boot prompt. This happened for `SYS_MSTACCCTL0` at `0x11020000`:

```
md.l 0x11020000 6
"Synchronous Abort" handler, esr 0x96000010, far 0x11020000
...
Resetting CPU ...
```

`esr 0x96000010` is a data abort with the fault code `0x10`, a synchronous external abort. `far` is the address that failed. After the register dump, U-Boot resets the board, and autoboot starts again (§1.1). U-Boot runs in the non-secure world. The most likely cause is that the register is secure-only, but that is an inference: the evidence record leaves the cause open. The abort is still the answer to the question the row asked: the register is not readable from this U-Boot state. Run such reads last, one at a time (`requests.md` section 1.7).

### 1.4 The console is also the device under test

SCIF0 is the U-Boot console and also the device the reads measure. U-Boot echoes each command on SCIF0. A read that comes directly after the echo sees the transmitter busy:

```
md.w 0x1004b808 1
1004b808: 0020
sleep 1; md.w 0x1004b808 1
1004b808: 0060
```

The first read shows `FSR` = `0x0020`: TDFE is 1 and TEND is 0, because the last echo character is still being sent. After `sleep 1`, nothing is sent between the pause and the read, and `FSR` reads `0x0060` (TEND = 1, the line is idle). `FDR` showed the same effect: `0x0100` (one byte in the TX FIFO) directly after the echo, and `0x0000` after the pause. This is how TEND behaves on silicon. TEND is 0 while a character is in flight, and it becomes 1 only when the line goes idle. The model must do the same ([design §4](../units/M2-first-character/design.md#4-tx-rx-and-flags)).

### 1.5 The serial tool's write policy

The serial-console tools open each session with a write policy:

| Policy | Effect |
|---|---|
| `deny` | every write is refused; for passive listening only, for example a boot log |
| `confirm` | each write needs approval; on a client that shows a dialog, the operator approves every command |
| `allow` | writes go through without approval |

A session can also have deny patterns. The server refuses a command that matches one, whatever the policy. On 2026-10-29 the session first used `confirm`, and the operator had to approve each `md`. The session then changed to `allow` with the same deny patterns: `mw`, `mm`, `nm`, `cp`, `mmc write`, `sf`, `saveenv`, `reset`, `boot*` and `go`. The server refused those named commands. The patterns are a finite list. They do not block every command that changes state. They also do not stop the read side effects in §1.2 and §1.3. At the U-Boot prompt the tools sent only `md` reads, `sleep 1`, `version` and the autoboot key string; the reboot was a `reboot` command sent earlier at the Linux root shell.

## 2. The SCIFA register tests (M2-T01)

The qtest file `qemu/tests/qtest/rzv2l-scifa-test.c` checks the SCIFA registers against the manual and the EVK values (fork commit `a032eef5d6`). Each test was seen red on a mutation before it counted. The red line is the assertion the mutation aims at, after a rebuild that changed the binary.

| Mutation (M2-T01, T07) | Test result |
|---|---|
| `FSR_RESET` `0x0020` → `0x0060` | `not ok …/scif/reset`: `(0x00000060 == 0x00000020)` |
| offset `0x02` reads BRR whatever SEMR.MDDRS is | `not ok …/scif/brr-mddr-bank`: `(0x00000035 == 0x000000ff)` |
| MDDR write refused only when TE **and** RE are 1 | `not ok …/scif/mddr-write-rule`: `(0x000000d5 == 0x000000a1)`, the TE-only case |
| `SMR_WMASK` `0x00fb` → `0x00ff` | `not ok …/scif/smr-mask`: `(0x0000007f == 0x0000007b)` |
| the SMR write with CM = 1 is accepted | `not ok …/scif/sync-mode-refused`: `(0x00000088 == 0x00000008)` |
| an undefined offset reads `0xffff` | `not ok …/scif/undefined-offset`: `(0x0000ffff == 0x00000000)` |
| `direct-boot` ignored | `not ok …/scif/direct-boot`: `(0x000000ff == 0x000000fe)`, the MDDR read |
| SCIF2 mapped `0x1000` too high | M1 acceptance: `FAIL mtree: memory map differs` and `FAIL qtree: renesas-rz-scifa @000000001004c000: missing 'direct-boot = false'` |

The `sync-mode-refused` test sees only half of the behaviour. The model refuses the write with a decode error, and qtest cannot see a bus error (`testing.md` §1). The test therefore checks that SMR keeps its old value. The guest probe in M2-T08 checks that the CPU takes the abort.

## 3. Transmit and TEND (M2-T02)

The model sends each byte through a shift register. A byte leaves the 16-byte FIFO, goes to the chardev, and the next byte follows one frame time later on the virtual clock. TEND becomes 1 only when the last frame is out and the FIFO is empty. The frame time comes from the manual's bit-rate formulas (p.1282, p.1287) and the frame format in SMR. With the direct-boot settings, a 10-bit frame takes 87.08 µs.

The qtest steps the virtual clock to 200 ns before the end of the frame and checks that TEND is still 0. It then steps 400 ns more and checks that TEND is 1. The 200 ns margin is smaller than the MDDR correction (680 ns), so a model that ignores MDDR fails the test.

| Mutation (M2-T02) | Test result |
|---|---|
| a 0-write clears an FSR flag without the prior read | `not ok …/scif/fsr-read-armed`: `(0x00000020 == 0x00000060)` |
| TDFE stored, not computed from the FIFO count | `not ok …/scif/tdfe-level`: `(0x00000040 == 0x00000060)` |
| TEND set in the FTDR write handler | `not ok …/scif/tend-deferred`: `(0x00000040 == 0x00000000)`, before the frame ends |
| TTRG hard-wired to 8 | `not ok …/scif/tx-trigger`: `(0x00000020 == 0x00000000)`, 5 bytes with trigger 4 |
| an FTDR write leaves TEND | `not ok …/scif/ftdr-clears-tend`: `(0x00000040 == 0x00000000)` |
| the MDDR correction (SEMR.BRME) ignored | `not ok …/scif/tend-deferred`: TEND already 1 at 86.88 µs |
| the second stop bit ignored | `not ok …/scif/tend-deferred`: the 7E2 frame ends 8.7 µs early |
| SMR.CKS ignored (review R4) | `not ok …/scif/tend-deferred`: TEND already 1 at a quarter of the CKS = 1 frame |
| BRR hardwired to 0x1A (review R4) | `not ok …/scif/tend-deferred`: TEND already 1 at half the BRR = 0x35 frame |
| TEND set with TE off and a byte still queued (review R1) | `not ok …/scif/tend-te-cleared`: `(0x00000040 == 0x00000000)` |
| bit 7 sent in 7-bit mode (review R3) | `not ok …/scif/tx-7bit`: `(0x000000c1 == 0x00000041)` |
| SEMR.ABCS0 ignored, or SEMR.BGDM ignored (recheck N1) | `not ok …/scif/tend-deferred`: `(0x00000000 == 0x00000040)`, TEND still 0 when the doubled-rate frame should be out |
| CKS capped at 1 (recheck N1) | `not ok …/scif/tend-deferred`: `(0x00000040 == 0x00000000)`, TEND already 1 long before the CKS = 3 frame ends |

## 4. Receive, DR and overrun (M2-T03)

The receive side has its own 16-byte FIFO. Most tests use loopback (FCR.LOOP): the transmitter feeds the receiver, and a looped byte arrives when its frame is done. The receive timing is then exact on the virtual clock. One test sends bytes through a real socket chardev.

Two manual rules are easy to get wrong:
- RDF is set when the FIFO *reaches* the trigger, but after a clear it is set again only while the FIFO holds *more* than the trigger (§22.8.2, p.1327).
- DR is set 15 bit times after the last byte (§22.2.7, p.1279). This is 1.5 frames only for 8-bit data with one stop bit. The test checks the 7E2 format too, where 1.5 frames is 13 µs longer.

| Mutation (M2-T03) | Test result |
|---|---|
| an FRDR read does not pop | `not ok …/scif/rx-fifo`: `(0x00000061 == 0x00000062)` |
| DR after 1.5 frames | `not ok …/scif/rx-dr-timeout`: DR still 0 in 7E2 |
| RDF set again at "equal to the trigger" | `not ok …/scif/rx-fifo`: `(0x00000002 == 0x00000000)` at 4 bytes |
| an FRDR read leaves RDF set | `not ok …/scif/rx-fifo`: the same line |
| no ORER on overrun | `not ok …/scif/rx-overrun`: `(0x00000000 == 0x00000001)` |
| ORER clears without the prior read | `not ok …/scif/rx-overrun`: the same line |
| RE ignored | `not ok …/scif/rx-disabled`: `(0x00000001 == 0x00000000)` |
| reception continues while ORER is set (review R2) | `not ok …/scif/rx-stopped-by-orer`: `(0x00000010 == 0x0000000f)` |
| the host held off while ORER is set, instead of losing the byte (recheck N2) | `not ok …/scif/rx-chardev-while-orer`: `(0x00000010 == 0x0000000f)` |

## 5. The interrupt lines (M2-T04)

Each SCIF channel has five level outputs: ERI, BRI, RXI, TXI and the shared TEI/DRI line. The model computes each line from the enable bits in SCR and the flags, as in Table 22.19 (p.1323). It recomputes them after every register access and every timer event. The SoC wires SCIF*n*'s lines to GIC SPIs 380 + 5*n* to 384 + 5*n*.

The qtest watches the device's own outputs. qtest cannot watch GIC inputs at SPI 256 or above (`testing.md` §1), so the GIC routing is checked by the hello probe instead (§6).

A trap in the test: qtest learns a line's level only when the device drives the line *after* the intercept starts. A line that went high during reset reads as low in the test. The first version of the TXI test therefore missed a mutation, "TXI ignores TIE". The fix makes the device report all five lines once, by writing SCR with its current value right after the intercept.

| Mutation (M2-T04) | Test result |
|---|---|
| TXI ignores TIE | `not ok …/scif/irq-txi`: TXI = 1 while TIE = 0 |
| RXI ignores RIE | `not ok …/scif/irq-rxi`: `(1 == 0)` |
| the DR term dropped from TEI/DRI | `not ok …/scif/irq-tei-dri`: `(0 == 1)` |
| BRI ignores REIE | `not ok …/scif/irq-bri`: `(0 == 1)` |
| RXI and TXI swapped | `not ok …/scif/irq-txi`: RXI rises with TIE |

## 6. Hello, and the M2 acceptance run (M2-T08, T09)

The hello probe is a bare-metal guest program in `tests/probes/hello-rzv2l/`. It does not set the UART up. It writes `Hello from RZ/V2L` the way TF-A's console does (`scifa.S:188-222` @ `f59ed5a31`):
1. For a newline, wait until FDR.T is below 16 and store CR to FTDR.
2. Wait until FDR.T is below 16 and store the byte to FTDR.
3. Read FSR and write it back with TEND cleared, once per call. A newline therefore clears TEND once, after both bytes. The first version of the probe sent CR through a recursive call and cleared TEND twice; the final review caught the difference (R6).

At the end it waits for TEND, as TF-A's flush does. Each wait has a limit, so a model bug makes the probe fail instead of hang. The probe works because direct mode starts SCIF0 as the firmware leaves it (§1.4 and the evidence file).

The probe then checks what only a CPU can see:
- SCIF0's TXI reaches the CPU as INTID 415 (32 + SPI 383), through the real GIC.
- An SMR write with CM = 1 takes a synchronous external abort (spec decision (c)).
- The undefined offset `+0x18` reads 0 without an abort.

`tests/acceptance/m2/run.sh` runs M1 acceptance first, then the probe. It compares the serial output with `expected/serial.txt` byte for byte: `Hello from RZ/V2L`, CR, LF. The semihosting output on stderr never counts as the greeting. Last comes the log gate: only the probe's two deliberate accesses may appear in the `-d` log.

One acceptance mutation needed thought. The ticket proposed "TEND set in the FTDR write" for A02, but this model also sets TEND again when the frame timer fires, so TF-A's flush still finishes. The failure that matters on real firmware is a model that completes the whole transmission inside the write: TEND rises at once, TF-A clears it, and nothing sets it again. That mutation makes the probe's flush time out with exit 2, which is the red line A02 expects.

## 7. What the final review found (M2-T13)

The independent review of the finished unit read the model against the manual rather than against the tests, and found three places where the model was silently wrong and one where the tests could not tell.

- **TEND and an idle shift register (R1).** The model set TEND whenever the shift register went idle. The manual's condition is stricter: FTDR must hold no data at the last bit (§22.2.7 p.1281). The two differ when software clears TE with bytes still queued: the frame in flight ends, nothing follows, and TEND must stay 0. The new test `tend-te-cleared` queues two bytes, clears TE, waits two frames and expects FDR.T = 1 and TEND = 0.
- **Reception after an overrun (R2).** Once ORER is set, the hardware stops receiving until software clears it (§22.2.13 p.1296). The model only checked whether the FIFO was full, so reading one byte let the next one in. Now a set ORER drops every incoming byte, looped or from the chardev, the way RE = 0 does. Bytes typed on the host while ORER is set are lost, as on the real line.
- **7-bit frames (R3).** With SMR.CHR = 1 only bits 6..0 go out (p.1274 note 3). The model changed the frame time but sent the whole byte. The receive side of 7-bit mode is still not modelled.
- **The clock divider was untested (R4).** Every timing case ran at the firmware's divider (CKS = 0, BRR = 0x1A). The reviewer forced the CKS term to zero and the whole suite stayed green. Two new cases, CKS = 1 and BRR = 0x35, now quadruple and double the frame time, with the expected times derived from the manual's formula in the test's comment.

Each fix came with its test shown red on the old model first, and each test has a mutation in `tests/eval/m2/` that makes it red again. The recheck of the fixes (a third model) then did what the first reviewer had done for CKS: it dropped the SEMR.ABCS0 and SEMR.BGDM terms and capped CKS at 1, and the suite stayed green. Three more timing cases close that: ABCS0 alone, BGDM alone and both, which halve and quarter the bit time (p.1284 note), and CKS = 3, which multiplies it by 64. A timing axis is only verified once a value other than the firmware's has been asserted on it. The other two findings were a citation (the output order of the five IRQ lines comes from Table 8.2, not Table 22.19) and the hello probe's claim to reproduce TF-A's access order exactly (§6).
