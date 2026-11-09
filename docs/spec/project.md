# qemu-rzv2l — Engineering Specification v0.4

**Status:** v0.4. v0.3 was accepted with the M0 exit review; §22 lists the changes.
**Target:** Renesas RZ/V2L SMARC EVK (SoC R9A07G054L2)
**Date:** 2026-10-08

**Companion documents:**

| Document | Content |
|---|---|
| `requirements.md` | requirement catalogue |
| `../device-map.md` | address/IRQ/clock map (M0 deliverable) |
| `../research/boot-chain-firmware.md` | firmware study |
| `../decisions/` | decision records |
| `traceability.md` | requirement → unit → task → test → evidence |
| `../units/` | per-milestone work units (spec, design, tasks) |

---

## 1. Intent

`qemu-rzv2l` implements a QEMU machine model of the RZ/V2L SMARC EVK. The model must be faithful enough that software built for the physical board runs **without modification**.

It is not a generic AArch64 platform; QEMU's `virt` already serves that purpose. It models the board's actual CPU topology, address map, interrupts and peripherals, to the level guest software can observe.

The RZ/V2L is the first target because:
- there is public hardware documentation (HW manual Rev 1.50, more than 3,500 pages)
- upstream and vendor Linux, TF-A, OP-TEE and U-Boot all support it
- **the physical EVK is available as a behavioural oracle**

Longer term, the project is a calibration platform for a method of modelling an SoC without the hardware (§21).

## 2. Scope and dependency stance

The project is **standalone**. Acceptance is defined only by guest artifacts this project builds or fetches itself, pinned by commit or hash:

| Tier | Guest | Role |
|---|---|---|
| **G0: OSS reference** | mainline Linux `Image` (arm64 defconfig), upstream `r9a07g054l2-smarc.dtb`, static BusyBox initramfs | primary acceptance; future upstream functional test |
| **G1: vendor reference** | Renesas BSP: `linux-renesas` (CIP), Renesas TF-A fork, Renesas U-Boot, OP-TEE | acceptance for vendor-only drivers and the firmware chain |
| **G2: consumers** | downstream products built on the BSP | integration profiles; never acceptance, never a build dependency |

G2 builds may be studied as real-world samples of G1 firmware (see `../research/boot-chain-firmware.md`).

## 3. Success definition

```
G0/G1 artifacts ── TF-A BL2/BL31 ── OP-TEE ── U-Boot ── FIT ── Linux + DTB ── userspace
                                         │
                              qemu-system-aarch64 -M rzv2l-smarc
```

The emulator provides **software-visible functional compatibility** for each modelled device. It does not attempt cycle accuracy, analogue behaviour, or anything the guest cannot observe.

## 4. Governing principle

Every model decision answers three questions:

| Question | Derived from |
|---|---|
| What does the guest expect? | DTS, driver, firmware |
| What does the hardware do? | manual + EVK observation |
| What must QEMU reproduce? | guest-observable behaviour minus irrelevant physical detail |

We model **behavioural contracts**.

## 5. Source authority

Sources are ranked by **domain**, not by a single list:

| Domain | Authority |
|---|---|
| Register layout, bit meaning, reset values | RZ/V2L Hardware User's Manual (`artifacts/rzv2l/hardware/r01uh0936ej0150-rzv2l.pdf`) |
| Board wiring and topology | SMARC module UM `r01uh0964ej0200`, carrier UM `r01uh0966ej0200` |
| Actual behaviour | the physical EVK (silicon) |
| What is required | guest code: DTS, Linux drivers, TF-A, U-Boot, OP-TEE, **as built** |
| Emulation mechanisms | upstream QEMU |
| Leads only | BSP driver manuals, other QEMU machine models, issues, blogs |

**Conflict rule:** when sources disagree, the disagreement is recorded as evidence. Silicon decides behaviour; the manual decides intended layout. No source is silently overridden.

**Effective-configuration rule:** a claim about firmware or kernel behaviour must be checked against the effective build configuration (compile log, `.config`, `conf.mk`). Source defaults alone are not enough.

## 6. Evidence rule

Every hardware-facing model or connection records:

| Field | Required |
|---|---|
| MMIO range | yes |
| IRQ numbers and trigger | when applicable |
| Clocks and resets consumed | when applicable |
| Reset value *and* post-firmware value (§9) | when applicable |
| DMA relationship | when applicable |
| Guest consumers (driver/firmware path, file:line) | yes |
| Manual reference (section/table/page of the PDF) | yes |
| Existing QEMU analogue | if any |
| Fidelity class + honesty class (§7) | yes |
| Unsupported behaviour | yes |
| Verification method | yes |

Claims are labelled **fact / code-derived inference / hardware observation / assumption**. Work without evidence is an *experiment*, recorded under `../experiments/`.

## 7. Fidelity classification

Every device has two independent classifications.

**Depth**
- **FULL**: documented software-visible behaviour, for the intended use.
- **FUNCTIONAL**: the subset supported guests need, with limitations listed.
- **STUB**: the minimum state for guest initialisation to continue. Visible in the docs.
- **UNSUPPORTED**: not emulated.

**Honesty**
- **faithful**: behaves as the hardware does, for what is modelled.
- **honest-fault**: the guest receives a visible failure (error status, probe failure, documented panic).
- **silent-wrong**: reports success without the effect. **Never acceptable.** A silent-wrong discovered in a model is a BLOCKER.

**Mapping to QEMU mechanisms**

| Mechanism | Guest sees | Allowed for |
|---|---|---|
| Real device model | modelled behaviour | FULL / FUNCTIONAL |
| `create_unimplemented_device()` | reads 0, ignores writes, logs under `-d unimp` | STUB only where the guest only writes, or where reading 0 is a faithful reset-like value; must be listed |
| Unmapped region | synchronous external abort | UNSUPPORTED regions the board also faults on (to be measured) |
| Unmapped region over working silicon | synchronous external abort | a recorded fidelity gap, only while the coverage list shows no guest at the current milestone touches the window and the window is listed in `../device-map.md` §4 for the M3b per-window review (DR-0005). The abort is honest-fault |

What a powered-down or clock-stopped module does on silicon (hang, zero, abort) is an open question for the oracle (§14).

## 8. Guest integrity

- **REQ-GUEST-001.** Acceptance guests use their stock DTB, **unmodified before loader fixups**.
- **REQ-GUEST-002.** Guest drivers are never patched to suit the emulator.
- **REQ-GUEST-003.** Firmware contains no QEMU-specific changes for acceptance. *Exception:* a firmware **build configuration** may be changed when a closed hardware dependency cannot be emulated honestly. Such a change is recorded as a fidelity gap. Example: OP-TEE `CFG_RZ_SCE=n`, §12.
  *Second exception:* a project **boot-policy profile** may build a pinned firmware source with a listed configuration fragment and listed upstream source patches, to demonstrate a software decision of §12 (FIT signatures, slot selection, rollback). The vendor-default build stays as the regression profile, and the fragment is listed as a fidelity gap (`../decisions/DR-0008-m9-boot-policy-profile.md`).
- **REQ-GUEST-004.** Any boot argument, injected DT node or loader behaviour present in an acceptance run is listed as a fidelity gap.

**Acceptance DTBs**
- **DTB-U**: the upstream mainline DTB (G0).
- **DTB-V**: the vendor kernel DTB (G1).
- Consumer DTBs, such as a DTB carried in a signed FIT, belong to G2 profiles.

**Loader fixup contract.** On the board, U-Boot changes the kernel DT before boot. In direct-kernel mode, QEMU's loader replaces U-Boot. The measured G1 list is in `../research/boot-chain-firmware.md` §5:
- `/memory`
- `/chosen` properties
- `/firmware/optee` injection
- `kaslr-seed` (only when the OP-TEE RNG works)
- boot-source and supply properties

Each fixup is either replicated or listed as a gap. QEMU's own `/memory` rewrite must produce the board's value (`0x48000000` + `0x78000000` for the 2 GB EVK).

**Live-DT acceptance test.** Compare `dtc -I fs /sys/firmware/devicetree/base` on the EVK with the same output from the QEMU guest, using the same guest artifacts. Every difference is explained.

## 9. Start states

The machine supports two explicit start states.

| State | Devices start at | Used by |
|---|---|---|
| **Firmware mode** | Hardware Manual reset values | real BL2 or BL31 entry (M7, M8) |
| **Direct mode** | the **post-firmware state**: what TF-A and U-Boot leave behind, measured on the EVK (U-Boot `md` before `bootm`) and traced to the firmware code that writes it | `-kernel` boot (M3–M6) |

What direct mode must reproduce (`../research/boot-chain-firmware.md`):
- entry at **NS-EL1**
- `CNTFRQ_EL0` = 24 MHz
- the GIC configured for the non-secure world
- PSCI available over SMC
- CPG clocks and resets on for firmware-enabled modules
- SCIF0 pin function selected
- WDT0 running, if a U-Boot path is being mimicked

Each device model keeps its reset value plus an optional post-firmware overlay that is applied only in direct mode.

**Oracle corollary.** Every EVK measurement records its **boot stage** (ROM / BL2 / U-Boot / post-Linux) and the image or build ID. Post-Linux register state is neither the reset state nor the post-firmware state.

## 10. Machine identity and topology

The canonical statements, evidence and status live in `requirements.md`; this section summarises them by ID.

- **REQ-MACH-001.** QEMU exposes `-M rzv2l-smarc`, built as a SoC container `TYPE_R9A07G054` (CPUs, GIC, on-chip devices) plus a board machine (DDR size, SD/eMMC attachment, board devices), following `hw/arm/fsl-imx8mp.c` / `imx8mp-evk.c`. The SoC is written so RZ/G2L (R9A07G044) can be added later. The final name follows QEMU conventions.
- **REQ-MACH-002.** 2× `cortex-a55`: `mp-affinity` `0x0`/`0x100` (DT `cpu@0`, `cpu@100`); the second CPU starts powered off; the MIDR identifies as Cortex-A55 r2p0 (TF-A panics otherwise; EVK MIDR `0x412FD050`).
- **REQ-MACH-003.** `CNTFRQ_EL0` reads 24 MHz (CPU `cntfrq` property). The SYC counter-module register `CNTFID0` is a separate requirement, REQ-SYC-001.
- **REQ-MACH-004.** Direct mode enters the kernel at NS-EL1 with PSCI over SMC.
- **REQ-MACH-005.** The A55 IMPDEF system registers the real firmware touches are present. Per EXP-001: `CPUPWRCTLR_EL1` is required; `CLUSTERIDR_EL1`/`CLUSTERCFR_EL1` are precautionary. QEMU 11.1.2's `cortex-a55` defines none of them.
- **REQ-MACH-006.** DDR appears where software expects it: base `0x40000000`; Linux-visible window `0x48000000` + `0x78000000` on the 2 GB EVK.
- **REQ-MACH-007.** GIC-600 distributor and redistributors at the stock DTB addresses, with no ITS.
- **REQ-MACH-008.** Modelled MMIO devices and interrupts sit at the addresses and SPI numbers of the stock DTB and firmware.

## 11. SoC contract (initial dependency set)

The exact register map and dependencies are not frozen here; they are derived into `../device-map.md`.

| Block | Why it is early | Treatment |
|---|---|---|
| Cortex-A55 ×2, GIC-600 (GICv3, no ITS), generic timer | core | existing QEMU models + REQ-MACH-002/003/004/005/007 |
| PSCI | SMP, reset, power-off | QEMU built-in (Stage A) → real BL31 (Stage B) |
| **SYSC** @ `0x11020000` | `LSI_DEVID` (BL2 panics unless `0x8447447`), `LSI_MODE` @ `0x11020A00` (boot source), `RVAL/RVAH` (CPU_ON), `LP_CTL5` ack (CPU_OFF), `CNTFID0` (SYC) | functional, early |
| **CPG** @ `0x11010000` | clock + reset + PM-domain provider. `CLK_MON` = `CLK_ON` (same polarity); `RSTMON` = `~RST & implemented_mask` (inverted: 1 = in reset); writes honour the `*_WEN` halves. CA55 reset and power handshake (`PCHCTL`/`PCHMON`). CPU OPP divider (no busy poll) | functional, early |
| **PFC / pinctrl** @ `0x11030000` | SCIF0 has `pinctrl-0`; without pinctrl, `sh-sci` defers forever | functional, early |
| **SCIF0** @ `0x1004B800` | console. RZ/SCIFA register layout; `FSR.TEND` and FIFO counts; baud divisor not enforced | functional, M2 |
| **IRQC (IA55)** @ `0x110A0000` | hierarchical IRQ domain for external/GPIO IRQs | investigate in M0 |
| **WDT0** | U-Boot auto-starts it (60 s); PSCI `SYSTEM_RESET` via the parity-error force register | functional by M4 |
| DMAC (`rz-dmac`) | SCIF/SDHI DMA; PIO fallback exists | later |
| **OTP** | chip ID @ `0x11861140` (OP-TEE HUK) | stub with a documented value |
| **RPC / SPIBSC** | U-Boot rewrites the SPI-NOR NVCR every boot; BL2 SPI boot | functional by M7 |
| **SDHI0/1** | storage. PIO at U-Boot level (doubled offsets, 64-bit data port); Linux adds DMA. No QEMU model exists; reuse the `hw/sd` card/eMMC models | M5 |
| ravb (GbE) + MDIO/PHY | networking; no QEMU model | M6 |
| DDR controller + PHY | BL2 training (507 params, 5 passes, ~11 polls); register-file stub | M8 |
| **TSIP** @ `0x11850000` | closed crypto engine; production OP-TEE needs it | UNSUPPORTED, honest-fault (§12) |
| RIIC + PMIC, versaclock | board devices; not touched before Linux | probe failure accepted early |
| Cortex-M33, DRP-AI, GPU, video, USB, CAN, audio | — | deferred (§18) |

## 12. Secure world and the limits of security claims

**Staging**

| Stage | EL3 / S-EL1 | Boot path | Milestone |
|---|---|---|---|
| **A** | QEMU built-in PSCI; no BL31/BL32 | direct kernel boot; DT without the OP-TEE node | M3–M6 |
| **B** | real **BL31**, entered directly with machine-built BL2→BL31 parameters, + **OP-TEE rebuilt with `CFG_RZ_SCE=n`** | real U-Boot → FIT → Linux | M7 |
| **C** | real **BL2** from a machine-staged SPI image (no boot-ROM model) + DDR stub | full chain | M8 |
| **N** | production OP-TEE with TSIP read-as-zero | negative test: expect `Failed to initialize SCE` and the panic | regression |

- Non-PSCI SMCs (OP-TEE probe, SiP) must not crash the guest in Stage A. EXP-001 showed that QEMU's PSCI handler, with SMC conduit, returns `NOT_SUPPORTED` for every unknown SMC, so no extra responder is needed. Linux's optee probe then fails honestly.
- **TZC-400 is not enforced.** The board as built (TF-A `TRUSTED_BOARD_BOOT=0`) leaves DDR accessible to the normal world. Enforcing TZC would make the model *more* restrictive than the silicon. Revisit if a G1 build enables TBB.

**The emulator cannot prove:**
- TrustZone memory isolation
- boot-ROM secure boot and anything fuse- or ROM-enforced
- physical attacks (timing, glitching, JTAG)

**The emulator can demonstrate** software decisions: FIT signature enforcement, bootcount and rollback logic, A/B selection, dm-verity behaviour.

## 13. Verification mechanisms

| Gate | What it shows |
|---|---|
| **qtest per device** (kernel-free, CI) | register behaviour against **manual** values: reset values, ID and capability registers, command/status semantics |
| **Mutation check** of each qtest | the test fails when the model's load-bearing behaviour is broken |
| **Unimplemented-access gate**: `-d unimp,guest_errors,invalid_mem` during acceptance runs | every access is either modelled or listed |
| **Oracle diffs**: live DT, `/proc/iomem`, `/proc/interrupts`, boot-log probe order, ID registers | model vs EVK |
| **Acceptance runs** per milestone (scripted, expected output) | software paths work |
| ASan/UBSan build of the device models | memory safety |

A successful boot is evidence that a software path works. It is **not** evidence that a device is faithful.

## 14. Hardware oracle

- The EVK is queried to answer a specific engineering question, stated before the measurement.
- **Read-only by default.** Writes to CPG, PMIC, WDT, boot media or QSPI need operator approval.
- Use a project-owned G1 debug image (`/dev/mem` available) or U-Boot `md`.
- Record any read side effects (FIFO pop, write-1-to-clear, read-to-clear), plus the boot stage and build ID.
- Store captures in `../evidence/`.

## 15. Workflow

**Pipeline:** Requirement → Research → Evidence packet → Design decision → Implementation → Focused test → Independent validation → VERIFIED.

**Requirement states:** PROPOSED · ACCEPTED · IMPLEMENTING · IMPLEMENTED · VERIFIED · DEFERRED · REJECTED. IMPLEMENTED ≠ VERIFIED.

**Requirement fields:** ID · Statement (SHALL, testable) · Rationale · Evidence · Dependencies · Verification · Milestone · Status. One evidence packet may cover a whole device.

**Decision records** (`../decisions/DR-NNNN-*.md`) are required where reasonable alternatives exist. Fields: Context · Evidence · Alternatives · Decision · Consequences · Unknowns · Revisit condition. An agent may propose a decision; architecturally significant ones need human review.

**Work units** (`../units/<unit>/`). Each milestone slice is a unit with two files (`../units/README.md`):

| File | Content |
|---|---|
| `spec.md` | one page: the REQ IDs, scope, what the guest needs, the exit criterion, the evidence it rests on |
| `tasks.md` | a short table of tasks and the tests that prove them, and one proof line per test (the mutation → the red line) |

`traceability.md` links every REQ to its unit, tests and evidence; it and the requirement statuses are updated once per release. M1 and M2 also have a `design.md`, written under the earlier three-file form (§22).

**Fidelity bugs** use `../units/templates/fidelity-bug.md`: observed behaviour, expected behaviour (with evidence), unchanged behaviour (what must not regress), and the layer verified.

**Actor / validator.** The validator asks what evidence would show the requirement is *not* met. It checks:
- addresses, IRQs and reset/post-firmware state
- unimplemented accesses
- traceability and reproducibility
- guest modifications
- the claimed fidelity and honesty

Findings are classed BLOCKER / FIDELITY GAP / LATER SCOPE / DOCUMENTATION.

## 16. Repository, fork and provenance

- This repo holds the spec, research, evidence, tests and guest builds. The QEMU fork `github.com/umair-as/qemu` is the submodule `qemu/`:
  - `rzv2l-base` = upstream `v11.1.2`
  - `rzv2l-dev` = the port

  See DR-0001.
- The fork carries only upstream-shaped content. Before any submission, the port is rebased onto QEMU master.
- **Upstream provenance.** QEMU declines contributions that include or derive from AI-generated content (`qemu/docs/devel/code-provenance.rst`). Agent-written device code is a prototype and test oracle. Upstream submission, if pursued, needs human-authored code. Provenance is stated once, in the README: all of `rzv2l-dev` beyond `rzv2l-base` is agent-assisted.

## 17. Milestones

| M | Name | Exit criterion |
|---|---|---|
| **M0** | Research baseline | sources pinned; `device-map.md`; boot dependency graph; §20 question answered; EXP-001 done; uncertainties recorded |
| **M1** | Machine skeleton | `-M rzv2l-smarc` with 2× A55 (REQ-MACH-002), GIC-600, timer, DDR, SYSC ID registers. `info mtree`/`info qtree` match `device-map.md`; a qtest reads GIC and SYSC ID registers equal to EVK values |
| **M2** | First character | `tests/probes/hello-rzv2l/` (an arm64 Image built from an ELF) prints `Hello from RZ/V2L` through SCIF0 @ `0x1004B800` in direct mode; SCIF qtest passes against manual reset values |
| **M3** | G0 Linux | mainline `Image` + DTB-U + BusyBox initramfs → shell. **M3a:** earlycon output. **M3b:** console via `sh-sci`, with CPG, pinctrl and PM domains probed. Both CPUs up via PSCI. All boot arguments and gaps listed |
| **M4** | G1 Linux | vendor kernel + DTB-V + initramfs userspace → shell; probe failures understood and listed; WDT0 behaviour defined |
| **M5** | Storage | SDHI + SD/eMMC with the real `renesas_sdhi` driver; ext4 read/write/sync verified against the image |
| **M6** | Networking | ravb + PHY with the stock driver; DHCP and data integrity |
| **M7** | U-Boot + Stage B | real BL31 + OP-TEE (`CFG_RZ_SCE=n`) + real U-Boot → Linux from SD; Linux reaches OP-TEE (driver, `/dev/tee0`, a trusted-application call; DR-0006). FIT moves to M9 |
| **M8** | Stage C | real BL2 (DDR stub, SPI boot) → full chain |
| **M9** | Platform behaviour | A/B selection, bootcount, rollback, FIT signature enforcement and rejection, storage corruption, update failure, within the §12 limits |

## 18. Non-goals (initially)

- DRP-AI, GPU, camera, display, USB, audio, CAN
- the Cortex-M33 (only its acknowledge bits are modelled)
- boot-ROM simulation: BL2 is staged by the machine
- TSIP emulation
- TZC enforcement
- cycle-accurate timing, power modelling
- every RZ/V2L peripheral

A block comes into scope when a milestone depends on it.

## 19. Failure policy

**Sequence:** observe → first unmet guest expectation → guest code → hardware contract → smallest model change → retest.

**Allowed outcomes for a failing probe:**
- stub (blind writes only)
- promote the stub to a model (the guest reads back or polls)
- extend an existing model
- **accept a bounded, honest probe failure** (documented)
- trim the DT **only** for hardware the board does not populate. Never for hardware it has.

**Forbidden except as recorded experiments:**
- guest DT edits
- driver patches
- arbitrary register constants
- invented status bits
- global kernel workarounds
- disabling drivers

## 20. M0 objective and acceptance question

The M0 agent session establishes evidence; it does not build the machine. It produces:
- `../sources.md` (pinned)
- `../device-map.md`
- `../research/boot-dependency-graph.md`
- `cpu-gic.md`, `scif.md`, `cpg-reset.md`, `pinctrl.md`, `sysc.md`
- EXP-001
- a proposed M1 slice
- open questions

**Acceptance question, in two parts.** Starting from QEMU executing the first instruction of the G0 kernel in direct mode, which emulated components and guest-visible behaviours are required before Linux prints:
- **(a)** its first character via earlycon, and
- **(b)** its first character via the real `sh-sci` console driver?

M0 is incomplete until both answers can be defended from evidence.

## 21. Methodology goal

RZ/V2L, with hardware available, calibrates the method: build the model, measure it against silicon, and refine the evidence, retrieval and validation process. A later SoC without hardware is where the method itself becomes the experiment.

## 22. Changes

### v0.3 → v0.4

- §8: REQ-GUEST-003 gets a second exception, a project boot-policy profile with a listed configuration fragment and listed upstream source patches (DR-0008), for M9.
- §15 requirements, at the v2.0 closure: REQ-BOOT-001 to REQ-BOOT-008 added for M9 (signed FIT images, slot selection, commit, rollback, damaged environment copies, updates and their interruptions); REQ-SYSC-002's verification moves from U-Boot, which prints no boot source, to BL2's own output and its choice of the FIP's device (M8). 45 of 46 requirements verified; REQ-TSIP-001 still needs a production OP-TEE that public sources cannot build.

### v0.3 errata (2026-11-04)

- §15 requirements: REQ-RPC-001 added for the SPI multi I/O bus controller and the module's QSPI flash, which §11 has functional by M7 (unit M7-rpc-spinor); statuses and traceability updated at the v1.1 closure.

### v0.3 errata (2026-10-29)

- §15 work units, from M3b on: one-page `spec.md` (scope, what the guest needs, exit criterion, evidence); `design.md` dropped; `tasks.md` a short table with one mutation line per test; `traceability.md` and requirement statuses updated once at v1.0, not per unit (DR-0004 amendment 2026-10-29).
- §17 M2 and REQ-TEST-001: the hello program lives in `tests/probes/hello-rzv2l/`, next to the other guest probes, and is an arm64 Image (M2 unit decision (a)).
- §7 mechanism table: an unmapped window over working silicon is allowed as a recorded fidelity gap under two conditions (DR-0005, open question R23).

### v0.3 errata (2026-10-27)

- §16 Upstream provenance: per-commit `Assisted-by:` trailers dropped; provenance is stated once in the README (DR-0004).

### v0.3 errata (2026-10-09)

- §17 M1: the CPU requirement reference corrected to REQ-MACH-002 (was REQ-MACH-003, the counter-frequency requirement).
- `../learning/` removed; manual citations are checked by an independent agent review.

### v0.2 → v0.3 (2026-10-08)

- Guest kernels pinned: G0 = mainline v6.12.59, G1 = `rz_linux-cip` `rz-6.12-cip14` @ `212f6e88b7` (same mainline base; see `../sources.md`).
- §15: spec-driven work units (`spec`/`design`/`tasks`, EARS acceptance, task IDs traced to REQs), `traceability.md`, and a fidelity-bug template.
- DR-0002 accepted; DR-0003 (GIC identity) accepted, option A.
- M0 deliverables assembled: research notes, device map, EVK evidence and requests, M0 report. Operator exit review done 2026-10-08.
- Requirement IDs in §10 aligned with `requirements.md`; REQ-MACH-008 (MMIO/IRQ placement) and REQ-SYC-001 (CNTFID0, split from REQ-MACH-003) added.

### v0.1 → v0.2

- Added the standalone stance with the G0/G1/G2 tiers (§2). Downstream consumers moved from milestone targets to profiles.
- The source hierarchy became authority domains plus a conflict rule and the effective-configuration rule (§5).
- Added the honesty axis and the QEMU mechanism mapping to fidelity (§7).
- REQ-GUEST-001 now reads "before loader fixups". Added the build-config exception, the loader fixup contract, the live-DT test and the DTB naming (§8).
- New: start states and the post-firmware overlay (§9).
- Machine: the SoC + board structure, MPIDR, CNTFRQ, IMPDEF sysregs and **EL1 entry** (§10).
- SoC contract: added PFC, SYSC details, IRQC, WDT, OTP, RPC, TSIP and DDR (§11).
- New: secure-world staging A/B/C/N, the TZC stance and the list of what cannot be proven (§12).
- New: verification mechanisms (§13).
- New: oracle policy (§14).
- New: fork shape and the QEMU AI-provenance policy (§16).
- Milestones: M3 split into earlycon and real driver; M3 uses G0, M4 uses G1 userspace; M7 merged with Stage B; M8 = Stage C (§17).
- Path-C failure outcomes (§19).
- The M0 question split into (a) and (b) (§20).
