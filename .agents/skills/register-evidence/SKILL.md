---
name: register-evidence
description: Build the evidence for one RZ/V2L block before modelling it — registers, reset values, IRQs, clocks and what the guest drivers actually touch — from the hardware manual text and pinned guest sources. Use before writing or extending any device model, or when a guest touches a register the model lacks.
---

# Register evidence

Goal: a short, citable answer to "what does the guest need from this block". Not a survey of the whole chapter.

## Scope from the consumer, not the manual

1. List the guest paths that touch the block at this milestone: the G0 Linux driver, earlycon, and the firmware (TF-A, U-Boot, OP-TEE) if the milestone runs it. Start from the `docs/device-map.md` row ("Guest consumers") and `docs/research/<block>.md`.
2. From those paths, list the registers actually read or written, with `file:line`. Only these need evidence now; everything else is recorded as "not modelled".

## What to collect

- **Manual** (the text extract under `artifacts/rzv2l/text/` for search; cite the **PDF** section/table/page): per register in scope its offset, size, access width, reset value, and per field the access type (R, R/W, R/(W) 0-after-1, W1C, read-to-clear). Check garbled tables against the PDF.
- **Every clearing and setting condition** of each status bit, not just the one the guest uses (e.g. FSR TEND also clears on an FTDR write, p.1281).
- **Guest sequence** (repo + commit + `file:line`, pins in `docs/sources.md`): what is written, what is polled, the timeout, and what happens on timeout.
- **Effective configuration** (rule 3): `.config`, compile log, `conf.mk`, DT `status`. A driver that is `=m` and never loaded in G0 is not a consumer.
- **Field class** (see `device-model` reference §1): config, command, status (level or event), side-effect read.
- **Two start states** (rule 9): the manual reset value, and the post-firmware value for direct-kernel mode. Without an EVK measurement the latter is (I).
- **Labels** on every claim: (F) fact, (I) inference, (O) EVK observation, (A) assumption.
- **Conflicts** (manual vs driver vs silicon): record both, never pick silently. If only the board can settle it, add a question to `docs/evidence/requests.md` (EVK reads follow AGENTS.md "Hardware oracle").

## Output

- The block's rows in `docs/device-map.md` and its note in `docs/research/<block>.md`.
- A table the model and the qtest can be written from directly:

| Offset | Register | Width | Reset (manual) | Direct-mode start | Fields used | Class | Guest `file:line` | Cite |
|---|---|---|---|---|---|---|---|---|

- Before stopping, check the block against the spec §6 evidence list: MMIO range, IRQs and trigger type, clocks/resets, DMA, both start states, guest consumers, manual reference, fidelity and honesty class, unsupported behaviour, verification method. A missing item is either filled or listed as open.

## Traps

- Register counts and FIFO depths come from the manual, never from a driver constant or a sibling SoC.
- "The guest never reads it back" does not make a register plain storage. A write can have effects elsewhere: another register's status, an IRQ, a FIFO, the wire, a reset. Plain storage only when the manual shows no such effect; otherwise model the effect or record the gap.
- A driver that polls a bit needs that bit's real rule, including every condition that sets or clears it.
- Long reads (a whole driver, a firmware tree) can go to research agents; their reports are leads until you check the `file:line` yourself.
- Stop when the table and the §6 check are complete for the consumers in scope.
