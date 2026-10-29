# Traceability

Requirement → unit → tasks → tests → evidence (spec §15). `requirements.md` is canonical for statements and status; this table only links.

**Columns:**
- **Implemented in:** where the behaviour is built.
- **Accepted in:** the milestone whose test proves it. These may differ: e.g. EL1 entry is configured in M1 but only proven when Linux boots in M3.
- **Unit / Tasks / Tests:** filled only when a unit's `tasks.md` exists. "—" means *not yet planned*, never "done".

| REQ | Implemented in | Accepted in | Unit | Tasks | Tests | Evidence | Status |
|---|---|---|---|---|---|---|---|
| REQ-MACH-001 | M1 | M1 | M1-machine-skeleton | M1-T03, T04, T06 | acceptance `-M help`, `info qtree`; qtest `rzv2l-smarc-test` | `../device-map.md` | V |
| REQ-MACH-002 | M1 | M1 (MPIDR/MIDR via test ELF) | M1-machine-skeleton | M1-T03, T05 | probe (MPIDR, MIDR of both CPUs) | `../research/cpu-gic.md`; EVK boot log | V |
| REQ-MACH-003 | M1 | M1 (test ELF reads CNTFRQ); M3 (Linux `arch_timer` line) | M1-machine-skeleton | M1-T03, T05 | probe (`CNTFRQ_EL0`) | `../research/cpu-gic.md`; EVK boot log | D |
| REQ-MACH-004 | M1 (`has_el2=false`, SMC conduit) | M3 (Linux reports EL1, PSCI works) | M1-machine-skeleton | M1-T04, T05 | probe (`CurrentEL` = 1, `ID_AA64PFR0_EL1.EL2` = 0, PSCI `CPU_ON` over SMC); the security state cannot be read from EL1, not checked | EXP-001; EVK boot log | D |
| REQ-MACH-005 | M7 | M7 (BL31 CPU_OFF runs) | — | — | — | EXP-001 | P |
| REQ-MACH-006 | M1 | M1 (`info mtree`); M3 (`/proc/iomem`) | M1-machine-skeleton | M1-T04, T06, T07 | acceptance `info mtree -f`, `info roms`, `dumpdtb` vs DTB-U | `../research/cpu-gic.md` | D |
| REQ-MACH-007 | M1 | M1 (placement + GICD/GICR identity == EVK, DR-0003 option A; TRM values; EVK-R60–R66 confirm on silicon) | M1-machine-skeleton | M1-T01, T03 | qtest `arm-gicv3-iidr-test`; qtest `rzv2l-smarc-test` `/gic/layout`, `/gic/identity` | `../research/cpu-gic.md`; EVK boot log; `../evidence/EVK-2026-10-29-post-firmware.md` (R60-R66) | V |
| REQ-MACH-008 | M1+ (per device) | each device's milestone | M1-machine-skeleton | M1-T03, T06 | acceptance `info mtree -f`, `info qtree` (vs `device-map.md`); M1 has no SPI devices, PPI wiring untested until M3 | `../device-map.md` | D |
| REQ-SYSC-001 | M1 | M1 | M1-machine-skeleton | M1-T02, T05 | qtest `rzv2l-smarc-test` `/sysc/id`; probe (abort on a non-ID offset) | `../research/sysc.md`; EVK BL2 print `0x18447447` | V |
| REQ-SYSC-002 | M1 (board property) | M7 (BL2/U-Boot boot-device selection) | M1-machine-skeleton | M1-T02 | qtest `rzv2l-smarc-test` `/sysc/boot-pins`, `/sysc/boot-mode-reserved` | `../research/sysc.md`; EVK BL2 LSI_MODE values | D |
| REQ-SYC-001 | M7 | M7 | — | — | — | `../research/sysc.md` §5 (inference); EVK-R50 pending | P |
| REQ-SCIF-001 | M2 | M2 (qtest + hello); M3 | M2-first-character | M2-T01–T07, M2-T13, T14 | qtest `rzv2l-scifa-test` (25 paths); eval `tests/eval/m2/checks.yaml` S01–S15, X01–X06 with their mutations; hello probe (A03, A06) | `../research/scif.md`; `../evidence/EVK-2026-10-29-post-firmware.md`; review and recheck 2026-10-29 (unit `tasks.md` T13, T14). Recorded gaps: 7-bit receive, TE cleared mid-frame, chardev byte lost while ORER is set (design §4, §7) | V |
| REQ-CPG-001 | M3b | M3b | — | — | — | `../research/cpg-reset.md`; HW manual p.327/368/409/450 | P |
| REQ-PFC-001 | M3b | M3b | — | — | — | `../research/pinctrl.md` | P |
| REQ-OSTM-001 | M3b | M3b | — | — | — | `../research/boot-dependency-graph.md`; EVK boot log | P |
| REQ-IRQC-001 | M3b | M3b | — | — | — | `../research/boot-dependency-graph.md` | P |
| REQ-MAP-001 | M1 (initial classification) → M3b | M3b | M1-machine-skeleton | M1-T05, T06 | probe (aborts on unmapped and non-ID SYSC offsets); acceptance log gate; classification of every DTB-U window not checked in M1 | `../device-map.md` | D |
| REQ-WDT-001 | M4 | M4 | — | — | — | `../research/boot-chain-firmware.md` | P |
| REQ-TSIP-001 | M7 | M7 (Stage N negative test) | — | — | — | `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-001 | — (process) | M3 | — | — | — | spec §8 | P |
| REQ-GUEST-002 | — (process) | M3 | — | — | — | spec §8 | P |
| REQ-GUEST-003 | — (process) | M7 | — | — | — | spec §8; `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-004 | — (process) | M3 | M1-machine-skeleton | M1-T07 (M1 fixups) | acceptance `dumpdtb` vs DTB-U | spec §8; `../research/scif.md` (earlycon gap) | D |
| REQ-GUEST-005 | M4 (loader) | M4 | — | — | — | `../research/boot-chain-firmware.md` §4 | P |
| REQ-TEST-001 | M2 | M2 | M2-first-character | M2-T08, T09, T13 | `tests/acceptance/m2/run.sh` (A01: exact serial bytes); eval A01–A06 with mutations | spec §17; review and recheck 2026-10-29 | V |
| REQ-TEST-002 | M1+ | every unit | M1-machine-skeleton | M1-T01–T07 | mutations per task in `../units/M1-machine-skeleton/tasks.md`; T04 has none of its own (covered by T03/T05); `/sysc/boot-mode-reserved`, `/gic/identity` and the PRR/default `LSI_MODE` reads have no recorded mutation | spec §13 | I |
| REQ-TEST-003 | M3+ | M3+ | M1-machine-skeleton | M1-T06 (M1 log gate) | acceptance log gate (`-d unimp,guest_errors,invalid_mem`) | spec §13 | D |
