# M1-machine-skeleton — design

**Status:** DRAFT (2026-10-09); implementation may start, operator reviews as tasks land
**Implements:** `spec.md` (REVIEWED). QEMU citations are qemu v11.1.2.

## Structure

| Piece | Repo | Files | Notes |
|---|---|---|---|
| SoC `TYPE_R9A07G054` | fork | `hw/arm/r9a07g054.c`, `include/hw/arm/r9a07g054.h` | container for CPUs, GIC, SYSC; memory map table; RZ/G2L can reuse it later with its own table |
| Board `rzv2l-smarc` | fork | `hw/arm/rzv2l-smarc.c` | RAM, SoC instance, boot info, board properties |
| SYSC | fork | `hw/misc/renesas_rzg2l_sysc.c`, `include/hw/misc/renesas_rzg2l_sysc.h` | named for the RZ/G2L family, whose SYSC layout RZ/V2L shares; IDs are properties |
| GIC `iidr` property (DR-0003 A) | fork | `hw/intc/gicv3_internal.h`, `arm_gicv3_common.c`, `arm_gicv3_dist.c`, `arm_gicv3_redist.c`, `include/hw/intc/arm_gicv3_common.h` | one generic, default-off property |
| Build wiring | fork | `hw/arm/Kconfig`, `hw/arm/meson.build`, `hw/misc/Kconfig`, `hw/misc/meson.build` | `R9A07G054` selects `ARM_GICV3`, `RENESAS_RZG2L_SYSC`; `RZV2L_SMARC` selects `R9A07G054` |
| Machine doc | fork | `docs/system/arm/rzv2l-smarc.rst` (+ index) | what is modelled, what is not |
| qtests | fork | `tests/qtest/rzv2l-smarc-test.c` (+ `meson.build`) | AC09–AC12b, AC11 on `virt` |
| Probe payload | project | `tests/probes/m1-skeleton/` | arm64 `Image`; reports through semihosting (below) |
| Acceptance run | project | `tests/acceptance/m1/run.sh` + expected files | AC01–AC08, AC13–AC14; drives the probe and the monitor |

The SoC follows `hw/arm/fsl-imx8mp.c`: `instance_init` creates the children, `realize` configures CPUs, then the GIC, then devices. Two differences from imx8mp matter:
- **`mp-affinity` is set explicitly** (`0x0`, `0x100`). imx8mp relies on QEMU's default, which numbers CPUs `0x0, 0x1, …` (8 per cluster), and would give CPU1 the wrong ID for this board's DT.
- **CPUs are realized before the GIC.** The GIC copies each CPU's `mp-affinity` into `GICR_TYPER` at its own realize (`hw/intc/arm_gicv3_common.c:462-469`).

## Memory map (M1)

| Region | Base | Size | Backing |
|---|---|---|---|
| SYSC | `0x11020000` | 64 KiB | `renesas-rzg2l-sysc` |
| GIC distributor | `0x11900000` | 64 KiB (QEMU's frame) | `arm_gicv3` |
| GIC redistributors | `0x11940000` | 2 × `0x20000` | `arm_gicv3`, `redist-region-count = [2]` |
| DDR | `0x40000000` | 2 GiB | board RAM |
| everything else | — | — | unmapped (abort) |

## CPUs and interrupts

- 2 × `cortex-a55`: `mp-affinity` `0x0`/`0x100`; `cntfrq` 24000000; `has_el2` false; `has_el3` true; CPU1 `start-powered-off`.
- GIC: `revision` 3, `num-cpu` 2, `num-irq` 512 (32 internal + 480 SPIs → `ITLinesNumber` 15), `has-security-extensions` true, `has-lpi` false.
- PPI wiring (INTID = 16 + PPI), from the device map; QEMU's BSA constants match:

| Source | PPI | INTID |
|---|---|---|
| `GTIMER_PHYS` (NS EL1 physical) | 14 | 30 |
| `GTIMER_VIRT` | 11 | 27 |
| `GTIMER_HYP` (NS EL2 physical) | 10 | 26 |
| `GTIMER_SEC` (secure EL1 physical) | 13 | 29 |
| `GTIMER_HYPVIRT` (NS EL2 virtual) | 12 | 28 |
| GIC maintenance | 9 | 25 |
| PMU | 7 | 23 |

- GIC outputs IRQ/FIQ/VIRQ/VFIQ go to each CPU's inputs.

## Register behaviour

### SYSC (`renesas-rzg2l-sysc`)

| Register | Offset | Value | Class | Behaviour | Evidence |
|---|---|---|---|---|---|
| `SYS_LSI_MODE` | `0xA00` | `0x10000` \| (`debugen` << 9) \| `boot-mode` | status, R | read-only; writes ignored and logged as guest errors | §6.3.42 p.207; Table 4.1 p.105; EVK BL2 prints |
| `SYS_LSI_DEVID` | `0xA04` | property `lsi-devid`, set to `0x18447447` by the SoC | ID, R | as above | §6.3.43 p.208; EVK BL2 print |
| `SYS_LSI_PRR` | `0xA08` | property `lsi-prr`, set to `0x0` | ID, R | as above | §6.3.44 p.209; EVK BL2 print |
| any other offset | — | — | — | read or write returns `MEMTX_DECODE_ERROR` (the guest takes a synchronous external abort, `target/arm/tcg/tlb_helper.c:316-352`) and logs `LOG_UNIMP` | Table 6.1 p.167-168 (non-zero resets make RAZ silent-wrong) |

- Access size: 32-bit only (`valid.min_access_size = valid.max_access_size = 4`); Table 6.1 lists the registers as 32-bit. Narrower accesses fail the same way. Whether silicon accepts byte reads is unknown; recorded as a gap.
- `boot-mode` is validated at realize: 0–5 (Table 4.1); 6–7 are reserved and rejected. `debugen` is a bool.
- No mutable state, so no reset handler and no migration state (`vmsd` not needed; noted in the doc comment).

### GIC identity (DR-0003 option A, amended)

Every GIC has read-only ID registers: a nameplate software can read. Linux reads `GICD_IIDR` at boot and matches it against a table of known GIC errata (linux v6.12.59 `drivers/irqchip/irq-gic-v3.c:2085`, table `:1962-2025`), so the nameplate must be the real chip's. QEMU's GIC always answers with one fixed nameplate, whatever machine it is in.

The Arm GIC-600 r1p6 TRM (100336_0106_00) gives the real values. Only one differs from QEMU:

| Register | GIC-600 r1p6 | QEMU today |
|---|---|---|
| `GICD_IIDR`, `GICR_IIDR` | `0x0201743B`: ProductID `0x02`, Variant `0x1` (r1), Revision `0x7` (p6), Arm `0x43B` (Tables 4-5, 4-22) | `0x0000043B` |
| PIDR/CIDR blocks | `44 00 00 00 92 B4 3B 00 0D F0 05 B1` (GICD), `…93…` (GICR) (Tables 4-2, 4-21) | identical |

So the change is one new `arm_gicv3` property, `iidr` (uint32, default `0x43B`). `gicv3_iidr()` takes the `GICv3State` and returns it for `GICD_IIDR` and `GICR_IIDR`; the ITS keeps its value (no ITS on this board). The default keeps every other machine unchanged (AC11). The SoC sets `iidr` = `0x0201743B`.

## Boot (direct mode)

`arm_boot_info`: `loader_start` `0x48000000`, `ram_size` `0x78000000`, `psci_conduit` `QEMU_PSCI_CONDUIT_SMC`. With an arm64 `Image`, QEMU's boot code enters at EL1 (no EL2), non-secure, and its built-in PSCI answers SMCs (`hw/arm/boot.c:954-956`, `1238-1254`, `704-722`). `/memory` becomes `0x48000000` + `0x78000000` (`boot.c:643-645`); `/psci` is replaced (`boot.c:366-401`). RAM size other than 2 GiB is rejected: the window values are the 2 GB EVK's.

## Start states

| Device | Firmware mode | Direct mode |
|---|---|---|
| CPUs | reset at EL3, CPU1 off | entered at NS-EL1 by QEMU's boot code; CPU1 off until PSCI `CPU_ON` |
| GIC | architectural reset | configured non-secure by QEMU's boot code (`hw/intc/arm_gicv3_common.c:587-602`) |
| SYSC | constants and latched pins | same |

Firmware mode has no user before M7; M1 only builds and tests direct mode, and keeps the firmware-mode path untested by design.

## Probe payload (`tests/probes/m1-skeleton/`)

Bare-metal C + assembly, built like EXP-001 (`aarch64-linux-gnu-gcc`, freestanding), packed as an arm64 `Image` so QEMU takes the Linux boot path. It reports through **semihosting** (`HLT #0xF000`; allowed at EL1 when `-semihosting-config enable=on`, `semihosting/config.c:66-69`) and ends with `SYS_EXIT` carrying a pass/fail status. Semihosting is a property of the test harness, not of the model.

Checks, one line of output each:
1. CPU0 `MPIDR_EL1` affinity `0x0`, `MIDR_EL1` `0x412FD050`, `CNTFRQ_EL0` 24000000, `CurrentEL` = 1 (AC03, AC05, AC06).
2. PSCI `CPU_ON(0x100)` over SMC; CPU1 writes the same four values to a mailbox in RAM; CPU0 waits with a timeout (AC04, AC03, AC05).
3. Install a vector table; read an unmapped address (`0x10000000`) and a non-ID SYSC offset (`0x11020000`); each must take a data abort with `ESR_EL1.EC` = `0x25` and `DFSC` = `0x10` (synchronous external abort) (AC14, AC13).

## Acceptance run (`tests/acceptance/m1/run.sh`)

Builds the probe, then runs `qemu-system-aarch64 -M rzv2l-smarc -kernel probe.Image -semihosting-config enable=on -d unimp,guest_errors` and checks:
- the probe's exit status and its lines (AC03–AC06, AC13, AC14);
- through the monitor: `info qtree` and `info mtree -f` against hand-written expected files derived from `../../device-map.md` (AC02, AC07), `info roms` for the `0x40000000`–`0x47FFFFFF` rule (AC07);
- `-M help` (AC01);
- with the stock G0 DTB: `dumpdtb`, then a DT diff whose only differences are the listed fixups (AC08). This needs DTB-U built from the pinned G0 kernel (a task).

The script fails on any unexpected `-d unimp` or guest-error line.

## Fidelity

| Item | Class | Not supported / gap |
|---|---|---|
| CPUs | FUNCTIONAL / faithful | `MPIDR_EL1.MT` = 0 (spec gap); A55 IMPDEF sysregs (M7); cache topology (QEMU reports an L2 the SoC lacks, `cpu-gic.md` claim 5) |
| GIC | FUNCTIONAL / faithful | identity per the TRM, silicon confirmation pending EVK-R60–R66; `SCR_EL3.FIQ` 0 vs board 1 in direct mode (observable from M3); SGI_base ID registers unverified |
| PSCI (QEMU built-in) | FUNCTIONAL | SMCCC reports v1.0, board v1.4 (`cpu-gic.md`); `MIGRATE_INFO_TYPE` differs |
| SYSC | FULL for the three ID registers; other offsets honest-fault | sub-word access; every register firmware uses (M7) |
| Unmapped space | honest-fault | — |

## Decisions

- Applies DR-0003 option A as amended: one `iidr` property.
- No new DR: the remaining choices follow the reviewed spec. Naming (`r9a07g054`, `rzv2l-smarc`, `renesas-rzg2l-sysc`) follows QEMU conventions and may change if upstreaming is ever pursued.
