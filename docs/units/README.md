# Work units

A work unit is one reviewable slice of a milestone. Each unit has a folder here, named `<milestone><stage>-<block>`: M3 has two stages, M3a (earlycon output, done inside `M2-first-character`) and M3b (the `sh-sci` console to a shell), so `M3b-cpg`, `M3b-ostm` and `M3b-pfc-irqc` are steps of M3b.

```
docs/units/<unit>/
├── spec.md     one page: scope, what the guest needs, exit criterion, evidence
└── tasks.md    tasks and tests, one proof line per test, boot evidence
```

M1 and M2 also have a `design.md` from the earlier three-file form.

**Lifecycle** (AGENTS.md "How work flows"):
1. `spec.md` from `../device-map.md`, `../research/` and the EVK evidence; implementation follows on branches `unit/<unit>` in both repos.
2. Each test is proven once: one line in `tasks.md`, the mutation and the red line.
3. The boot loop runs to the next blocker; `spec.md` records it with the coverage list.
4. One independent review round (`templates/review-prompt.md`) plus at most one recheck of the fixes; the PR body gets a short Review fixes list.
5. At its end: the unit's learning page (`../learning/`) and the progress page (`../milestones.md`).

Templates: `templates/spec.md`, `templates/tasks.md`, `templates/review-prompt.md`, and `templates/fidelity-bug.md` for a model that is found wrong.
