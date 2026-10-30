# DR-0003: GIC identity registers

- **Status:** Accepted by the operator: option A
- **Date:** 2026-10-08

## Context

The M1 exit gate (spec §17) requires a qtest showing that the GIC and SYSC identity registers equal the EVK values. QEMU v11.1.2 hard-codes the GIC identity: `gicv3_iidr()` returns `0x43B` for both `GICD_IIDR` and `GICR_IIDR`, and `gicv3_idreg()` supplies fixed PIDR/CIDR values for both the distributor and the redistributor frames.

## Evidence

- qemu v11.1.2 `hw/intc/gicv3_internal.h:749-757` (`gicv3_iidr`); used by `hw/intc/arm_gicv3_dist.c:447,600` and `hw/intc/arm_gicv3_redist.c:355,460`.
- `docs/research/cpu-gic.md`: the Linux `irq-gic-v3` driver and TF-A read these registers. The silicon value is assumed to be a GIC-600 IIDR, not yet measured.
- The EVK boot log confirms GIC-600 sizing (480 SPIs, redistributor frames), but not the identity values.

## Alternatives

| Option | Summary |
|---|---|
| **A. Faithful identity** | Make the identity configurable for the distributor and the redistributors; set it to the measured EVK values |
| B. Accepted gap | Keep `0x43B`; amend the §17 gate |
| C. Defer | Exit M1 on placement only; move the identity check to a later unit |

## Decision

**Option A.** M1 adds identity properties to QEMU's `arm_gicv3`, covering IIDR plus the PIDR/CIDR blocks of both frames. The rzv2l machine sets them to the values measured on the EVK. Until a property is set, QEMU's defaults stay unchanged.

## Amendment (2026-10-09)

The Arm GIC-600 r1p6 TRM (100336_0106_00) documents the identity values. Only the IIDR differs from QEMU: `GICD_IIDR` = `GICR_IIDR` = `0x0201743B` (§4.2.3 Table 4-5, §4.4.1 Table 4-22), while the distributor and redistributor PIDR/CIDR blocks equal QEMU's existing table byte for byte (Table 4-2 p.4-108, Table 4-21 p.4-127). Option A therefore reduces to **one** default-off `iidr` property on `arm_gicv3`. The M1 qtest asserts the TRM values; the EVK reads (EVK-R60–R66) confirm them on silicon, and a disagreement is recorded as a conflict and resolved in favour of silicon.

## Consequences

- The §17 gate stays as written: GICD and GICR identity must equal the EVK.
- **M1 exit needs EVK reads** `EVK-R60`/`R61` (GICD IIDR, PIDR/CIDR) and `EVK-R62`/`R63`/`R65`/`R66` (GICR IIDR and TYPER for both redistributors; the full PIDR/CIDR block of each) from `docs/evidence/requests.md`.
- A generic QEMU change, subject to the project's provenance restrictions (spec §16): an agent-written implementation is a prototype, and any upstream submission needs human-authored code.

## Unknowns

- Whether silicon matches the TRM values (EVK-R60–R66).

## Revisit condition

- The EVK reads show values QEMU cannot represent.
- Upstream QEMU gains an equivalent property: rebase onto it instead.
