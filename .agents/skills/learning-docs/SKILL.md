---
name: learning-docs
description: Write, extend or rewrite files in docs/learning/ for qemu-rzv2l. Use whenever an explanation for the operator must land in the learning docs (AGENTS.md "Explanations land in the repo"), when a new milestone needs its learning file, or when a learning doc is restyled.
---

# Learning docs

The rules live in the repo, not here: `docs/learning/STYLE.md` (adapted Simple Technical English) and `docs/learning/README.md` (file list, conventions). This skill is only the procedure.

## Steps

1. Read `docs/learning/STYLE.md` and `docs/learning/README.md` in full. Follow them over anything below.
2. Choose the file:
   - a general QEMU concept → `qemu-basics.md`
   - how a test works → `testing.md`
   - a milestone's machine or devices → that milestone's file (`m1-machine-tour.md`; for a new milestone, a new `mN-<topic>.md` with the context box from STYLE.md §4.4, and a row in README.md)
   - commands → `building-and-testing.md`
   - a new term → `glossary.md` and STYLE.md §5
3. Write from real evidence: monitor output, test output, code with `file:line`. Run the command; do not invent output.
4. Link every project file and section (relative Markdown links; anchors from the heading text).
5. For a rewrite: copy the old version to a temporary location first, then run `scripts/doc-facts.py <old> <new>`. It must report "same facts". Any difference is either a mistake to fix or a deliberate change to name to the operator.
6. Run `scripts/lint.py style links`. Style hints are advisory (the operator wants loose rules): fix those that make the text clearer, keep the rest. More detail is welcome where a topic needs it.
7. Check links resolve to real headings (lint `links` checks files only; anchors need a manual or scripted check).
8. Show the operator the result. Do not commit until they have read it (they batch learning-doc commits).

## Pitfalls

- Shortening sentences must not drop a qualifier ("only", "in M1", "with `-kernel`"). Re-read each split sentence against the original.
- Keep quotations from QEMU docs verbatim, even if they break the style; they are quotes.
- Never put host paths, the operator's working area (`$RZV2L_WORKAREA`) or agent tooling paths (`.agents/`, `.claude/`) in the docs.
