# M1-machine-skeleton — tasks

Fork tasks go on `unit/M1-machine-skeleton` in `qemu/`; project tasks on `main` or the same-named branch (AGENTS.md "Branches and PRs"). One task per commit where practical; the commit names the task ID. Each test must be seen to fail on the stated mutation before the task closes.

| ID | Task | REQ / AC | Files | Test | Mutation that must turn it red | Status |
|---|---|---|---|---|---|---|
| M1-T01 | `arm_gicv3` property `iidr` (default `0x43B`), used for `GICD_IIDR` and `GICR_IIDR` | MACH-007 / AC10, AC11 | fork `hw/intc/gicv3_internal.h`, `arm_gicv3_common.c`, `arm_gicv3_dist.c`, `arm_gicv3_redist.c`, `include/hw/intc/arm_gicv3_common.h` | qtest: `virt` still reads `0x43B` (AC11) | change the default | TODO |
| M1-T02 | SYSC device `renesas-rzg2l-sysc`: `LSI_MODE`/`DEVID`/`PRR`, bus error elsewhere, 32-bit only, `boot-mode` 0–5 + `debugen` | SYSC-001, SYSC-002 / AC12, AC12b, AC13 | fork `hw/misc/renesas_rzg2l_sysc.c`, `include/hw/misc/renesas_rzg2l_sysc.h`, `hw/misc/Kconfig`, `hw/misc/meson.build` | qtest: the three values; `boot-mode=3` → `0x10003`; invalid `boot-mode` refused | wrong DEVID constant; `debugen` on bit 8 | TODO |
| M1-T03 | SoC `r9a07g054`: 2× A55 (`mp-affinity`, `cntfrq`, EL2 off, EL3 on, CPU1 off), GIC (512 IRQs, 2 redist, security on, `iidr` `0x0201743B`), PPI wiring, SYSC | MACH-001/002/003/007/008 / AC09, AC10 | fork `hw/arm/r9a07g054.c`, `include/hw/arm/r9a07g054.h` | qtest: GIC bases, `ITLinesNumber` 15, `LPIS` 0, `GICR_TYPER` affinity + `Last`, IIDR and ID blocks vs TRM | CPU1 `mp-affinity` `0x1`; `num-irq` 256 | TODO |
| M1-T04 | Board `rzv2l-smarc`: 2 GiB RAM at `0x40000000` (other sizes refused), boot info (`0x48000000` + `0x78000000`, SMC), board properties; Kconfig/meson; machine doc | MACH-001/004/006 / AC01, AC07 | fork `hw/arm/rzv2l-smarc.c`, `hw/arm/Kconfig`, `hw/arm/meson.build`, `docs/system/arm/rzv2l-smarc.rst` + index, `tests/qtest/rzv2l-smarc-test.c` + `meson.build` | `-M help`; qtest file builds and runs T01–T03 checks | — (covered by T03/T05) | TODO |
| M1-T05 | Probe payload: CPU0/CPU1 IDs, `CNTFRQ`, `CurrentEL`, PSCI `CPU_ON`, abort on unmapped and on a non-ID SYSC offset; semihosting exit status | MACH-002/003/004, SYSC-001, MAP-001 / AC03–AC06, AC13, AC14 | project `tests/probes/m1-skeleton/` | probe exits 0 under `-M rzv2l-smarc` | `cntfrq` 62.5 MHz; map a RAZ window at `0x10000000` | TODO |
| M1-T06 | Acceptance run: probe + `info qtree` / `info mtree -f` / `info roms` vs expected files; fails on unexpected `-d unimp,guest_errors` lines | MACH-001/006/008, MAP-001 / AC01–AC07, AC13, AC14 | project `tests/acceptance/m1/` | `run.sh` exits 0 | move SYSC base; load a blob at `0x40000000` | TODO |
| M1-T07 | Build DTB-U from pinned G0 (v6.12.59); `dumpdtb` diff shows only `/memory`, `/psci`, initrd fixups | MACH-006, GUEST-004 / AC08 | project `tests/guests/g0/` (DTB only), `tests/acceptance/m1/` | DT diff check in `run.sh` | change `ram_size` | TODO |
| M1-T08 | Repo layout and traceability: add `tests/probes/`, `tests/acceptance/`, `tests/guests/` to AGENTS.md layout; fill traceability tasks/tests | TEST-002 | project `AGENTS.md`, `docs/spec/traceability.md` | `scripts/lint.py` 0 errors | — | TODO |

## Closure checklist (before closing the unit)
- [ ] every REQ in spec.md appears in at least one task
- [ ] every task names a test; each test's result **and** its mutation check (the test seen to fail on a broken model) are recorded
- [ ] `../../spec/traceability.md` updated; `scripts/lint.py` reports 0 errors
- [ ] independent review done on the final revision: project commit `…`, fork commit `…`
- [ ] every review finding has a disposition (fixed / gap / rejected with evidence); **no unresolved BLOCKER**, since a recorded blocker is still a blocker
- [ ] material fixes rechecked by the reviewer on that final revision
- [ ] fidelity gaps accepted by the operator are listed
- [ ] later: EVK-R60–R66 and EVK-R01 confirm the TRM and BL2 values on silicon (not a closure gate; a conflict reopens AC10/AC12)
