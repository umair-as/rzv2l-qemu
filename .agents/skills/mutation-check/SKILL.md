---
name: mutation-check
description: Prove a qtest, guest probe or acceptance check can fail — break the model with a plausible wrong value, confirm a fresh rebuild, see the exact assertion go red, restore. Use before recording any test as verification (AGENTS.md rule 7).
---

# Mutation check

A test that was never seen to fail proves nothing. Examples with real output: `docs/learning/testing.md` (mutation tables per task).

## Steps

1. **Choose the mutation:** a *plausible* wrong value the test claims to guard, not a crash. Good: a reset value off by one bit, a field moved by one bit, an IRQ line swapped, a timer 3× too long, a flag that clears without the read. Bad: deleting the device (QEMU aborts before any assertion runs).
2. Write it down first: file, the change, and the assertion you expect to fail.
3. Apply it in `qemu/` (a `sed` or one edit). Don't commit it.
4. **Rebuild and confirm the rebuild happened:** `cd build/qemu && ninja qemu-system-aarch64 <test target>` must show a `Linking target` line. If the mutation does not compile, the old binary stays and the test runs green against it: that green means nothing.
5. Kill stale QEMU processes from earlier runs by PID (`pgrep -f qemu-system-aarch64`, then `kill <pid>`). A broad `pkill -f` inside a script can match its own command line.
6. Run only the targeted test. Read the red **line**: it must be the assertion from step 2. A different red (QEMU aborting at startup, a timeout, another case) does not count; choose a better mutation.
7. Restore: `git -C qemu checkout -- <file>`, rebuild, run the test green again.
8. Record in the unit's `tasks.md`: mutation, test, red line (one row each, as in `docs/units/M1-machine-skeleton/tasks.md`).

## Choosing mutations by test type

| Test checks | Mutate |
|---|---|
| a reset/ID value | the constant |
| a field position | the `FIELD()` shift |
| a writable mask | the mask, by one bit |
| a flag clear rule | make the 0-write clear without the prior read |
| a level status | store it instead of computing it |
| an IRQ equation | drop one term, or swap two lines in the SoC |
| a timer completion | complete synchronously in the write handler |
| a memory map / qtree check | move the base, or add a window |
| a log gate | add one extra `LOG_GUEST_ERROR` line |

## Pitfalls

- A test that only checks "a bit is set" survives most value mutations: if the mutation stays green, the test is too weak; strengthen it, don't pick an easier mutation.
- When the model improves, re-run old mutations of negative tests; they can rot green.
- Checker-only tests (e.g. the DTB comparator in `tests/acceptance/m1/check.py`) are mutated through their **input**, not the model.
