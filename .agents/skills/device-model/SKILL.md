---
name: device-model
description: Write or extend a QEMU device model for an RZ/V2L block in the qemu/ fork — register file, reset and start states, IRQ lines, timers, chardev, honest faults, trace points. Use when implementing a NEW block from docs/device-map.md or fixing a model behaviour a guest depends on.
---

# Device model

Input: the evidence table from `register-evidence`, and the reviewed unit spec. Code goes in the fork (`qemu/`), upstream style. Code patterns: [reference.md](reference.md).

## Steps

1. **Start from the closest model**, not from scratch: this project's `qemu/hw/misc/renesas_rzg2l_sysc.c` (REG32/FIELD, decode errors for unmodelled offsets, trace points, properties), or a QEMU model named in `docs/research/<block>.md`. Borrow structure, not semantics: check every borrowed behaviour against the evidence table.
2. **Register file:** one `REG32`/`FIELD` per register and field in scope. Access sizes in `.valid` as the manual allows; QEMU then refuses other sizes (logged under `invalid_mem`).
3. **Per field, its class** (reference §1). Status bits are computed from model state on read, never stored as a constant.
4. **Two start states** (rule 9): manual reset values in the reset hold phase; the direct-kernel start state behind a property (default off) set by the board and documented in the header.
5. **IRQs:** one `update_irq()` implementing the manual's line equations, called after every state change (reference §3).
6. **Time:** anything the silicon takes time to do completes on a virtual-clock timer, not in the write handler, when any guest reads status between trigger and completion (reference §4).
7. **Unmodelled parts fail honestly** (rule 6, reference §7). A default that hides a missing input (e.g. a clock) is a bug: make it fail visibly.
8. **State:** a `VMStateDescription` with every guest-visible field, timers included.
9. **Header comment:** manual section, what is modelled, what is not.
10. Build out-of-tree under `build/qemu` (never inside `qemu/`). If no machine selects the new Kconfig yet, compile-check it by hand (`docs/learning/building-and-testing.md` §2).
11. `scripts/checkpatch.pl --no-signoff` clean, on the uncommitted diff (new files added with `git add -N`) or, once committed, on `rzv2l-base..HEAD`.

Then: `soc-wiring`, `qtest-golden`, `mutation-check`.

## Rules that bite

- No invented status bits, no arbitrary constants, no `x ?: DEFAULT` for an input that should be wired. A value without evidence is an experiment (`docs/experiments/`).
- Model all of what the consumer polls: if a poll loop walks several status bits, every bit it can read.
- Don't extend a QEMU model whose semantics conflict with the manual (e.g. `hw/char/sh_serial.c` vs SCIFA, `docs/research/scif.md` §9). Write a new type.
- The fork carries only upstream-shaped code: no project paths, spec IDs or agent files.
