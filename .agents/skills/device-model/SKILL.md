---
name: device-model
description: Write or extend a QEMU device model for an RZ/V2L block in the qemu/ fork — register file, reset and start states, IRQ lines, timers, chardev, honest faults, trace points. Use when implementing a NEW block from docs/device-map.md or fixing a model behaviour a guest depends on.
---

# Device model

Input: the evidence table from `register-evidence`, and the unit spec. Code goes in the fork (`qemu/`), upstream style. Patterns with code: [reference.md](reference.md).

## Steps

1. **Pick the template.** Start from the closest existing model, not from scratch:
   - this project: `qemu/hw/misc/renesas_rzg2l_sysc.c` (REG32/FIELD, `MEMTX_DECODE_ERROR` for unmodelled offsets, trace points, properties)
   - QEMU: the reuse candidates named in `docs/research/<block>.md` (e.g. `hw/char/renesas_sci.c` for a character-time TX timer)
   Reuse ideas, not semantics: check every borrowed behaviour against the evidence table.
2. **Files:** `qemu/hw/<class>/renesas_<block>.c`, `qemu/include/hw/<class>/renesas_<block>.h`, a `config` in `qemu/hw/<class>/Kconfig`, a `meson.build` line, and trace events in `qemu/hw/<class>/trace-events`.
3. **Register file:** one `REG32`/`FIELD` per register and field in scope, offsets and widths from the evidence. Set `.valid` access sizes to what the manual allows; QEMU then refuses other sizes (logged under `invalid_mem`).
4. **Per field, implement its class** (reference §1): config, command, status (level vs event), side-effect read. Status bits are computed from model state on read, never stored as a constant.
5. **Two start states** (rule 9): reset values from the manual in the reset hold phase; the direct-kernel start state as a property (default off) set by the board, documented in the header.
6. **IRQs:** write one `<block>_update_irq()` that implements the manual's line equations and call it after every state change (reference §3). Never raise an IRQ from inside a register write path ad hoc.
7. **Time:** anything the silicon takes time to do (a character on the wire, a conversion, a reset release) completes on a `QEMU_CLOCK_VIRTUAL` timer, not inside the write handler, when any guest reads status between the trigger and the completion (reference §4).
8. **Unmodelled parts fail honestly** (rule 6): an unmodelled offset returns `MEMTX_DECODE_ERROR` with `LOG_UNIMP`; an unsupported mode sets the block's own error status if it has one. Never return success or a plausible value for work the model did not do. A default that hides a missing input (e.g. a clock) is a bug: make a missing input fail visibly.
9. **State:** a `VMStateDescription` with every guest-visible field, timers included.
10. **Comment the evidence** in the file header: manual section, what is modelled, what is not.
11. Build out-of-tree: `cd build/qemu && ninja qemu-system-aarch64`. Never build inside `qemu/`. If no machine selects the new Kconfig yet, compile-check by hand (`docs/learning/building-and-testing.md` §2).
12. `cd qemu && git add -N <new files> && git diff | scripts/checkpatch.pl --no-signoff -` must be clean.

Then: `soc-wiring` to put it in the machine, `qtest-golden` to test it, `mutation-check` to prove the test.

## Rules that bite

- No invented status bits, no arbitrary constants, no `x ?: DEFAULT` for an input that should be wired. If the evidence does not give a value, it is an experiment (`docs/experiments/`).
- Model what the consumer **polls**, all of it: if a poll loop walks several status bits, model every bit it can read, not just the first.
- Don't extend a QEMU model whose semantics conflict with the manual (e.g. `hw/char/sh_serial.c` vs SCIFA, `docs/research/scif.md` §9). Write a new type.
- The fork carries only upstream-shaped code: no project paths, no spec IDs, no agent files.
