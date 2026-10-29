---
name: mutation-check
description: Prove a qtest, guest probe or acceptance check can fail — break the model with a plausible wrong value, confirm a fresh rebuild, see the exact assertion go red, restore. Use before recording any test as verification (AGENTS.md rule 7).
---

# Mutation check

A test that was never seen to fail proves nothing. Examples with real output: the M1 and M2 mutation tables in `docs/learning/testing.md` and `docs/learning/m2-first-character.md` (historical; new units record one line per mutation in `tasks.md`).

## Steps

1. **Choose a plausible wrong value** the test claims to guard, not a crash: a reset value off by one bit, a field moved by one bit, an IRQ line swapped, a timer 3× too long, a flag that clears without the read. Deleting the device is not a mutation (QEMU aborts before any assertion runs).
2. Write down the file, the change and the assertion you expect to fail, before running.
3. Apply it in `qemu/`, uncommitted, in a form you can reverse exactly (a saved patch of just that change).
4. **Rebuild and confirm the binary was actually relinked.** A mutation that fails to compile leaves the old binary, and the test runs green against it: that green means nothing.
5. Make sure no QEMU from an earlier run is still alive (stop it by PID; a `pkill -f` pattern can match your own shell).
6. Run only the targeted test. The red **line** must be the assertion from step 2. A different red (startup abort, timeout, another case) does not count: choose a better mutation.
7. **Reverse only the mutation.** Never `git checkout -- <file>`: it also throws away your uncommitted work in that file. Confirm the file's diff is your own work again, rebuild, and see the test green.
8. Record it as one line in the unit's `tasks.md`: the exact code change → the red line. No patch file, no eval entry, no learning-doc table (AGENTS.md "Record each proof once").

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

## Traps

- A test that only checks "a bit is set" survives most value mutations. If the mutation stays green, strengthen the test; don't pick an easier mutation.
- When the model improves, re-run old mutations of negative tests; they can rot green.
- Never pipe a check (build, `checkpatch`, qtest, `scripts/lint.py`) through `tail`, `head` or `grep` in a way that hides its exit status: a failed check then looks like a pass, and the next step (a commit, a push) runs anyway. Use `set -o pipefail`, or run the check on its own line and test `$?` before going on.
- Checker-only tests (e.g. the DTB comparator in `tests/acceptance/m1/check.py`) are mutated through their **input**, not the model.
