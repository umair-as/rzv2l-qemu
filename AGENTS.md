# AGENTS.md

This is the canonical orientation for AI coding agents working in this repo. It is agent-agnostic. Claude-specific extras live in `CLAUDE.md`.

## What this repo is

`qemu-rzv2l` develops a QEMU machine model of the **Renesas RZ/V2L SMARC EVK** (SoC R9A07G054L2: 2× Cortex-A55, GIC-600, 2 GB DDR4). The aim is to run software built for the real board **without modifying that software**.

The specification is `docs/spec/project.md` (v0.3). The requirements are in `docs/spec/requirements.md` (the canonical requirement IDs), and traceability is in `docs/spec/traceability.md`. v0.1 is not tracked; spec §22 summarises the changes. Read the spec before any hardware-facing work.

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

## How work flows

| Role | Who | Does | Does not |
|---|---|---|---|
| Operator | the human owner | designs and reviews specs, unit specs, decisions; approves EVK actions, commits and pushes | write the model code |
| Implementer | an agent (usually Claude Code) | writes research, unit tasks, model code, tests, per an operator-reviewed unit spec | start a unit before its spec is reviewed |
| Reviewer | a *different* model (Codex, or another Claude model) | tries to disprove the implementer's claims: checks every manual citation (page, register, bit, reset value) and every guest `file:line` against the source; keeps verified and inferred apart | edit source; review its own work |

- The operator sees only what review cannot settle: source conflicts, inferences, assumptions and design choices. Do not ask the operator to proofread citations.
- The reviewer works from `docs/units/templates/review-prompt.md`. Its findings are leads too: the implementer re-checks each one before acting on it.
- One review checkpoint at a time. The project has no deadline; review matters more than speed.
- **Explanations land in the repo.** Whatever the implementer explains to the operator (a QEMU concept, how a device works, a build or test step) goes into `docs/learning/` before the task's commit, written along the way or batched per task. Text about uncommitted code is committed with that code.

**Session state** (the current handoff and task board) is kept outside the tracked tree, in the operator's local working area. At the start of a session, read the handoff the operator points you to; at the end, update it with the current state and the next step. Durable results are promoted into `docs/`; working material stays out of tracked files.

**Public terms only.** Tracked files and commit messages describe this project in its own public terms: repo-relative paths, and public upstream sources cited as repository + commit + `file:line`.

## Upstream provenance: read this before writing QEMU code

QEMU's policy (`qemu/docs/devel/code-provenance.rst`, section "Use of AI-generated content") is to **decline contributions that include or derive from AI-generated content**. It **allows** AI for research, API/algorithm investigation, static analysis and debugging, provided that output is not included in the contribution.

Consequences for this project:
- Device-model code an agent writes on `rzv2l-dev` is **not upstreamable as-is**. Agent-written code serves as the working prototype and test oracle. Human authorship would be necessary for any submission but is **not sufficient**: the policy also declines contributions *derived from* AI-generated content. Whether and how anything goes upstream is an open operator decision, not a rewrite step.
- Agents can contribute freely to the parts upstream never sees: evidence packets, research notes, device maps, test plans, guest build scripts, oracle captures, validation reviews and debugging.
- Every agent-touched commit in **both** repos carries an `Assisted-by:` trailer (see Commit style). That way it is always mechanically clear which commits are AI-assisted. Never omit or strip it.

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
- CPG monitors: `CLK_MON` = `CLK_ON` (same polarity); `RSTMON` = `~RST & implemented_mask` (inverted, 1 = in reset). Linux and TF-A poll both; getting either wrong makes drivers time out (U-Boot SDHI, Linux `sh-sci`).
- The production OP-TEE panics without TSIP, a closed crypto IP. Emulation uses an OP-TEE rebuilt with `CFG_RZ_SCE=n`; TSIP is honest-fault.

## Repo layout

Each directory is described by its purpose, not its contents. `scripts/lint.py` checks this block against the tree: add or remove a line here when a directory is created or removed.

```
docs/spec/          specification, requirements, traceability
docs/units/         work units per milestone, and their templates
docs/milestones/    milestone reports
docs/research/      per-block research notes
docs/decisions/     decision records
docs/experiments/   experiment records (EXP-NNN-*.md)
docs/learning/      how QEMU models a machine, from real monitor output
docs/evidence/      EVK captures; each records board, image/build ID and boot stage
docs/device-map.md  MMIO/IRQ/clock/reset map, with evidence per row
docs/sources.md     source register: manuals, pinned guest and firmware sources
tests/experiments/  sources and run scripts backing docs/experiments/
tests/acceptance/   per-milestone acceptance runs and their expected outputs
tests/probes/       bare-metal guest programs that check a machine from inside
scripts/            repo tooling (lint, build and run helpers)
artifacts/rzv2l/    manuals index, manifest and checksums (the manuals are not tracked)
qemu/               submodule: the QEMU fork
```

## Sources

- Hardware truth: `artifacts/rzv2l/hardware/r01uh0936ej0150-rzv2l.pdf` (HW manual Rev 1.50). The GIC-600 registers are in the Arm GIC-600 r1p6 TRM (100336_0106_00), to which the manual defers (§8.4 p.548). For grep, use the searchable text in `artifacts/rzv2l/text/`. Cite the **PDF** (section/table/page), not the text file.
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

Rebuilding, qtests, checkpatch, tracing and editor setup: `docs/learning/building-and-testing.md`.

Useful QEMU debugging (see `docs/imx95/methodology.md` in qemu-imx95):
- `-d unimp,guest_errors,invalid_mem`: an acceptance run must have every unimplemented access fixed or listed. `invalid_mem` is the only mask that logs accesses to unmapped addresses and refused access sizes (`docs/learning/building-and-testing.md` §5).
- `-d nochain` plus gdb `hbreak` when TCG breakpoints misbehave.
- `-icount` only to debug races; never in boot tests.

## Hardware oracle (the physical EVK)

- **Read-only by default.** Writes to CPG, PMIC, WDT, eMMC boot partitions or QSPI need explicit operator approval.
- Use a project-owned debug image (G1) or U-Boot `md`. Hardened images typically block `/dev/mem`.
- Record whether a register read has side effects (FIFO pop, write-1-to-clear, read-to-clear).
- A measurement answers a specific question stated beforehand. Store it under `docs/evidence/`.
- **Provenance.** Every evidence file names the image or build it came from. When the image was not built by this project, the raw originals are kept privately by the operator and the evidence file records their SHA-256, so an excerpt can always be checked against its source. Over time, prefer re-measuring on G0/G1 images this project builds; such evidence replaces downstream-image evidence.

## Commit style

- **Project repo:** Conventional Commits, `<type>(<scope>): <subject>`, imperative mood, ≤72 chars. Scopes: `spec`, `docs`, `research`, `evidence`, `tests`, `scripts`, `artifacts`, `qemu` (submodule bumps).
- **QEMU fork (`rzv2l-dev`):** upstream QEMU style, `<subsystem>: <subject>` (e.g. `hw/arm: add RZ/V2L SoC skeleton`), `scripts/checkpatch.pl --no-signoff` clean, one logical change per commit. No `Signed-off-by:` on agent-written commits: it certifies the DCO, which QEMU holds cannot be given for AI-generated code (`qemu/docs/devel/code-provenance.rst`). The operator signs off only code they wrote, if a submission is ever considered.
- **Commit body:** say what was verified and how, and what was not verified. A test that has never been seen to fail does not count as verification (rule 7).
- **AI attribution, both repos:** end every agent-touched commit with `Assisted-by: <tool>:<exact-model-id-you-are-running-as>`. Use one line per model that touched the change, in order. Never copy a model id from a doc or a past commit. **Do not add `Co-Authored-By:` lines for AI tools.**
- Run `scripts/lint.py` before every commit; it must report 0 errors. Warnings are reviewed, not ignored.
- **Do not run `git commit`, `git push`, or submodule bumps without operator confirmation.**

## Branches and PRs

- **Project repo (`main`):** small docs and process changes are committed straight to `main` after operator confirmation. Each work unit gets a branch `unit/<unit-id>` (e.g. `unit/M1-machine-skeleton`) and merges to `main` through a PR, after the independent reviewer pass.
- **QEMU fork:** `rzv2l-dev` is the integration branch; never commit to `rzv2l-base`. Each unit gets a topic branch `unit/<unit-id>`, merged into `rzv2l-dev` through a PR on the fork, with `scripts/checkpatch.pl` clean. PRs target the fork only, never upstream `qemu/qemu`: an upstream submission is a separate operator decision and needs human-authored code.
- **Linking the two:** a unit's project-repo PR carries the submodule bump to the merged `rzv2l-dev` commit, so `main` only ever points at reviewed fork code.
- **PR body:** sections **What**, **Verification**, **Not verified**, **Scope**, and the same `Assisted-by:` lines as the commits. No tool-generated footers.
- Opening, merging and pushing PRs needs operator confirmation, as for commits.
