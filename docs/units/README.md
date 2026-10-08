# Work units

A work unit is one reviewable slice of a milestone, for example `M1-machine-skeleton`. Each unit lives in its own folder:

```
docs/units/<unit>/
├── spec.md     what and why: REQ IDs, EARS acceptance criteria, scope, non-goals
├── design.md   how: model structure, register behaviour, start states, evidence pointers
└── tasks.md    ordered tasks with stable IDs, each tied to REQs, files and a test
```

**Lifecycle:**
1. `spec.md` is drafted from `../spec/requirements.md`, `../device-map.md` and the research notes.
2. The operator reviews the spec. Nothing is implemented before that.
3. `design.md` and `tasks.md` are written; DRs are opened where alternatives exist.
4. Tasks are implemented on the QEMU fork's `rzv2l-dev` branch, one task per commit where practical. Commit messages name the task ID.
5. Each task closes only when its test passes; `../spec/traceability.md` is updated.
6. The unit closes after a consistency check: every REQ appears in a task, every task names a test, and every test result is recorded.

Templates are in `templates/`.
