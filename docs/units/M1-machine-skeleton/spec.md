# M1-machine-skeleton — spec

**Milestone:** M1
**Status:** REVIEWED (2026-10-09): operator review and independent review (findings dispositioned)
**Requirements:** REQ-GUEST-004 (loader fixups listed), REQ-MACH-001, REQ-MACH-002, REQ-MACH-003, REQ-MACH-004 (configured only), REQ-MACH-006, REQ-MACH-007, REQ-MACH-008 (M1 windows), REQ-SYSC-001, REQ-SYSC-002 (implemented; accepted at M7), REQ-MAP-001 (initial classification only), REQ-TEST-002

## Goal

`qemu-system-aarch64 -M rzv2l-smarc` instantiates the board's CPU, interrupt and memory topology plus the SYSC identity registers, at the addresses the stock DTB and firmware expect. Nothing prints yet; console output is M2. M1 is the base every later device attaches to, so its job is to get placement and identity exactly right and prove it with tests that assert manual and EVK values, not the model's own output.

## Acceptance criteria (EARS)

| ID | Criterion | REQ | Verified by |
|---|---|---|---|
| M1-AC01 | WHEN `qemu-system-aarch64 -M help` is run THEN the output SHALL list `rzv2l-smarc`. | MACH-001 | run script |
| M1-AC02 | The machine SHALL be built as a board around a SoC object `TYPE_R9A07G054` that contains the CPUs, the GIC and the on-chip devices; `info qtree` SHALL show this structure. | MACH-001 | `info qtree` vs `../../device-map.md` |
| M1-AC03 | WHEN the machine starts THEN it SHALL have two `cortex-a55` CPUs whose `MPIDR_EL1` affinity fields are `0x0` and `0x100`, and whose `MIDR_EL1` reads `0x412FD050` (r2p0). | MACH-002 | probe payload |
| M1-AC04 | WHEN the machine starts THEN CPU1 SHALL be powered off, and WHEN CPU0 issues PSCI `CPU_ON` for `0x100` over SMC THEN CPU1 SHALL start at the given entry point. | MACH-002, MACH-004 | probe payload |
| M1-AC05 | WHEN either CPU reads `CNTFRQ_EL0` THEN it SHALL read `24000000`. | MACH-003 | probe payload |
| M1-AC06 | WHEN an arm64 `Image` is loaded with `-kernel` (direct mode) THEN it SHALL be entered at EL1 with PSCI over SMC, in the non-secure state. | MACH-004 (configured; accepted at M3) | probe payload reads `CurrentEL`; the non-secure state is code-derived (qemu v11.1.2 `hw/arm/boot.c:704-722`), not observable by the probe |
| M1-AC07 | `info mtree` SHALL show 2 GiB of RAM at `0x40000000`, and no QEMU-loaded blob (`info roms`) SHALL overlap `0x40000000`–`0x47FFFFFF`, the firmware-reserved region. | MACH-006 | run script |
| M1-AC08 | WHEN the stock upstream DTB is passed with `-dtb` THEN the `/memory` node QEMU passes on (monitor command `dumpdtb`, qemu v11.1.2 `hw/arm/boot.c:643-645`) SHALL be `0x48000000` + `0x78000000`, and the only other differences from the stock DTB SHALL be QEMU's known loader fixups, each on the REQ-GUEST-004 gap list: `/psci` replaced (qemu v11.1.2 `hw/arm/boot.c:366-401`; the stock DT has its own, `r9a07g054.dtsi:165-168`) and the `/chosen` initrd properties when an initrd is given (`boot.c:612-627`). | MACH-006, GUEST-004 | run script + DT diff |
| M1-AC09 | The GIC distributor SHALL be at `0x11900000` and the redistributors at `0x11940000` (CPU0) and `0x11960000` (CPU1), with no ITS; `GICD_TYPER.ITLinesNumber` SHALL be 15 (480 SPIs) with `LPIS` = 0; `GICR_TYPER` SHALL carry each CPU's affinity, with `Last` set only on the second redistributor. | MACH-007, MACH-008 | qtest |
| M1-AC10 | `GICD_IIDR`, `GICR_IIDR` and the PIDR/CIDR blocks of the distributor and of **both** redistributors' RD_base frames SHALL equal the EVK values from EVK-R60–R66 (DR-0003 option A). | MACH-007 | qtest vs EVK capture |
| M1-AC11 | IF the GIC identity properties are not set THEN QEMU's existing GIC identity SHALL be unchanged, so no other machine changes behaviour. | MACH-007 | qtest on an existing machine |
| M1-AC12 | WHEN `0x11020A04` (`SYS_LSI_DEVID`) is read THEN it SHALL return `0x18447447`; WHEN `0x11020A08` (`SYS_LSI_PRR`) is read THEN it SHALL return `0x00000000`. Both are read-only (R) in Table 6.1 p.167-168; writes SHALL be ignored (inference from R). | SYSC-001 | qtest vs EVK BL2 print, confirmed by EVK-R01 before acceptance |
| M1-AC12b | WHEN `0x11020A00` (`SYS_LSI_MODE`) is read THEN it SHALL return `STAT_SEC_EN` (bit 16) = 1, `STAT_DEBUGEN` (bit 9) from the board property `debugen` (default 0), `STAT_MD_BOOT` (bits [2:0]) from the board property `boot-mode` (default **0, eSD**), and 0 in every other field (§6.3.42 p.207). `boot-mode` SHALL accept only the modes Table 4.1 p.105 defines (0–5). The register is read-only (R); writes SHALL be ignored (inference from R). | SYSC-002 | qtest vs EVK BL2 prints (`0x10000`, `0x10200`, `0x10001`, `0x10201`, `0x10203`) and EVK-R01 |
| M1-AC13 | IF any other SYSC offset is accessed THEN the access SHALL fail with a bus error (the guest takes an external abort) and be logged under `-d unimp`. Reading zero would be silently wrong: Table 6.1 p.167-168 gives non-zero reset values (e.g. `SYS_MSTACCCTL0` `0x00AAAA00`, `SYS_AOF0` `0x32103210`). | SYSC-001, MAP-001 | probe payload + `-d unimp` log |
| M1-AC14 | Every address outside the M1 windows (RAM, GIC, SYSC) SHALL be unmapped, so a stray access aborts visibly instead of reading a silent zero. | MAP-001 | probe payload (an access to an unmapped address takes a synchronous external abort) + `info mtree`; a qtest cannot see this, because qtest discards the bus result (qemu v11.1.2 `system/qtest.c:545-572`) |
| M1-AC15 | Every qtest assertion above SHALL be mutation-checked: a deliberately broken model value makes the test fail, and the failure is recorded. | TEST-002 | mutation record |

## Exit gate

- **Passes when:** AC01–AC15 hold on the final reviewed revision, the closure checklist in `tasks.md` is complete, and `scripts/lint.py` reports 0 errors.
- **Disqualifies:** any assertion whose expected value comes from the model itself or from an unmeasured prediction (in particular AC10 before EVK-R60–R66 are captured); any placeholder mapped beyond the three M1 windows.
- **Known blind spot:** M1 runs no OS. Nothing in M1 shows that Linux boots or that interrupts are delivered; those are M2/M3 claims.

## Scope

**In:**
- SoC object `TYPE_R9A07G054` and board `rzv2l-smarc`, structured like `fsl-imx8mp` / `imx8mp-evk`, so RZ/G2L can be added later.
- 2× `cortex-a55`: `mp-affinity` `0x0`/`0x100` (MT = 0, see the gap below), `cntfrq` 24 MHz, `has_el2=false`, `has_el3=true`, CPU1 `start-powered-off`.
- GIC via QEMU's `arm_gicv3` (revision 3, 2 CPUs, 512 IRQs, two redistributor frames, `has-security-extensions=true`, no LPIs), realized after the CPUs; generic-timer and maintenance PPIs wired as in the device map.
- A generic, default-off identity property set on `arm_gicv3` (DR-0003 option A), in upstream shape.
- 2 GiB RAM at `0x40000000`; direct-mode boot info with `loader_start` `0x48000000`, `ram_size` `0x78000000`, PSCI conduit SMC.
- SYSC: `SYS_LSI_DEVID` and `SYS_LSI_PRR` as read-only constants, `SYS_LSI_MODE` from the board properties `boot-mode` and `debugen`; every other offset in the 64 KiB window fails with a logged bus error.
- A small bare-metal probe payload (arm64 `Image` format, so QEMU's Linux path gives direct-mode entry) that reports MPIDR, MIDR, `CNTFRQ_EL0`, `CurrentEL` and the CPU1 start through a memory mailbox read by qtest or gdbstub, since there is no UART until M2.

**Out (non-goals):**
- CPG, PFC, OSTM, IRQC, WDT, DMAC and SCIF (M2/M3b).
- SYC `CNTFID0` (REQ-SYC-001, M7) and the A55 IMPDEF system registers (REQ-MACH-005, M7).
- SYSC registers firmware uses later: `RVAL`/`RVAH`, `LP_CTL*`, access control, address translation (M7).
- Any OS guest boot.

**Start states (spec §9):** the SYSC identity registers are constants, the same in both states. The GIC is not: it starts at its architectural reset, and in direct mode QEMU's boot code configures it for the non-secure world (qemu v11.1.2 `hw/intc/arm_gicv3_common.c:587-602`). With security extensions on, `GICD_CTLR.DS` = 0, which matches the board log; for the model this is code-derived (`arm_gicv3_common.c:546-551`) until an M3 boot prints it. The board's `SCR_EL3.FIQ=1` versus QEMU's 0 is a known direct-mode gap (`../../research/cpu-gic.md` §6 D2), observable only from M3.

**Accepted gap: `MPIDR_EL1.MT`.** M1 reports MT = 0. Arm documents MT = 1 for Cortex-A55 (Cortex-A55 TRM, external), but the board value is unmeasured. Setting MT through `mp-affinity` would break PSCI `CPU_ON`, because QEMU matches the full value against the target Linux passes (`0x100`, from DT `reg`): qemu v11.1.2 `target/arm/arm-powerctl.c:22-31`, `hw/intc/arm_gicv3_common.c:462-469`. Revisit at M7, where real TF-A derives core positions from MPIDR.

## Evidence

- Addresses, IRQs and classes: `../../device-map.md` (DDR, CPU cluster, generic timer, GIC distributor, redistributors, GIC remainder, SYSC rows).
- CPU, GIC, timer and entry state: `../../research/cpu-gic.md` §6–§7; EXP-001 (`../../experiments/`).
- SYSC registers and which software reads them: `../../research/sysc.md`; the M0 report's "SYSC in M1" table.
- EVK values: `../../evidence/EVK-2026-10-08-boot-log.md` (MIDR, redistributor bases, 480 SPIs, DEVID, PRR); GIC identity from `../../evidence/requests.md` EVK-R60–R66 (not yet captured).
- Decisions: DR-0003 (GIC identity, option A).

## Decisions (operator review, 2026-10-09)

1. `MPIDR_EL1.MT`: 0 in M1, recorded as a gap (above); revisit at M7, where real TF-A replaces QEMU's PSCI and the value can first be measured.
2. `SYS_LSI_MODE`: implemented in M1 from board properties `boot-mode` (manual modes 0–5, default 0 = eSD, the operator's usual boot source) and `debugen` (AC12b); REQ-SYSC-002 is accepted at M7.
3. Everything outside the M1 windows stays unmapped (AC14).
4. The probe payload's location under `tests/` is decided in `design.md`.
5. Other SYSC offsets fail with a bus error, not read-as-zero (AC13; review finding R12).
6. GIC identity (AC10) covers the RD_base frames only, which is what Linux reads (linux v6.12.59 `drivers/irqchip/irq-gic-v3.c:1043`). Whether the GIC-600 repeats ID registers in the SGI_base frame is unverified (external Arm document); not asserted.
