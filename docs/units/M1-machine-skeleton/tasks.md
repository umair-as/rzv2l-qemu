# M1-machine-skeleton — tasks

Fork tasks go on `unit/M1-machine-skeleton` in `qemu/`; project tasks on `main` or the same-named branch (AGENTS.md "Branches and PRs"). One task per commit where practical; the commit names the task ID. Each test must be seen to fail on the stated mutation before the task closes.

| ID | Task | REQ / AC | Files | Test | Mutation that must turn it red | Status |
|---|---|---|---|---|---|---|
| M1-T01 | `arm_gicv3` property `iidr` (default `0x43B`), used for `GICD_IIDR` and `GICR_IIDR` | MACH-007 / AC10, AC11 | fork `hw/intc/gicv3_internal.h`, `arm_gicv3_common.c`, `arm_gicv3_dist.c`, `arm_gicv3_redist.c`, `arm_gicv3_its.c`, `arm_gicv3_kvm.c`, `include/hw/intc/arm_gicv3_common.h`, `tests/qtest/arm-gicv3-iidr-test.c` + `meson.build`, `MAINTAINERS` | qtest: `virt` still reads `0x43B` (AC11); `-global arm-gicv3.iidr` reads back on GICD and both GICRs | change the default; GICR ignores the property | DONE; review: HVF and WHPX also refuse a non-default `iidr` (read only, no host to build) |
| M1-T02 | SYSC device `renesas-rzg2l-sysc`: `LSI_MODE`/`DEVID`/`PRR`, bus error elsewhere, 32-bit only, `boot-mode` 0–5 + `debugen` | SYSC-001, SYSC-002 / AC12, AC12b, AC13 | fork `hw/misc/renesas_rzg2l_sysc.c`, `include/hw/misc/renesas_rzg2l_sysc.h`, `hw/misc/Kconfig`, `hw/misc/meson.build` | qtest: the three values; `boot-mode=3` → `0x10003`; invalid `boot-mode` refused | wrong DEVID constant; `debugen` on bit 8; `sec-en` unset; `MD_OSCDRV`/`MD_CLKS` moved one bit | DONE (fork `51378195d3`, merged to `rzv2l-dev`); review: `sec-en`, `md-clks`, `md-oscdrv` properties, EVK-cited goldens |
| M1-T03 | SoC `r9a07g054`: 2× A55 (`mp-affinity`, `cntfrq`, EL2 off, EL3 on, CPU1 off), GIC (512 IRQs, 2 redist, security on, `iidr` `0x0201743B`), PPI wiring, SYSC | MACH-001/002/003/007/008 / AC09, AC10 | fork `hw/arm/r9a07g054.c`, `include/hw/arm/r9a07g054.h` | qtest: GIC bases, `ITLinesNumber` 15, `LPIS` 0, `GICR_TYPER` affinity + `Last`, IIDR and ID blocks vs TRM | CPU1 `mp-affinity` `0x1`; `num-irq` 256 | DONE (fork `51378195d3`, merged to `rzv2l-dev`) |
| M1-T04 | Board `rzv2l-smarc`: 2 GiB RAM at `0x40000000` (other sizes refused), boot info (`0x48000000` + `0x78000000`, SMC), board properties; Kconfig/meson; machine doc | MACH-001/004/006 / AC01, AC07 | fork `hw/arm/rzv2l-smarc.c`, `hw/arm/Kconfig`, `hw/arm/meson.build`, `docs/system/arm/rzv2l-smarc.rst` + index, `tests/qtest/rzv2l-smarc-test.c` + `meson.build` | `-M help`; qtest file builds and runs T01–T03 checks | — (covered by T03/T05) | DONE (fork `51378195d3`, merged to `rzv2l-dev`) |
| M1-T05 | Probe payload: CPU0/CPU1 IDs, `CNTFRQ`, `CurrentEL`, PSCI `CPU_ON`, abort on unmapped and on a non-ID SYSC offset; semihosting exit status | MACH-002/003/004, SYSC-001, MAP-001 / AC03–AC06, AC13, AC14 | project `tests/probes/m1-skeleton/` | probe exits 0 under `-M rzv2l-smarc` | `cntfrq` 62.5 MHz; map a RAZ window at `0x10000000`; `has_el2` true | DONE: 15 checks pass; both mutations red. `ID_AA64PFR0_EL1.EL2` = 0 added on both CPUs (17 checks), `has_el2` mutation red |
| M1-T06 | Acceptance run: probe + `info qtree` / `info mtree -f` / `info roms` vs expected files; fails on unexpected `-d unimp,guest_errors,invalid_mem` lines | MACH-001/006/008, MAP-001 / AC01–AC07, AC13, AC14 | project `tests/acceptance/m1/` | `run.sh` exits 0 | move SYSC base; load a blob at `0x40000000` | DONE: run.sh PASS; mutations red (SYSC base, loader at 0x40000000, extra log line) |
| M1-T07 | Build DTB-U from pinned G0 (v6.12.59); `dumpdtb` diff shows only `/memory`, `/psci`, initrd fixups | MACH-006, GUEST-004 / AC08 | project `tests/guests/g0/` (DTB only), `tests/acceptance/m1/` | DT diff check in `run.sh` | change `ram_size` | DONE: run.sh PASS (209 nodes, only `/psci` rewritten); `ram_size` mutation red; `/psci` must keep `method = "smc"` and `compatible` `arm,psci-1.0` (both seen red on edited dumps). DTB-U SHA-256 `4c339906…e85620` with host DTC 1.7.0 (kernel's in-tree: 1.7.0-gbcd02b52), so a rebuild may differ by tool |
| M1-T08 | Repo layout and traceability: add `tests/probes/`, `tests/acceptance/`, `tests/guests/` to AGENTS.md layout; fill traceability tasks/tests | TEST-002 | project `AGENTS.md`, `docs/spec/traceability.md` | `scripts/lint.py` 0 errors | — | DONE: layout lines present (`tests/guests/` added with T07); traceability rows for the 13 M1 REQs filled; lint 0 errors |

## Closure

Closed: reviewed and merged (`rzv2l-dev`, then `main`). Its traceability rows are updated with the v1.0 closure; the GIC identity it set from the TRM is confirmed on silicon by EVK-R60-R66 (`../../evidence/EVK-2026-10-29-post-firmware.md`).

## Proofs added at the v1.1 closure

The three M1 checks that had no recorded mutation (REQ-TEST-002), each built with a confirmed relink, run alone, then restored:

| # | Mutation | Red line |
|---|---|---|
| 1 | `RZG2L_SYSC_BOOT_MODE_MAX` 5 → 6 (boot mode 6 accepted) | `rzv2l-smarc-test.c:144:test_sysc_boot_mode_reserved: child process ... did not fail as expected` |
| 2 | `R9A07G054_GIC_IIDR` `0x0201743b` → `0x0201743a` | `rzv2l-smarc-test.c:187:test_gic_identity: assertion failed (qtest_readl(qts, GICD_BASE + GICD_IIDR) == GIC600_IIDR): (0x0201743a == 0x0201743b)` |
| 3 | `R9A07G054_LSI_PRR` `0x0` → `0x1` | `rzv2l-smarc-test.c:96:test_sysc_id: assertion failed (qtest_readl(qts, SYSC_BASE + SYS_LSI_PRR) == LSI_PRR_RZV2L): (0x00000001 == 0x00000000)` |
| 4 | `R9A07G054_LSI_SEC_EN` `true` → `false` (the default `SYS_LSI_MODE`) | `rzv2l-smarc-test.c:99:test_sysc_id: assertion failed (qtest_readl(qts, SYSC_BASE + SYS_LSI_MODE) == LSI_MODE_SEC_EN): (0x00000000 == 0x00010000)` |
