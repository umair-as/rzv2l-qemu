# Traceability

Requirement → unit → tasks → tests → evidence (spec §15). `requirements.md` is canonical for statements and status; this table only links.

**Columns:**
- **Implemented in:** where the behaviour is built.
- **Accepted in:** the milestone whose test proves it. These may differ: e.g. EL1 entry is configured in M1 but only proven when Linux boots in M3.
- **Unit / Tasks / Tests:** filled only when a unit's `tasks.md` exists. "—" means *not yet planned*, never "done".

| REQ | Implemented in | Accepted in | Unit | Tasks | Tests | Evidence | Status |
|---|---|---|---|---|---|---|---|
| REQ-MACH-001 | M1 | M1 | M1-machine-skeleton (proposed) | — | — | `../device-map.md` | P |
| REQ-MACH-002 | M1 | M1 (MPIDR/MIDR via test ELF) | M1-machine-skeleton (proposed) | — | — | `../research/cpu-gic.md`; EVK boot log | P |
| REQ-MACH-003 | M1 | M1 (test ELF reads CNTFRQ); M3 (Linux `arch_timer` line) | M1-machine-skeleton (proposed) | — | — | `../research/cpu-gic.md`; EVK boot log | P |
| REQ-MACH-004 | M1 (`has_el2=false`, SMC conduit) | M3 (Linux reports EL1, PSCI works) | M1-machine-skeleton (proposed) | — | — | EXP-001; EVK boot log | P |
| REQ-MACH-005 | M7 | M7 (BL31 CPU_OFF runs) | — | — | — | EXP-001 | P |
| REQ-MACH-006 | M1 | M1 (`info mtree`); M3 (`/proc/iomem`) | M1-machine-skeleton (proposed) | — | — | `../research/cpu-gic.md` | P |
| REQ-MACH-007 | M1 | M1 (placement + GICD/GICR identity == EVK, DR-0003 option A; needs EVK-R60–R66) | M1-machine-skeleton (proposed) | — | — | `../research/cpu-gic.md`; EVK boot log | P |
| REQ-MACH-008 | M1+ (per device) | each device's milestone | — | — | — | `../device-map.md` | P |
| REQ-SYSC-001 | M1 | M1 | M1-machine-skeleton (proposed) | — | — | `../research/sysc.md`; EVK BL2 print `0x18447447` | P |
| REQ-SYSC-002 | M1 (board property) | M7 (BL2/U-Boot boot-device selection) | — | — | — | `../research/sysc.md`; EVK BL2 LSI_MODE values | P |
| REQ-SYC-001 | M7 | M7 | — | — | — | `../research/sysc.md` §5 (inference); EVK-R50 pending | P |
| REQ-SCIF-001 | M2 | M2 (qtest + hello); M3 | — | — | — | `../research/scif.md` | P |
| REQ-CPG-001 | M3b | M3b | — | — | — | `../research/cpg-reset.md`; HW manual p.327/368/409/450 | P |
| REQ-PFC-001 | M3b | M3b | — | — | — | `../research/pinctrl.md` | P |
| REQ-OSTM-001 | M3b | M3b | — | — | — | `../research/boot-dependency-graph.md`; EVK boot log | P |
| REQ-IRQC-001 | M3b | M3b | — | — | — | `../research/boot-dependency-graph.md` | P |
| REQ-MAP-001 | M1 (initial classification) → M3b | M3b | — | — | — | `../device-map.md` | P |
| REQ-WDT-001 | M4 | M4 | — | — | — | `../research/boot-chain-firmware.md` | P |
| REQ-TSIP-001 | M7 | M7 (Stage N negative test) | — | — | — | `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-001 | — (process) | M3 | — | — | — | spec §8 | P |
| REQ-GUEST-002 | — (process) | M3 | — | — | — | spec §8 | P |
| REQ-GUEST-003 | — (process) | M7 | — | — | — | spec §8; `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-004 | — (process) | M3 | — | — | — | spec §8; `../research/scif.md` (earlycon gap) | P |
| REQ-GUEST-005 | M4 (loader) | M4 | — | — | — | `../research/boot-chain-firmware.md` §4 | P |
| REQ-TEST-001 | M2 | M2 | — | — | — | spec §17 | P |
| REQ-TEST-002 | M1+ | every unit | — | — | — | spec §13 | P |
| REQ-TEST-003 | M3+ | M3+ | — | — | — | spec §13 | P |
