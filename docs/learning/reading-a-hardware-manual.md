# Reading a hardware manual and corroborating it

## Three sources of truth, three questions

Modelling a device means reconciling three sources, each authoritative for a different question:

| Source | Answers | Typical failure |
|---|---|---|
| **Hardware manual** | What *should* the register do? Layout, bit meaning, reset value. | Errata, copy-paste errors between sibling SoCs (the RZ/V2L device-ID table row carries the RZ/G2L value) |
| **Guest code** (Linux driver, TF-A, U-Boot) | Which bits does software actually *use*, and how? | Reads only some bits; may rely on undocumented behaviour |
| **The real board** | What does the silicon *actually* do? | Can only be observed, not explained |

A model is right when all three agree. When they disagree, the disagreement is itself the finding: record it, never silently pick one.

## Anatomy of a register page

Every register section in the RZ manual has the same parts. Using `CPG_RST_SCIF` (§7.2.4.135, p.409) as the example:

1. **Title and purpose.** "Reset Control Register SCIF … controls the reset signals for individual modules."
2. **Bit diagram.** Two rows of 16 bits (31–16, then 15–0), each with:
   - **Bit name**, e.g. `UNIT0_RSTB`. A `B` or `_N` suffix often means *active low*: 0 = asserted.
   - **Initial Value**: the value after power-on reset. This is what the model must return before anyone writes.
   - **R/W**, the access type:
     - `R`: read-only
     - `RW`: read/write
     - `R0W1`: always reads 0; writing 1 has an effect. Typical of write-enable and "clear" bits.
3. **Bit description table.** What each value means. **Read this, not just the name.** Polarity lives here: on p.409, 0 = reset *applied*, while on p.450 (the monitor) 1 = reset applied.

## Recurring patterns in this SoC

- **Write-enable halves.** Many CPG registers have `*_WEN` bits in [31:16] guarding the data bits in [15:0]. Software writes `(mask << 16) | value`, and only bits whose WEN is set change. The model must honour this; ignoring it lets software corrupt neighbouring bits.
- **Control and monitor pairs.** A control register (software writes) plus a monitor register (hardware reports). Drivers write, then *poll* the monitor with a timeout. The polarity of the pair is decided page by page, not by assumption.
- **Reserved bits.** "Whenever it is read, 0 is read. The written value will be ignored." The model must do exactly that.

## How to verify a research claim

1. Take a claim from a note, e.g. "RSTMON is the inverse of RST".
2. Open the cited manual page and read the bit description, not the summary table.
3. Open the cited driver line and check the code polls for exactly that meaning.
4. If the board is available, read the register at a known boot stage (U-Boot `md.l <addr> 1`) and compare.
5. Matching? The claim is verified. Not matching? Record which source says what.

## Classifying a bit for the model

When deciding how a register behaves in QEMU, triage each field:

| Class | Behaviour | Model as |
|---|---|---|
| Config | write persists, read returns the last write | plain storage |
| Command | write triggers an action; hardware self-clears | action + read back 0 |
| Status | reflects hardware state | computed on read (a mirror, a timer, a FIFO level) |

A plain read/write register is *wrong* for command and status bits: a poll loop either spins forever or "succeeds" without the effect happening. That is the silent-wrong failure the project forbids.

## Boot stage matters

A register read means different things at different times:

| Stage | What you see |
|---|---|
| Power-on reset | the manual's Initial Value |
| After TF-A / U-Boot | the "post-firmware" state; what QEMU's direct-kernel mode must reproduce |
| After Linux | whatever drivers left; neither of the above |

Always write down the stage with a measurement.
