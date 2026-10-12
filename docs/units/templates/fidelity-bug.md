# FB-NNN: <short title>

**Found in:** unit / milestone, guest (G0/G1/G2), QEMU commit
**Layer verified:** e.g. "register model", "driver probe", "boot sequence"

## Observed (current behaviour)
What the guest sees in QEMU: log excerpt, register trace (`-d unimp,guest_errors,invalid_mem`, trace events).

## Expected (with evidence)
What the hardware does: manual section/page, driver file:line, EVK measurement (boot stage).

## Unchanged (must not regress)
Behaviour and tests that must stay as they are after the fix.

## Root cause
At layer N the cause is X (spec rule: name the layer you verified).

## Fix and verification
Commit, test added, mutation check.
