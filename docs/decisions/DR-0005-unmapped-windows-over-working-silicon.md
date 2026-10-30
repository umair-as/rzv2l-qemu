# DR-0005: Unmapped windows over working silicon

- **Status:** Accepted by the operator
- **Date:** 2026-10-29

## Context

Spec §7 allows an unmapped region (the guest takes a synchronous external abort) only for "UNSUPPORTED regions the board also faults on". M1 leaves everything outside RAM, the GIC and SYSC unmapped. Most of that address space is working silicon, so M1 and the next milestones already rely on a case §7 does not allow (open question R23).

The alternatives were to map every DTB-U window as a placeholder from the start, or to allow the abort as a recorded gap. A placeholder that reads zero is silent-wrong wherever the silicon reset value is not zero, and the alternative is unmapped, which the guest sees as an abort.

## Evidence

- The EVK reads of 2026-10-29 (`../evidence/EVK-2026-10-29-post-firmware.md`) show both behaviours on silicon: undefined offsets inside working blocks read zero (SCIF0 `+0x18`, PFC `+0x3100`), and SYSC access-control registers abort from the non-secure side. The silicon does not answer "abort or zero" uniformly, so each window needs its own decision.
- M1's AC14 (`../units/M1-machine-skeleton/spec.md`) keeps every address outside the M1 windows unmapped, and its probe shows the abort.

## Decision

An unmapped window over working silicon is allowed as a **recorded fidelity gap** only when both conditions hold:

1. the coverage list shows that no guest at the current milestone touches the window, and
2. the window is listed in `../device-map.md` §4 for the M3b per-window review (REQ-MAP-001).

An abort is **honest-fault**, not silent-wrong: the guest sees the failure. A window a guest at the current milestone does touch must be modelled, or must be a listed STUB under the existing §7 rules, before that milestone is accepted.

## Consequences

- Spec §7 gets one mechanism row for this case (v0.3 erratum 2026-10-29).
- Each unit's acceptance run checks its coverage list against the unmapped windows. A guest access to one of them is a failure to fix, not a gap to record.
- The M3b per-window review decides each window: modelled, STUB, or kept unmapped because the board faults there too.
