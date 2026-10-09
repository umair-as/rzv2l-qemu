# <unit> — tasks

| ID | Task | REQ / AC | Files | Test | Status |
|---|---|---|---|---|---|
| <unit>-T01 | … | REQ-… / AC01 | `hw/…` | `tests/qtest/…` | TODO / DONE |

## Closure checklist (before closing the unit)
- [ ] every REQ in spec.md appears in at least one task
- [ ] every task names a test; each test's result **and** its mutation check (the test seen to fail on a broken model) are recorded
- [ ] `../../spec/traceability.md` updated; `scripts/lint.py` reports 0 errors
- [ ] independent review done on the final revision: project commit `…`, fork commit `…`
- [ ] every review finding has a disposition (fixed / gap / rejected with evidence); **no unresolved BLOCKER**, since a recorded blocker is still a blocker
- [ ] material fixes rechecked by the reviewer on that final revision
- [ ] fidelity gaps accepted by the operator are listed
