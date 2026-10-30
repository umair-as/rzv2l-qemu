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
| REQ-MACH-003 | M1 | M1 (test ELF reads CNTFRQ); M3 (Linux `arch_timer` line) | M1-machine-skeleton | M1-T03, T05 | probe (`CNTFRQ_EL0`); M3 acceptance boots with the stock timer node | `../research/cpu-gic.md`; EVK boot log. Rate gap: QEMU counts at 24.39 MHz (device map gap 18) | V |
| REQ-MACH-004 | M1 (`has_el2=false`, SMC conduit) | M3 (Linux reports EL1, PSCI works) | M1-machine-skeleton; M3b-shell | M1-T04, T05; M3b-shell T2 | probe (`CurrentEL` = 1, `ID_AA64PFR0_EL1.EL2` = 0, PSCI `CPU_ON` over SMC); M3 acceptance: both CPUs online (proof 1: CPU 1 affinity); the security state cannot be read from EL1 | EXP-001; EVK boot log | V |
| REQ-MACH-005 | M7 | M7 (BL31 CPU_OFF runs) | — | — | — | EXP-001 | P |
| REQ-MACH-006 | M1 | M1 (`info mtree`); M3 (`/proc/iomem`) | M1-machine-skeleton | M1-T04, T06, T07 | acceptance `info mtree -f`, `info roms`, `dumpdtb` vs DTB-U; G0 `/proc/iomem`: System RAM `48000000-bfffffff` | `../research/cpu-gic.md`; `../evidence/EVK-2026-10-30-linux.md` §1 (EVK RAM `48000000-bffbffff` + G2 ramoops at the top) | V |
| REQ-MACH-007 | M1 | M1 (placement + GICD/GICR identity == EVK, DR-0003 option A; TRM values; EVK-R60–R66 confirm on silicon) | M1-machine-skeleton | M1-T01, T03 | qtest `arm-gicv3-iidr-test`; qtest `rzv2l-smarc-test` `/gic/layout`, `/gic/identity` | `../research/cpu-gic.md`; EVK boot log; `../evidence/EVK-2026-10-29-post-firmware.md` (R60-R66) | V |
| REQ-MACH-008 | M1+ (per device) | each device's milestone | every unit | M1-T03, T06; each unit's SoC task | acceptance `info mtree -f`, `info qtree` (vs `device-map.md`); qtests per device; M3/M4 boots | `../device-map.md`; `../evidence/EVK-2026-10-30-linux.md` §1-2 (EVK `/proc/iomem` and IRQ numbers match) | V |
| REQ-SYSC-001 | M1 | M1 | M1-machine-skeleton | M1-T02, T05 | qtest `rzv2l-smarc-test` `/sysc/id`; probe (abort on a non-ID offset) | `../research/sysc.md`; EVK BL2 print `0x18447447` | V |
| REQ-SYSC-002 | M1 (board property) | M7 (BL2/U-Boot boot-device selection) | M1-machine-skeleton | M1-T02 | qtest `rzv2l-smarc-test` `/sysc/boot-pins`, `/sysc/boot-mode-reserved` | `../research/sysc.md`; EVK BL2 LSI_MODE values | D |
| REQ-SYC-001 | M7 | M7 | — | — | — | `../research/sysc.md` §5 (inference); EVK-R50 pending | P |
| REQ-SCIF-001 | M2 | M2 (qtest + hello); M3 | M2-first-character | M2-T01–T07, M2-T13, T14 | qtest `rzv2l-scifa-test` (25 paths); eval `tests/eval/m2/checks.yaml` S01–S15, X01–X06 with their mutations; hello probe (A03, A06) | `../research/scif.md`; `../evidence/EVK-2026-10-29-post-firmware.md`; review and recheck (unit `tasks.md` T13, T14). Recorded gaps: 7-bit receive, TE cleared mid-frame, chardev byte lost while ORER is set (design §4, §7) | V |
| REQ-CPG-001 | M3b | M3b | M3b-cpg | T1-T5 | qtest `rzv2l-cpg-test`; proofs in `../units/M3b-cpg/tasks.md` | `../research/cpg-reset.md`; HW manual p.327/368/409/450; EVK R10-R19, X01 | V |
| REQ-PFC-001 | M3b | M3b | M3b-pfc-irqc | T2, T3 | qtest `rzv2l-pfc-irqc-test` `/pfc/*`; M3 acceptance (pinctrl-rzg2l bound, `ttySC0` takes over); proofs in `../units/M3b-pfc-irqc/tasks.md` | `../research/pinctrl.md`; EVK R30-R36, R71 | V |
| REQ-OSTM-001 | M3b | M3b | M3b-ostm | T1-T6 | qtest `rzv2l-ostm-test`; hello probe OSTM2 interrupts; M3 time rate check; proofs in `../units/M3b-ostm/tasks.md` | `../research/boot-dependency-graph.md`; EVK boot log | V |
| REQ-IRQC-001 | M3b | M3b | M3b-pfc-irqc | T1, T3 | qtest `rzv2l-pfc-irqc-test` `/irqc/registers`; hello probe (unlisted offset faults); M3 acceptance (pin controller binds after the IRQC) | `../research/boot-dependency-graph.md`; `../evidence/EVK-2026-10-30-linux.md` §2 (routing has a consumer: gap 15) | V |
| REQ-MAP-001 | M1 (initial classification) → M3b | M3b | M1-machine-skeleton; M3b units | M1-T05, T06; each unit's window task | probe (aborts on unmapped and non-ID SYSC offsets); M3/M4 log gates (only recorded stub windows) | `../device-map.md`; `../evidence/EVK-2026-10-30-linux.md` §1 | V |
| REQ-WDT-001 | M4 | M4 | M4-vendor-kernel | T2-T6 | qtest `rzv2l-wdt-test` (expiry, PEEN forced reset); M4 acceptance (WDT0 refresh, stop, reset); proofs in `../units/M4-vendor-kernel/tasks.md`. The PSCI reset through a real BL31 waits for M7 | `../research/boot-chain-firmware.md`; `../evidence/EVK-2026-10-30-linux.md` §3, §6 | V |
| REQ-SDHI-001 | M5 | M5 | M5-sdhi | T1-T4 | — |
| REQ-SDHI-002 | M5 | M5 | M5-sdhi | T5 | — |
| REQ-TSIP-001 | M7 | M7 (Stage N negative test) | — | — | — | `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-001 | — (process) | M3 | M1-machine-skeleton; M3b-shell | M1-T07; M3b-shell T3 | acceptance `dumpdtb` vs DTB-U (only listed fixups differ); M3/M4 runs use the stock DTB-U / DTB-V and their own bootargs | spec §8 | V |
| REQ-GUEST-002 | — (process) | M3 | M3b-shell; M4-vendor-kernel | M3b-shell T1; M4-vendor-kernel T1 | `tests/guests/g0/build-kernel.sh`, `tests/guests/g1/build-kernel.sh` refuse a checkout with local changes; G1 uses its own defconfig | spec §8; `../sources.md` | V |
| REQ-GUEST-003 | — (process) | M7 | — | — | — | spec §8; `../research/boot-chain-firmware.md` | P |
| REQ-GUEST-004 | — (process) | M3 | M1-machine-skeleton; M3b-shell | M1-T07 (M1 fixups); M3b-shell T3 | acceptance `dumpdtb` vs DTB-U; M3 runs with no `-append` | spec §8; device map §4 gaps 6-8 | V |
| REQ-GUEST-005 | M4 (loader) | M4 | — | — | — | `../research/boot-chain-firmware.md` §4 | P |
| REQ-TEST-001 | M2 | M2 | M2-first-character | M2-T08, T09, T13 | `tests/acceptance/m2/run.sh` (A01: exact serial bytes); eval A01–A06 with mutations | spec §17; review and recheck | V |
| REQ-TEST-002 | M1+ | every unit | every unit | M1-T01–T07; each unit's proofs | a qtest per device model with recorded mutations (`tasks.md` of M2, M3b-*, M4-vendor-kernel); M1: T04 has none of its own (covered by T03/T05); `/sysc/boot-mode-reserved`, `/gic/identity` and the PRR/default `LSI_MODE` reads have no recorded mutation | spec §13 | D |
| REQ-TEST-003 | M3+ | M3+ | M1-machine-skeleton; M3b-shell; M4-vendor-kernel | M1-T06; M3b-shell T2; M4-vendor-kernel T5 | acceptance log gates (`-d unimp,guest_errors,invalid_mem`): only recorded stub windows, an empty log fails | spec §13 | V |
