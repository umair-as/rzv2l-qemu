# AGENTS.md

This is the canonical orientation for AI coding agents working in this repo. It is agent-agnostic. Claude-specific extras live in `CLAUDE.md`.

## What this repo is

`qemu-rzv2l` develops a QEMU machine model of the **Renesas RZ/V2L SMARC EVK** (SoC R9A07G054L2: 2× Cortex-A55, GIC-600, 2 GB DDR4). The aim is to run software built for the real board **without modifying that software**.

The specification is `docs/spec/project.md` (v0.2). The requirements are in `docs/spec/requirements.md`, and v0.1 is archived in `docs/spec/archive/`. Read the spec before any hardware-facing work.

The project is **standalone**. Guest artifacts come in three tiers:

| Tier | Guest | Role |
|---|---|---|
| G0 | mainline Linux + upstream `r9a07g054l2-smarc.dtb` + BusyBox initramfs | primary acceptance |
| G1 | Renesas vendor BSP (`linux-renesas`, Renesas TF-A / U-Boot, OP-TEE) | acceptance |
| G2 | downstream products built on the BSP | integration profiles only |

G2 consumers never define acceptance and are never a build dependency. Their build outputs may be *studied* as samples of real vendor firmware.

## Two repositories

```
qemu-rzv2l/                 this repo: spec, research, evidence, tests, guest builds, scripts
└── qemu/                   submodule → github.com/umair-as/qemu (fork of qemu/qemu)
      rzv2l-base            pinned upstream base (v11.1.2); never commit here
      rzv2l-dev             the port; `git diff rzv2l-base...rzv2l-dev` is the whole port
```

- The fork contains **only** what upstream QEMU could accept: `hw/`, `include/hw/`, `tests/qtest/`, `docs/system/arm/`, Kconfig/meson wiring. No agent files, specs or evidence.
- Project tags use the `rzv2l-vX.Y` namespace, never bare `vX.Y`, which collides with QEMU's own tags.
- Rebasing the base is a deliberate, recorded decision (`docs/decisions/`), not routine.

## Upstream provenance: read this before writing QEMU code

QEMU's policy (`qemu/docs/devel/code-provenance.rst`, section "Use of AI-generated content") is to **decline contributions that include or derive from AI-generated content**. It **allows** AI for research, API/algorithm investigation, static analysis and debugging, provided that output is not included in the contribution.

Consequences for this project:
- Device-model code an agent writes on `rzv2l-dev` is **not upstreamable as-is**. Upstream is a later goal, conditional on the emulation succeeding. A submission will need human-authored code. Agent-written code serves as the working prototype and test oracle.
- Agents can contribute freely to the parts upstream never sees: evidence packets, research notes, device maps, test plans, guest build scripts, oracle captures, validation reviews and debugging.
- Every agent-touched commit in **both** repos carries an `Assisted-by:` trailer (see Commit style). That way it is always mechanically clear which fork commits must be rewritten by a human before any upstream submission. Never omit or strip it.

## Engineering rules (from the spec, non-negotiable)

1. **Evidence before implementation.** Every hardware-facing change cites:
   - the MMIO range, IRQ, clocks, resets and reset values it implements
   - the hardware manual section
   - the guest source path (driver/DTS/firmware, with file:line)
   - its fidelity class
   - what it does not support
   - how it was verified

   If it has no evidence, it is an experiment, recorded under `docs/experiments/`.
2. **Label every claim:** documented fact / code-derived inference / hardware observation / assumption.
3. **Check the effective build configuration** (compile log, `.config`, `conf.mk`), not just source defaults, before claiming what firmware or a kernel does. Two earlier "findings" failed exactly this check.
4. **Never modify the guest to fit the model.** No guest DT edits, driver patches, firmware patches or invented kernel arguments. A needed boot argument or loader fixup is recorded as a fidelity gap.
5. **Failure policy:** observe → find the first unmet guest expectation → trace it to guest code → find the hardware contract → change the smallest model → retest. Arbitrary register constants, invented status bits and disabled drivers are forbidden, except as recorded experiments.
6. **Never silently wrong.** A model either behaves as the hardware does, or fails honestly in a way the guest can see. Classes:
   - FULL / FUNCTIONAL / STUB / UNSUPPORTED (how much is modelled)
   - honest-fault vs silent-wrong (whether it lies). Silent-wrong is never acceptable.
7. **Booting is not proof of fidelity.** Device behaviour is verified by qtests that assert **hardware-manual** values (reset values, capability/ID registers), not by the model's own prior output. Tests are mutation-checked: break the model and confirm the test goes red.
8. **Name the layer you verified.** "At layer N the cause is X" — don't claim the root cause until you've shown it.
9. **Two start states.** Firmware mode: devices start at manual reset values. Direct-kernel mode: devices start at the measured *post-firmware* state, i.e. what TF-A/U-Boot leave behind. Keep both explicit in each model.

## Board facts already established (evidence: `docs/research/boot-chain-firmware.md`, `docs/experiments/`)

- The kernel is entered at **NS-EL1**, not EL2: EVK logs and TF-A `RCAR_BL33_EXECUTION_EL`.
- PSCI goes over SMC. CPUs are `cpu@0` and `cpu@100`, so set `mp-affinity` = `0x0`, `0x100`.
- `CNTFRQ` = 24 MHz. TF-A copies it from SYC `CNTFID0`; the DT timer has no `clock-frequency`.
- BL2 panics unless `SYS_LSI_DEVID[27:0] == 0x8447447`. U-Boot and BL2 read `SYS_LSI_MODE` @ `0x11020A00` for the boot source.
- Each CPG `CLK_MON`/`RSTMON` register must mirror its `CLK_ON`/`RST` register, or the U-Boot SDHI probe fails.
- The production OP-TEE panics without TSIP, a closed crypto IP. Emulation uses an OP-TEE rebuilt with `CFG_RZ_SCE=n`; TSIP is honest-fault.

## Repo layout

```
docs/spec/          specification v0.2+, requirements, acceptance, traceability
docs/device-map.md  MMIO/IRQ/clock/reset map with evidence per row
docs/sources.md     source register (manuals, pinned guest/firmware sources)
docs/research/      per-block research (scif, cpg-reset, cpu-gic, boot-dependency-graph, …)
docs/decisions/     decision records (context, evidence, alternatives, decision, revisit condition)
docs/experiments/   experiment records (EXP-NNN-*.md): question, setup, observations, conclusions
docs/evidence/      EVK captures; each records board, image/build ID and **boot stage** (ROM/BL2/U-Boot/post-Linux)
tests/hello-rzv2l/  bare-metal first-character test (ELF)
tests/experiments/  sources and run scripts backing docs/experiments/
tests/guests/       G0/G1 guest build scripts (outputs gitignored)
tests/acceptance/   per-milestone run scripts + expected-output checks
scripts/            build/run helpers
artifacts/rzv2l/    manuals index, manifest.json, SHA256SUMS (PDFs and text extracts are gitignored: Renesas copyright)
```

## Sources

- Hardware truth: `artifacts/rzv2l/hardware/r01uh0936ej0150-rzv2l.pdf` (HW manual Rev 1.50). For grep, use the searchable text in `artifacts/rzv2l/text/`. Cite the **PDF** (section/table/page), not the text file.
- Board: the SMARC module UM (`r01uh0964ej0200`) and carrier UM (`r01uh0966ej0200`).
- When sources conflict: the manual is authority for intended layout and reset values, silicon for actual behaviour, and guest code for what is actually required. Record the conflict; never silently pick one.
- The BSP driver manuals (`bsp-drivers/`) describe software usage only. Treat them as leads.
- Reference QEMU ports: https://github.com/kylefoxaustin/qemu-imx93 and https://github.com/kylefoxaustin/qemu-imx95. Borrow method and structure, never RZ/V2L facts.

## Build and run (provisional; scripts land under `scripts/`)

```bash
git submodule update --init                    # qemu/ at the pinned rzv2l-dev commit
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs
ninja qemu-system-aarch64
```

Build out-of-tree under `build/` (gitignored). Never build inside `qemu/`.

Useful QEMU debugging (see `docs/imx95/methodology.md` in qemu-imx95):
- `-d unimp,guest_errors`: an acceptance run must have every unimplemented access fixed or listed.
- `-d nochain` plus gdb `hbreak` when TCG breakpoints misbehave.
- `-icount` only to debug races; never in boot tests.

## Hardware oracle (the physical EVK)

- **Read-only by default.** Writes to CPG, PMIC, WDT, eMMC boot partitions or QSPI need explicit operator approval.
- Use a project-owned debug image (G1) or U-Boot `md`. Hardened images typically block `/dev/mem`.
- Record whether a register read has side effects (FIFO pop, write-1-to-clear, read-to-clear).
- A measurement answers a specific question stated beforehand. Store it under `docs/evidence/`.

## Commit style

- **Project repo:** Conventional Commits, `<type>(<scope>): <subject>`, imperative mood, ≤72 chars. Scopes: `spec`, `docs`, `research`, `evidence`, `tests`, `scripts`, `artifacts`, `qemu` (submodule bumps).
- **QEMU fork (`rzv2l-dev`):** upstream QEMU style, `<subsystem>: <subject>` (e.g. `hw/arm: add RZ/V2L SoC skeleton`), with `Signed-off-by:` from the operator, `scripts/checkpatch.pl` clean, one logical change per commit.
- **AI attribution, both repos:** end every agent-touched commit with `Assisted-by: <tool>:<exact-model-id-you-are-running-as>`. Use one line per model that touched the change, in order. Never copy a model id from a doc or a past commit. **Do not add `Co-Authored-By:` lines for AI tools.**
- **Do not run `git commit`, `git push`, or submodule bumps without operator confirmation.**
