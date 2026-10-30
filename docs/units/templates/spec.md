# <unit> — spec

**Milestone:** M?. **Requirements:** REQ-…. **Status:** written <date>; implementation follows.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A).

## Scope
Per block: base, size, model name, fidelity class (`../../device-map.md`). The registers modelled and their rules, each with its manual section, table and page. The two start states (reset values; post-firmware values with `-kernel`, from EVK rows). Source conflicts, recorded. **Not modelled:** …

## What the guest needs
The pinned guest code (`file:line`) and the registers it touches, in the order it touches them.

## Exit criterion
What the boot (or probe) shows when the unit is done, and where it is expected to stop next.

## Evidence
Manual sections and pages; `../../research/…`; EVK rows (`../../evidence/…`).

## Next blocker (<date>, fork `<sha>`)
Written at the end: the boot's last lines, the cause, the layer verified, and the coverage list (`-d unimp,guest_errors,invalid_mem`: window, class, guest outcome).
