---
name: qtest-golden
description: Write a qtest for an RZ/V2L device model that asserts hardware-manual values (reset values, ID registers, flag rules, IRQ lines) rather than the model's own output. Use for every new or changed register behaviour in the qemu/ fork.
---

# qtest with manual goldens

The machine qtest is `qemu/tests/qtest/rzv2l-smarc-test.c` (registered in `qemu/tests/qtest/meson.build` under `CONFIG_RZV2L_SMARC`). Add cases there, or a new `<block>-test.c` when it grows large. Background: `docs/learning/testing.md` §1.

## Steps

1. **Goldens first.** Write the expected values as `#define`s at the top, each with its source in a comment (manual section/table/page, TRM table, or EVK evidence file). If a number came from running the model, it is not a golden: delete it.
2. **One test per behaviour**, named `/aarch64/rzv2l-smarc/<block>/<behaviour>`. Cover what the guest depends on, by class:
   - reset values of every register in scope
   - config: write, read back, writable mask (write all-ones, expect only the R/W bits)
   - command: write, then the bit reads 0 when done (advance time with `qtest_clock_step` if it completes on a timer)
   - status: drive the state (fill a FIFO, change a trigger) and assert the flag follows
   - clear rules: a 0-write without a prior 1-read must **not** clear a read-armed flag; after the read it must
   - side-effect reads: two reads give the documented sequence
   - IRQ lines: `qtest_irq_intercept_in(qts, "/machine/soc/gic")`, then `qtest_get_irq(qts, n)` for SPI n, toggling enable and flag bits through the manual's equation
   - properties: each board property value changes the register as documented; invalid values refuse to start (`g_test_trap_subprocess`, as `boot-mode-reserved` does)
3. **Sweep the axis the register exposes.** One prescaler or one trigger level is one shape; a model hardwired to that shape passes. Test at least two values per field that changes timing or thresholds.
4. Build and run:
   ```bash
   cd build/qemu
   ninja qemu-system-aarch64 tests/qtest/rzv2l-smarc-test
   QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-smarc-test
   ```
   One case: add `-p /aarch64/rzv2l-smarc/<block>/<behaviour>`.
5. Run `mutation-check` on every new case before calling it verified.
6. Record in the unit's `tasks.md`: the test name, the mutation and the red line it produced.

## Limits of qtest (use a guest probe instead)

- qtest discards transaction results: a bus error reads as 0 (`docs/learning/testing.md` §1). Aborts, exception levels, PSCI and timer frequency need `guest-probe`.
- qtest runs no CPU: anything that depends on the guest's timing (a read between a write and a timer completion) is only approximated by `qtest_clock_step`. Firmware-sequence bugs (SCIFA TEND) need a probe that replays the firmware's access order.

## Pitfalls

- A range is not a golden. "Between 1 and 100" passes a 3× wrong value.
- "An IRQ fired" or "a bit set" is not a value check. Assert the exact register value and the exact line.
- A golden derived from another model value (e.g. expected period computed from the model's clock) moves with the bug. Anchor it on the manual or the guest's intent.
