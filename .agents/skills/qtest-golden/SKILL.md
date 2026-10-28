---
name: qtest-golden
description: Write a qtest for an RZ/V2L device model that asserts hardware-manual values (reset values, ID registers, flag rules, IRQ lines) rather than the model's own output. Use for every new or changed register behaviour in the qemu/ fork.
---

# qtest with manual goldens

The machine qtest is `qemu/tests/qtest/rzv2l-smarc-test.c` (under `CONFIG_RZV2L_SMARC`); a large block may get its own `<block>-test.c`. Background: `docs/learning/testing.md` §1.

## Steps

1. **Goldens first:** expected values as `#define`s, each citing its source (manual section/table/page, TRM table, or EVK evidence file). A number that came from running the model is not a golden: delete it.
2. **One test per behaviour**, named `/aarch64/rzv2l-smarc/<block>/<behaviour>`. By class:
   - reset values of every register in scope
   - config: write, read back, writable mask (write all-ones, expect only the R/W bits)
   - command: the bit reads 0 when done (advance virtual time if it completes on a timer)
   - status: drive the state (fill a FIFO, change a trigger) and assert the flag follows
   - clear rules: a 0-write without a prior 1-read must **not** clear a read-armed flag; after the read it must
   - side-effect reads: two reads give the documented sequence
   - IRQ line equations: intercept the **device's outputs** (`qtest_irq_intercept_out` on its QOM path, e.g. `/machine/soc/<child>`), then toggle enable and flag bits through the manual's equation and assert each line
   - properties: each board property value changes the register as documented; invalid values refuse to start (as `boot-mode-reserved` does)
3. **Sweep the axis the register exposes:** at least two values per field that changes timing or thresholds. One value is one shape, and a hardwired model passes it.
4. Run `mutation-check` on every new case before calling it verified.
5. Record the test and its mutation in the unit's `tasks.md` (Test and Mutation columns), and the red line in the task's mutation table in `docs/learning/testing.md`.

## Limits of qtest (use `guest-probe` instead)

- qtest's IRQ interception holds 256 lines (`MAX_IRQ` in `system/qtest.c` and `libqtest.c`). Intercepting GIC inputs for SPIs ≥ 256 (all SCIFs) overflows it. Check the GIC routing (SPI → INTID at the CPU) with a probe.
- Bus errors read as 0: aborts, exception levels, PSCI and timer frequency need a probe.
- No CPU runs: a read between a write and a timer completion is only approximated by stepping the clock. Firmware access-order bugs (SCIFA TEND) need a probe that replays the firmware's sequence.

## Traps

- A range is not a golden: "between 1 and 100" passes a 3× wrong value.
- "An IRQ fired" or "a bit set" is not a value check: assert the exact register value and the exact line.
- A golden computed from another model value (e.g. a period from the model's clock) moves with the bug. Anchor it on the manual or the guest's intent.
