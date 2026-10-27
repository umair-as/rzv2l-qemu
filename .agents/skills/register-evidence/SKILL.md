---
name: register-evidence
description: Build the evidence for one RZ/V2L block before modelling it — registers, reset values, IRQs, clocks and what the guest drivers actually touch — from the hardware manual text and pinned guest sources. Use before writing or extending any device model, or when a guest touches a register the model lacks.
---

# Register evidence

Goal: a short, citable answer to "what does the guest need from this block", fast. Not a survey of the whole chapter.

## Scope first (the step that saves the most time)

1. Start from the **consumer**, not the manual. List the guest paths that touch the block at this milestone: G0 Linux driver, earlycon, firmware (TF-A, U-Boot, OP-TEE) if the milestone runs it. `docs/device-map.md` row "Guest consumers" is the starting list; `docs/research/<block>.md` may already answer most of it.
2. From those paths, list the **registers actually read or written**, with `file:line`. Only these registers need evidence now. Everything else is "not modelled", recorded as such.

## Steps

1. Manual: `rg -n '<REG>|<block>' artifacts/rzv2l/text/hardware/r01uh0936ej0150-rzv2l.txt`. For each register in scope get offset, size, access width, reset value, and per field the access type (R, R/W, R/(W) 0-after-1, W1C, read-to-clear). Cite the **PDF** section/table/page, not the text file. Check tables against the PDF itself when the extract looks garbled.
2. Guest source: cite repository + commit + `file:line` (pins in `docs/sources.md`). Record the exact sequence: what is written, what is polled, with which timeout, and what happens on timeout.
3. Effective configuration (rule 3): confirm the path is built — `.config`, compile log, `conf.mk`, DT `status`. A driver that is `=m` and never loaded in G0 is not a consumer.
4. Classify each field the guest touches (see `device-model` reference):
   - config (write persists, read returns last write)
   - command (self-clears when done)
   - status (reflects model state; level or event)
   - side-effect read (FIFO pop, read-to-clear, read-arms-clear)
5. Note the **two start states** (rule 9): manual reset value, and the post-firmware value for direct-kernel mode. A post-firmware value without an EVK measurement is an inference, labelled (I).
6. Label every claim (F) fact / (I) inference / (O) EVK observation / (A) assumption.
7. Conflicts (manual vs driver vs silicon): record both, never pick silently. If only the board can settle it, add a question to `docs/evidence/requests.md`; EVK reads follow the AGENTS.md "Hardware oracle" rules.

## Output

- Update or add the block's rows in `docs/device-map.md` and its note in `docs/research/<block>.md`.
- End with a table the model and the qtest can be written from directly:

| Offset | Register | Width | Reset (manual) | Direct-mode start | Fields used | Class | Guest `file:line` | Cite |
|---|---|---|---|---|---|---|---|---|

## Pitfalls

- Register **counts** and FIFO depths come from the manual, never from a driver constant or a sibling SoC.
- A driver that writes a register and never reads it back needs storage, not behaviour. A driver that polls a bit needs that bit's real rule.
- Delegate long reads (a whole driver, a firmware tree) to `manual-researcher` / `guest-researcher` agents if present; their reports are leads until you check the `file:line` yourself.
- Stop when the table is complete for the consumers in scope. More reading belongs to a later milestone.
