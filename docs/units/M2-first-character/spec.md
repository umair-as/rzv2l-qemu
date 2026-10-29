# M2-first-character — spec

**Milestone:** M2, plus M3a (earlycon output)
**Status:** DRAFT (2026-10-29): decisions (a)-(d) taken by the operator, design revised after the Codex design review; waiting for the operator's spec review
**Requirements:** REQ-SCIF-001, REQ-TEST-001, REQ-GUEST-001 (stock DTB for the M3a run), REQ-GUEST-004 (the earlycon boot argument), REQ-TEST-002 (mutation-checked tests), REQ-MAP-001 (new windows, unmapped-window gaps)

## Goal

The machine gets its first console. A new SCIFA model sits at the five SCIF bases, and SCIF0 is wired to the host serial chardev. A bare-metal hello image prints `Hello from RZ/V2L` the way TF-A does, without its own UART set-up, because direct mode starts SCIF0 in the post-firmware state measured on the EVK. Then a mainline G0 kernel with DTB-U prints through `earlycon` (M3a) until its first unmet expectation, which is recorded and left for M3b. The SCIFA model is checked against the manual by qtests, and each check is proven by a mutation the eval harness applies and reverts.

## Acceptance criteria (EARS)

Check IDs (S, A, L) are the eval-harness IDs from `design.md` §8.

| ID | Criterion | REQ | Verified by |
|---|---|---|---|
| M2-AC01 | WHEN the device resets (firmware mode) THEN every register SHALL read its Table 22.4 value (p.1271): SMR 0, BRR = MDDR `0xFF`, SCR 0, FSR `0x0020`, FCR 0, FDR 0, LSR 0, SEMR 0, FTCR `0x1F1F`. | SCIF-001 | S01 |
| M2-AC02 | WHILE SEMR.MDDRS = 1 offset `0x02` SHALL access MDDR, otherwise BRR (§22.2.8 p.1282, §22.2.9 p.1287). | SCIF-001 | S02 |
| M2-AC03 | IF MDDR is written while SCR.TE = 1 or SCR.RE = 1 THEN the write SHALL be ignored; WHILE TE = RE = 0 it SHALL be accepted (§22.2.9 p.1287). U-Boot's divisor write is lost this way on silicon (EVK-R21). | SCIF-001 | S03 |
| M2-AC04 | WHEN 0 is written to an FSR flag THEN the flag SHALL clear only if it was read as 1 since it was last set (§22.2.7 p.1278). | SCIF-001 | S04 |
| M2-AC05 | WHILE the TX FIFO count ≤ the TX trigger (FCR.TTRG or FTCR.TFTC) or SCR.TE = 0, FSR.TDFE SHALL be 1, including straight after a clear (§22.2.7 p.1280, §22.2.10 p.1290, §22.2.15 p.1299). | SCIF-001 | S05, S07 |
| M2-AC06 | WHEN FTDR is written THEN TEND SHALL clear (§22.2.7 p.1281) and SHALL NOT set again until virtual time has passed the last character's frame time with the FIFO empty. | SCIF-001 | S06, S13 |
| M2-AC07 | WHEN the chardev delivers bytes THEN they SHALL enter the 16-byte RX FIFO, FDR.R SHALL count them, RDF SHALL set at the RX trigger and clear on an FRDR read, an FRDR read SHALL pop, and DR SHALL set 15 bit times after the last byte while the count is below the trigger, whatever the frame format (§22.2.7 p.1279, §22.8.2 p.1327). | SCIF-001 | S08a, S08b |
| M2-AC08 | The five level IRQ outputs SHALL follow Table 22.19 p.1323: ERI, BRI, RXI, TXI, TEI/DRI (`design.md` §5). TXI, RXI, TEI/DRI and BRI (through ORER) are shown rising and falling; ERI is shown only staying low, because no backend produces ER (gap). | SCIF-001 | S09a-S09d |
| M2-AC09 | WHEN an offset with no register is accessed THEN reads SHALL return 0 and writes SHALL be ignored, logged under `-d guest_errors`. EVK-R70 measured one 16-bit read at `+0x18` = 0 with no bus error; other offsets and all writes are unmeasured (A). | SCIF-001 | S10 |
| M2-AC10 | IF the guest selects clock-synchronous mode (SMR.CM = 1) THEN the model SHALL fail as decision (c) chooses: A, `LOG_UNIMP` and nothing transmitted; or B, a decode error on that SMR write, which the CPU takes as an abort. | SCIF-001 | S11; for B also A06 |
| M2-AC11 | The device SHALL start at Table 22.4 when the property `direct-boot` is off, and at the EVK post-firmware values (EVK-R20-R26) when it is on. The board SHALL set the property on SCIF0 only when a kernel image is loaded. | SCIF-001 | S12 |
| M2-AC12 | WHEN the hello image runs in direct mode THEN the serial chardev SHALL carry exactly `Hello from RZ/V2L`, written with TF-A's putc/flush sequence and no UART set-up of its own, and the image SHALL exit 0. IF TEND completes inside the FTDR write THEN the flush SHALL time out with exit 2, not hang. | TEST-001, SCIF-001 | A01, A02 |
| M2-AC13 | WHEN SCR.TIE = 1 and TDFE = 1 THEN the CPU SHALL take INTID 415 (SPI 383, SCIF0 TXI). | SCIF-001 | A03 |
| M2-AC14 | `info mtree` and `info qtree` SHALL show the five SCIF windows at their device-map bases, size `0x400`, wired to SPIs 380-404 in device-map order, and every M1 line SHALL be unchanged. | SCIF-001, MAP-001 | A04 |
| M2-AC15 | The acceptance run's `-d unimp,guest_errors,invalid_mem` log SHALL contain only allow-listed lines. | MAP-001 | A05 |
| M2-AC16 | WHEN the pinned G0 kernel (v6.12.59 arm64 defconfig, effective `.config` read) boots with the unmodified DTB-U and the boot argument decided in (b) THEN the console SHALL show `Linux version 6.12.59` and `earlycon: scif0 at MMIO 0x000000001004b800`. | SCIF-001 (M3), GUEST-001, GUEST-004 | L01, L02 |
| M2-AC17 | The first boot blocker after earlycon SHALL be recorded with the layer verified and the coverage list, and SHALL NOT be fixed in this unit. | GUEST-004 | L03 (review item) |
| M2-AC18 | Every S and A check SHALL be seen red on its stated mutation, on its stated line, in a fresh worktree build (`scripts/eval.py m2`). | TEST-002 | eval report |

## Exit gate

- **Passes when:** AC01-AC18 hold on the final reviewed revision, `scripts/eval.py m2` reports every check green and every mutation red on its stated line, M1 acceptance still passes, and the closure checklist in `tasks.md` is complete.
- **Disqualifies:** a golden taken from the model's own output; a status bit or "ready" constant with no manual or EVK source; a check whose mutation fails at start-up or by timeout where a value assert was promised.
- **Known blind spots:** baud rates are not enforced, so the host sees bytes whatever the divisor. The read timing behind EVK-R23 is U-Boot's, so "TEND rises after the frame" is observed on silicon only indirectly.

## Scope

**In:**
- `TYPE_RENESAS_RZ_SCIFA` (fork `hw/char/renesas_rz_scifa.c`): asynchronous mode, FUNCTIONAL / faithful. Covers the register file with BRR/MDDR banking, the read-armed flag clears, the TDFE/RDF level rules, deferred TEND on a virtual-time timer, 16-byte FIFOs with FDR, the DR timeout and the five IRQ lines. A `direct-boot` property selects the start state.
- Five instances in `r9a07g054` at the device-map bases, SPIs 380-404, `serial_hd(0)` on SCIF0. The device map placed SCIF1-4 in M3b. They cost nothing extra and give the M3b per-window review real windows instead of unmapped ones (device-map change listed for review).
- The hello image (path per decision (a)) and its checks; an acceptance run `tests/acceptance/m2/`.
- The eval harness: `tests/eval/m2/checks.yaml`, `tests/eval/m2/mutations/`, `scripts/eval.py`.
- A G0 kernel build in `tests/guests/g0/`, booted to earlycon output and stopped at the first blocker.
- A bench profile `rzv2l-smarc-m2-hello`, the learning doc `docs/learning/m2-first-character.md`, traceability and requirement statuses.

**Out (non-goals):**
- CPG, PFC, IRQC, OSTM and the `sh-sci` probe (M3b). The model does not gate register access on the module clock or MSTOP.
- Clock-synchronous mode, baud-rate enforcement, modem lines (MCE, RTS/CTS), break transmit and receive, the noise filter, DMAC requests.
- Fixing whatever stops the kernel after earlycon.

**Start states (spec §9):** firmware mode starts at Table 22.4. Direct mode starts SCIF0 at the EVK post-firmware values; SCIF1-4 stay at reset, because firmware leaves them unclocked (EVK-R13: CLK_MON SCIF = `0x1`). The values belong to the firmware recorded in `../../evidence/EVK-2026-10-29-post-firmware.md`.

## Evidence

- Registers, flags, IRQs and the firmware TX patterns: `../../research/scif.md` §3-§10 and its EVK results section.
- Post-firmware values and undefined-offset behaviour: `../../evidence/EVK-2026-10-29-post-firmware.md` (EVK-R13, R20-R26, R70).
- Bases, SPIs and gaps: `../../device-map.md` (SCIF rows, §3 rows for SCIF0, §4 rows 6, 12, 13).
- Earlycon path and DTB-U `/chosen`: `../../research/scif.md` §5; DTB-U built by `tests/guests/g0/build-dtb.sh` (SHA-256 `4c339906…`).
- Unmapped windows: DR-0005.

## Decisions (operator, 2026-10-29)

The operator chose the recommended option in each case, in agreement with the Codex design review: **(a) A**, **(b)** as proposed, **(c) B**, **(d) A**. The options stay below for the record.

**(a) Where the hello image lives.** REQ-TEST-001 and spec §17 say `tests/hello-rzv2l`, but that directory is not in the AGENTS.md layout block, which lint checks (lint already warns about the missing path).

| Option | Change |
|---|---|
| **A. `tests/probes/hello-rzv2l/` (recommended)** | Errata to REQ-TEST-001 and spec §17. The hello image is a bare-metal guest program that checks the machine from inside, which is what `tests/probes/` is for. It also reuses the M1 probe's build and semihosting exit |
| B. `tests/hello-rzv2l/` | A new AGENTS.md layout line; no spec change |

**(b) The earlycon boot argument.** DTB-U `/chosen/bootargs` is `ignore_loglevel rw root=/dev/nfs ip=on`, with no `earlycon` (checked on the built DTB-U). In direct mode `-append` replaces the DTB bootargs entirely. Proposal: `-append "ignore_loglevel rw root=/dev/nfs ip=on earlycon"`, which keeps the stock arguments and adds a bare `earlycon` (never `earlycon=scif,…`, which selects the SH4 layout: `scif.md` §5). It is recorded as a fidelity gap; device-map §4 row 6 already lists it, and REQ-GUEST-004 requires it.

**(c) Clock-synchronous mode (SMR.CM = 1).** Ticket 1's S11 asks for `LOG_UNIMP` and no transfer. The project's `device-model` skill (reference §7) says an unsupported mode should return a decode error on the register that selects it. Both are honest-fault; they differ in when the guest notices. No G0/G1/firmware consumer sets CM (`design.md` §2), so this only decides how a wrong guest fails.

| Option | Guest sees | S11 and its mutation |
|---|---|---|
| A. `LOG_UNIMP`, store CM, send nothing | TEND never sets; the guest notices only when a TEND wait times out (TF-A's flush has no timeout, so firmware would hang) | S11 asserts nothing is sent; mutation: transmit anyway |
| **B. Decode error on the SMR write with CM = 1 (recommended)** | an external abort on the write, at once; SMR keeps its old value | S11 asserts SMR is unchanged (qtest cannot see the bus error itself: M1 AC14 note), and a new check A06 in the hello image asserts the CPU takes the abort. An unchanged SMR alone cannot tell a decode error from an ignored write. Mutation: accept the write |

**(d) When the SoC wiring lands.** Ticket 1 says "no SoC wiring yet (part 2)", but S01-S13 run on `-M rzv2l-smarc` and need SCIF0 mapped there (review R4). `-M none` cannot map a sysbus device, so an isolated fixture would need a test-only machine.

| Option | Change |
|---|---|
| **A. Move the SoC wiring (T07) into Part 1 (recommended)** | T07 runs before T05; the qtests run on the real machine, and the M1 expected files are updated in the same part. Part 2 keeps the board-level runs (hello, acceptance, earlycon) |
| B. A test-only machine for the qtests | more fork code that upstream would not want, and the tests would not see the real wiring |

## Open questions (resolved in design unless the operator objects)

1. **Access widths.** The manual gives a width per register but not what silicon does on a wrong width. The model accepts 8-bit and 16-bit accesses; a 32-bit access is refused, so the guest sees a bus error (A). Linux, TF-A and U-Boot use the documented widths.
2. **Undefined offsets beyond `+0x18`.** Only `+0x18` was measured. Read-as-zero is extrapolated to the whole `0x18-0x3FF` range (I). S10 therefore asserts zero plus the log line, and its mutation changes from "read as zero" to "abort instead".
3. **Character time.** It is computed from SMR (CHR, PE, STOP, CKS), BRR, SEMR (BGDM, ABCS0, BRME) and MDDR with the p.1282/p.1287 formulas and P0 = 100 MHz. It is used only for timing (device-map §4 row 13). With TF-A's settings that is 114 836 bit/s, a frame time of about 87 µs.
