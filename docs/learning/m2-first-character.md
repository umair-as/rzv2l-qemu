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

