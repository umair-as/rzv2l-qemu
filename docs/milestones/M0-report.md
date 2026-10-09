# M0 report — research baseline

**Status:** **accepted by the operator, 2026-10-08.** DR-0003 decided: option A. EVK register reads are not needed to *start* M1; the GIC identity reads (EVK-R60–R66) are needed to *pass* its exit gate.
**Date:** 2026-10-08
**Spec:** `../spec/project.md` v0.3

## Exit criteria (spec §17)

| Criterion | Result |
|---|---|
| Sources pinned | `../sources.md`: HW manual Rev 1.50 + board manuals; G0 = linux v6.12.59; G1 = `rz_linux-cip` `rz-6.12-cip14` @ `212f6e88b7`; TF-A `f59ed5a31`, U-Boot `4eebfbaa4e`, OP-TEE `82a5cd3b`; QEMU base v11.1.2 |
| Device map | `../device-map.md` |
| Boot dependency graph | `../research/boot-dependency-graph.md` |
| §20 question answered | see below |
| EXP-001 | `../experiments/EXP-001-smc-and-impdef-sysregs.md` |
| Uncertainties recorded | each research note's "Claims to verify" / "Questions for the EVK"; consolidated in `../evidence/requests.md` |

## Deliverables

| Area | Documents |
|---|---|
| Research (reviewed by the operator against the HW manual) | `../research/{boot-chain-firmware,cpg-reset,sysc,scif,pinctrl,cpu-gic,boot-dependency-graph}.md` |
| Board evidence | `../evidence/EVK-2026-10-08-boot-log.md` |
| Decisions | DR-0001 (repo and fork shape), DR-0002 (secure-world staging); both accepted |
| Process | spec v0.3 work units (`../units/`), `../spec/traceability.md` |

## The §20 answer (G0 = v6.12.59, direct mode)

**(a) First earlycon character** needs:
- CPU at EL1, and RAM with the board's `/memory` (`0x48000000` + `0x78000000`)
- the DTB in x0
- a bare `earlycon` on the command line, which is a recorded fidelity gap
- SCIF0 at `0x1004B800` in the RZ/SCIFA layout: SCSCR read/write, FSR TDFE/TEND with manual clear semantics (TEND completes after, not inside, the FTDR write), FTDR to the chardev, and a usable post-firmware line state

Nothing else: earlycon starts in `setup_arch()` before the GIC, timer, PSCI, CPG, PFC, SYSC or OSTM are used.

**(b) First character through `ttySC0`** needs everything in (a) except the boot argument, plus:
- GIC-600 with the virtual-timer PPI (ID 27); CNTFRQ 24 MHz; PSCI over SMC
- SYSC `SYS_LSI_DEVID` reading `0x18447447`
- a CPG that probes first time: board clock rates; CLK_MON as a same-polarity mirror; RSTMON as an inverted mirror; MSTOP inert; GPIO resets released in the start state
- IRQC probing
- OSTM1/2 mapped and counting, with TE cleared by TT
- a PFC that probes and accepts the SCIF0 pin configuration; without it SCIF0 defers forever
- every earlier-probing built-in device mapped, so it fails softly

Evidence and the full trace are in `../research/boot-dependency-graph.md` §1–§6.

## Corrections made during M0

| What | Corrected to | Evidence |
|---|---|---|
| Kernel entry at EL2 (early review) | EL1 | EVK log; TF-A `bl2_plat_mem_params_desc.c:18` |
| RSTMON "mirrors" RST | an inverted mirror | HW manual p.409 vs p.450; `rzg2l-cpg.c`; TF-A `plat_pm.c` |
| PCHMON reads `0x08` | a PACCEPT handshake bit | TF-A `plat_pm.c:30-70` |
| SCIF probes after the deferred-probe timeout | defers forever | `drivers/pinctrl/devicetree.c:127-140` |
| Chip-ID SiP leak; QSPI offset bug (firmware study) | refuted | build configuration and updater logic |
| Manual DEVID conflict (Table 6.1 vs §6.3.43) | §6.3.43 is right: `0x18447447` | EVK BL2 prints |

## Proposed M1 slice: unit `M1-machine-skeleton` (for operator review)

**Goal:** `qemu-system-aarch64 -M rzv2l-smarc` instantiates the board's CPU, interrupt and memory topology plus the SYSC identity registers. No guest console output is expected yet; that is M2.

| Item | Content | REQ |
|---|---|---|
| SoC object + board | `TYPE_R9A07G054` (`hw/arm/r9a07g054.c`) + machine `rzv2l-smarc`, structured like `fsl-imx8mp`; RZ/G2L-ready | REQ-MACH-001 |
| CPUs | 2× cortex-a55: `mp-affinity` 0x0/0x100, CPU1 powered off, MIDR r2p0 (QEMU default `0x412FD050` matches the EVK) | REQ-MACH-002 |
| Counter frequency | CPU `cntfrq` = 24 MHz | REQ-MACH-003 |
| Entry state | `has_el2=false`, PSCI conduit SMC, `loader_start` `0x48000000` (configured in M1; **accepted in M3** when Linux reports EL1) | REQ-MACH-004 |
| DDR | 2 GiB at `0x40000000` | REQ-MACH-006 |
| GIC | `arm_gicv3`: distributor `0x11900000`, redistributors `0x11940000` (stride `0x20000`), 480 SPIs, no ITS | REQ-MACH-007 |
| SYSC | the minimal register set below | REQ-SYSC-001 |
| Other windows | the placeholder policy below | REQ-MAP-001 (initial classification only) |

### SYSC in M1: minimal supported set

`../research/sysc.md` shows that G0/G1 Linux reads exactly one SYSC register (`SYS_LSI_DEVID`), and firmware reads LSI_MODE/DEVID/PRR and, in Stage B, RVAL/RVAH and LP_CTL*.

| Offset | Register | M1 behaviour | Class |
|---|---|---|---|
| `0xA00` | `SYS_LSI_MODE` | read-only, from board property `boot-mode` (default `0x10203`, QSPI; values per the EVK evidence); writes ignored as on silicon | FUNCTIONAL, faithful |
| `0xA04` | `SYS_LSI_DEVID` | read-only `0x18447447`; writes ignored | FULL, faithful |
| `0xA08` | `SYS_LSI_PRR` | read-only `0x0` (dual A55); writes ignored | FULL, faithful |
| all other offsets | — | **UNSUPPORTED in M1**: logged as unimplemented (`LOG_UNIMP`), read as zero. This is **not** a fidelity claim: no M1 guest reads them. RVAL/RVAH, LP_CTL*, the access-control and address-translation registers get modelled behaviour in M7 (Stage B), where TF-A first uses them. | STUB (experiment) |

### Placeholder policy for other windows in M1

M1 runs no OS guest; its tests are qtests and a bare-metal test ELF. Any other window mapped in M1 is a **placeholder experiment**, not accepted guest behaviour:
- **Mapping is not fidelity.** A read-as-zero placeholder avoids an unmapped-access abort and nothing else. It does not prevent hangs (e.g. OSTM's TE spin), false success or a frozen clock.
- Each window's eventual class and milestone come from `../device-map.md` (model / honest-fault / evidence-backed read-as-zero / unmapped). REQ-MAP-001 is accepted only at M3b, after a per-window review.
- Placeholders that a later milestone's guest would rely on wrongly (OSTM, CPG, PFC) must be replaced by models **before** that milestone's acceptance run, never patched around.

### SYC (`0x11000000`) is not in M1

`CNTFID0` belongs to REQ-SYC-001 (M7). Its register layout is an **inference** (standard Arm counter-module layout) awaiting EVK-R50 and a manual cross-check. In M1 and direct mode, the counter frequency comes from the CPU `cntfrq` property (REQ-MACH-003). SYC stays unmapped until there is evidence about how it behaves.

### M1 start vs M1 exit

- **Needed to start M1:** nothing further. All M1 inputs are evidenced (EVK boot log, BL2 prints, notes).
- **Needed to pass the M1 exit gate** (spec §17: "a qtest reads GIC and SYSC ID registers equal to EVK values"): the SYSC part is ready; the GIC part needs EVK-R60–R66 (DR-0003 option A).

### DR-0003: GIC identity (decided: option A, `../decisions/DR-0003-gic-identity.md`)

| Option | What | Cost | Exit gate |
|---|---|---|---|
| **A. Faithful identity** | Make QEMU's `arm_gicv3` identity configurable for **both** the distributor and the redistributors (QEMU's `gicv3_iidr()` helper serves GICD_IIDR and GICR_IIDR, and the PIDR/CIDR blocks of both frames), and set them to the EVK values | Needs EVK-R60/R61 (GICD IIDR, PIDR/CIDR) **and** EVK-R62/R63/R65 (GICR IIDR, TYPER, PIDR2) before M1 exit; a generic QEMU change, subject to the project's provenance restrictions (spec §16) | unchanged: GICD and GICR identity == EVK |
| **B. Accepted gap** | Keep QEMU's hard-coded `0x43B`; record it as a fidelity gap | none now | **§17 must be amended** by an explicit reviewed change: "GIC placement and SPI count verified; GIC identity is a recorded gap" |
| **C. Defer** | Exit M1 on placement only; identity moves to a later unit | none now | amend §17 to move the identity check; track it in traceability |

**Decision (operator, 2026-10-08):** option A.

### M1 tests (proposed)

- qtest: SYSC LSI_MODE / DEVID / PRR values vs the EVK, writes ignored, and the unimplemented offsets logged; mutation-checked.
- qtest: GIC placement (distributor/redistributor bases, `GICD_TYPER` ITLinesNumber for 480 SPIs, `GICR_TYPER` affinity and Last bit per CPU). GIC identity per DR-0003: under option A, GICD_IIDR, GICR_IIDR and both frames' PIDR/CIDR equal the EVK values (EVK-R60–R66).
- Test ELF: reads MPIDR on both cores (CPU1 via PSCI CPU_ON), MIDR, CNTFRQ, CurrentEL; results checked through a memory mailbox via qtest/gdbstub, since there is no UART until M2.
- Script: `info mtree` / `info qtree` diffed against `../device-map.md`.

## Requirement changes from M0

Added to `../spec/requirements.md` as PROPOSED; `requirements.md` is the canonical ID list, and spec §10 is aligned to it:
- **REQ-OSTM-001:** OSTM counts at P0 and clears TE on TT.
- **REQ-IRQC-001:** the IRQC is mapped so its driver probes.
- **REQ-MAP-001:** every DTB-U window gets a per-window classification and target milestone. Mapping alone is not a fidelity claim.
- **REQ-MACH-008:** modelled MMIO and interrupt placement matches the stock DTB (previously spec §10's REQ-MACH-006 wording).
- **REQ-SYC-001:** SYC `CNTFID0` at M7, split out of REQ-MACH-003, which now covers CPU `CNTFRQ` only.

Reworded: **REQ-CPG-001** now states `CLK_MON` = `CLK_ON` and `RSTMON` = `~RST & mask`, with WEN behaviour and a mutation-checked polarity test.

## Open (carried into M1)

- **EVK register reads** (`../evidence/requests.md`): post-firmware CPG, PFC, SCIF0, PLL and CNTFID0 values, and the GIC distributor and redistributor identity (EVK-R60–R66). Those GIC reads matter for M1's exit gate under option A; the rest are needed before M2/M3b.
- Cache topology: QEMU's A55 reports an L2 that the silicon lacks (HW manual p.83). Decide in M1 whether to override the cache ID registers or record a gap.
- **Effective configuration:** the G0 research used the arm64 `defconfig` source. The built G0 kernel's effective `.config` has not been checked. It must be, before M3 acceptance, per AGENTS.md rule 3.
- `ID_AA64PFR0_EL1.EL2` will read 0 with `has_el2=false`, while the silicon implements EL2 (device-map gap 14, an assumption).
