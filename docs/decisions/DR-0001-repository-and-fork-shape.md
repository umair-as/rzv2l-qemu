# DR-0001: Repository and QEMU fork shape

- **Status:** Accepted (operator, 2026-10-08)
- **Date:** 2026-10-08

## Context

QEMU has no out-of-tree machine plugins, so the model lives in a QEMU tree. The project also produces material upstream QEMU would never carry:
- the spec, research and evidence
- guest build scripts and oracle captures
- agent instructions
- copyrighted Renesas manuals, as a local index only

Upstream submission is a possible later goal, if the emulation succeeds.

## Evidence

- `qemu-imx93` / `qemu-imx95` are the whole project inside a QEMU fork, with a branch pair (`main` pins upstream, `imx93-dev` carries the port). Their project docs live inside the fork.
- QEMU's code-provenance policy declines AI-generated content (`qemu/docs/devel/code-provenance.rst`).

## Alternatives

1. **Project repo + QEMU fork as a submodule.**
2. The project inside the QEMU fork (the i.MX approach).
3. A patch queue (`patches/*.patch` applied onto pinned QEMU by a script).

## Decision

Option 1:
- Project repo `qemu-rzv2l`.
- Submodule `qemu/` → `github.com/umair-as/qemu`. `rzv2l-base` is pinned at upstream `v11.1.2`; `rzv2l-dev` carries the port and is the fork's default branch.
- Project tags use the `rzv2l-vX.Y` namespace.

## Consequences

- The fork stays upstream-shaped. Agent files, specs and evidence never enter it.
- The method (spec, research, validation) is reusable for a second SoC, independent of this fork.
- Every acceptance result pins the project commit plus the submodule SHA.
- Cost: submodule bumps are explicit commits, and contributors must `git submodule update --init`.
- Development on a stable point release means a rebase onto master is needed before any submission.

## Unknowns

- Whether upstream submission happens at all, which depends on the M3–M5 outcomes and on human-authored code (§16 of the spec).

## Revisit condition

- The start of upstream preparation.
- A need to track QEMU master features that are not in 11.1.x.
