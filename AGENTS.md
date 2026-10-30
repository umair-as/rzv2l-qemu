# AGENTS.md

The orientation for AI coding agents in this repo. Claude-specific mechanics are in `CLAUDE.md`. The project's own words (G0, UNIMP, M3b-…) are explained in `docs/README.md`.

## What this repo is

`qemu-rzv2l` is a QEMU machine model of the **Renesas RZ/V2L SMARC EVK** (SoC R9A07G054L2: 2× Cortex-A55, GIC-600, 2 GB DDR4). It aims to run software built for the real board **without modifying that software**.

The specification is `docs/spec/project.md`, the requirement IDs are in `docs/spec/requirements.md`, and `docs/spec/traceability.md` links them to tests. Read the spec before any hardware-facing work.

Guest software comes in three tiers:

| Tier | Guest | Role |
|---|---|---|
| G0 | plain upstream Linux + upstream `r9a07g054l2-smarc.dtb` + BusyBox initramfs | primary acceptance |
| G1 | Renesas vendor stack (`linux-renesas`, Renesas TF-A / U-Boot, OP-TEE) | acceptance |
| G2 | products built on G1 | studied as samples only; never acceptance, never a build dependency |

## Two repositories

```
qemu-rzv2l/        this repo: spec, research, evidence, tests, guest builds, scripts
└── qemu/          submodule → github.com/umair-as/qemu (fork of qemu/qemu)
      rzv2l-base   pinned upstream base (v11.1.2); never commit here
      rzv2l-dev    the port; `git diff rzv2l-base...rzv2l-dev` is the whole port
```

- The fork holds only what upstream QEMU could take: `hw/`, `include/hw/`, `tests/qtest/`, `docs/system/arm/`, Kconfig/meson wiring. No agent files, specs or evidence.
- Project tags are `rzv2l-vX.Y`, never bare `vX.Y` (QEMU's own tags).
- Moving the base is a recorded decision (`docs/decisions/`).

## How work flows

| Role | Who | Does |
|---|---|---|
| Operator | the human owner | reviews units and decisions when they choose, approves EVK actions, says when to merge |
| Implementer | an agent | writes research, unit pages, model code and tests |
| Reviewer | a *different* model (Codex, or another Claude model in a fresh, non-forked context) | tries to disprove the implementer's claims; never edits source or reviews its own work |

- **What the operator sees:** only what review cannot settle: source conflicts, inferences, assumptions, design choices. Never ask the operator to proofread citations.
- **Unit paperwork is one page.** A unit is `docs/units/<unit>/spec.md` (scope, what the guest needs, exit criterion, evidence) and `tasks.md` (a short table). Implementation follows the spec page without waiting for a review. One learning page per unit, and an update of `docs/milestones.md`, at its end. Traceability and requirement statuses are updated once per release, not per unit.
- **Record each proof once.** The test is the record. Its mutation is one line in the unit's `tasks.md`: the exact change → the red line. Not repeated in PR bodies or learning docs. `scripts/eval.py m2` is M2's regression suite: run it once before a PR, with `--no-mutations` unless the serial-port (SCIFA) code changed.
- **Windows the boot touches** are mapped with the class `docs/device-map.md` gives them, without stopping. A window that needs a different class is listed for the operator at the unit's end.
- **Review:** one round plus at most one recheck limited to the fixes; doc-only findings are fixed without a round. The implementer re-checks every finding at the source before acting. The report stays in the operator's working area; the PR body gets a short **Review fixes** list. The reviewer works from `docs/units/templates/review-prompt.md`, which has the review build and mutation rules. When a PR changes no QEMU code, there is no review build.
- **Research agents** may do broad source reading. Their reports are leads: verify surprising claims before recording them.
- **Quiet commands.** Build, test and boot output goes to a file; read the tail or the failing lines. `set -o pipefail` when a check is piped.
- **Session state** (handoff and task board) lives in the operator's working area, outside the tracked tree. Read the handoff at the start; rewrite it at the end (about one page). Never delete working-area material without approval.
- **No stale material.** What was superseded is deleted, not archived; git history is the archive. Stale text is fixed where it is.
- **No dates in docs.** Git records when text was written. A date stays only where it identifies a fact that can change outside the repo: an EVK measurement, a claim about the "latest" upstream release, the spec changelog, a decision record's acceptance date.
- **Public terms only.** Tracked files and commit messages use repo-relative paths and public upstream sources (repository + commit + `file:line`). Tooling names the working area only as `$RZV2L_WORKAREA`.

## Workflow (skills and gates)

The modelling and testing procedures are skills in `.agents/skills/<name>/SKILL.md` (Claude Code reads them through the `.claude/skills` symlink; DR-0004). Each does one piece of work: `register-evidence`, `device-model`, `soc-wiring`, `qtest-golden`, `guest-probe`, `mutation-check`, `guest-bringup`, `learning-docs`, `bench-drive`. A skill never commits or pushes.

Gates:
- **Every committer** (git hooks, wired per clone; see `.claude/hooks/git_gate.py`): no commits on `rzv2l-base`; no `Signed-off-by:` in fork commits; `scripts/lint.py` before each project commit.
- **Claude Code** (tool hook): no builds inside `qemu/`.

## Upstream provenance

QEMU declines contributions that include or derive from AI-generated content (`qemu/docs/devel/code-provenance.rst`). Everything on `rzv2l-dev` beyond `rzv2l-base` is agent-assisted, so it is not upstreamable, and upstream submission is not a goal: the project shows what agent-driven QEMU modelling can do. Provenance is stated once, in the README. A commit the operator writes by hand says so.

## Engineering rules (from the spec, non-negotiable)

1. **Evidence before implementation.** Every hardware-facing change cites its MMIO range, IRQ, clocks, resets and reset values; the manual section; the guest source (`file:line`); its fidelity class; what it does not support; how it was verified. Without evidence it is an experiment (`docs/experiments/`).
2. **Label every claim:** fact / code-derived inference / hardware observation / assumption.
3. **Check the effective build configuration** (`.config`, `conf.mk`, compile log), not source defaults, before claiming what firmware or a kernel does.
4. **Never modify the guest to fit the model.** No DT edits, driver or firmware patches, invented kernel arguments. A needed boot argument or loader fixup is a recorded fidelity gap.
5. **Failure loop:** observe → first unmet guest expectation → guest code → hardware contract → smallest model change → retest. No arbitrary constants, invented status bits or disabled drivers, except as recorded experiments.
6. **Never silently wrong.** A model behaves as the hardware does or fails visibly. Classes: FULL / FUNCTIONAL / STUB / UNSUPPORTED, and honest-fault vs silent-wrong (never acceptable).
7. **Booting is not proof.** qtests assert **manual** values (reset values, ID registers), not the model's own output, and each test is seen red on a mutation.
8. **Name the layer you verified** before claiming a root cause.
9. **Two start states:** firmware mode (manual reset values) and direct-kernel mode (the measured post-firmware state). Keep both explicit in each model.

## Board facts already established

Evidence: `docs/research/boot-chain-firmware.md`, `docs/experiments/`, `docs/evidence/`.
- Linux is entered at **NS-EL1**; PSCI over SMC; CPUs `cpu@0` / `cpu@100` (`mp-affinity` `0x0`, `0x100`).
- `CNTFRQ` = 24 MHz, from SYC `CNTFID0`; the DT timer has no `clock-frequency`.
- BL2 panics unless `SYS_LSI_DEVID[27:0] == 0x8447447`; boot source from `SYS_LSI_MODE` @ `0x11020A00`.
- CPG: `CLK_MON` = `CLK_ON` for implemented bits (WDT bits 7:6 differ on silicon, EVK X01); `RSTMON` = `~RST & implemented_mask`. Linux and TF-A poll both.
- The production OP-TEE panics without TSIP (closed crypto). Emulation uses OP-TEE rebuilt with `CFG_RZ_SCE=n`; TSIP is honest-fault.

## Repo layout

Lint checks this block against the tree: add or remove a line when a directory is created or removed.

```
docs/README.md      index of docs/, reading order and the project's words
docs/milestones.md  progress: milestones, units, SoC blocks, what comes next
docs/spec/          specification, requirements, traceability
docs/units/         work units per milestone, and their templates
docs/research/      per-block research notes
docs/decisions/     decision records
docs/experiments/   experiment records (EXP-NNN-*.md)
docs/learning/      how QEMU models a machine, from real monitor output
docs/evidence/      EVK captures; each records board, image/build ID and boot stage
docs/device-map.md  MMIO/IRQ/clock/reset map, with evidence per row
docs/sources.md     source register: manuals, pinned guest and firmware sources
tests/experiments/  sources and run scripts backing docs/experiments/
tests/acceptance/   per-milestone acceptance runs and their expected outputs
tests/eval/         M2's eval checks and mutation patches (regression suite)
tests/probes/       bare-metal guest programs that check a machine from inside
tests/guests/       scripts that build or fetch guest artifacts (outputs untracked)
scripts/            repo tooling (lint, build and run helpers)
bench/              web front end for one QEMU session (stock QEMU interfaces only) and its self-test
artifacts/rzv2l/    manuals index, manifest and checksums (the manuals are not tracked)
qemu/               submodule: the QEMU fork
.agents/            skills shared by Claude Code and Codex
.claude/            Claude Code agents, hooks and settings (skills: symlink to .agents/skills)
```

## Sources

- Hardware truth: the HW manual Rev 1.50 (`artifacts/rzv2l/hardware/r01uh0936ej0150-rzv2l.pdf`); for the GIC-600, the Arm GIC-600 r1p6 TRM, to which the manual defers (§8.4 p.548). Grep the text in `artifacts/rzv2l/text/`; cite the **PDF** (section, table, page).
- Board: SMARC module UM (`r01uh0964ej0200`) and carrier UM (`r01uh0966ej0200`).
- Conflicts: the manual rules intended layout and reset values, silicon rules actual behaviour, guest code rules what is required. Record the conflict; never pick silently.
- The BSP driver manuals and other QEMU machine models are leads only.

## Build and run

```bash
git submodule update --init
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs
ninja qemu-system-aarch64
```

Build out of tree under `build/`, never inside `qemu/`. More: `docs/learning/building-and-testing.md`.

Debugging:
- `-d unimp,guest_errors,invalid_mem`: an acceptance run has every unimplemented access fixed or listed; `invalid_mem` is the only mask that logs unmapped addresses and refused access sizes.
- `-d nochain` plus gdb `hbreak` when TCG breakpoints misbehave.
- `-icount` only to debug races; never in boot tests.

## Hardware oracle (the physical EVK)

- **Read-only by default.** Writes to CPG, PMIC, WDT, eMMC boot partitions or QSPI need the operator's approval.
- Measure with a project-owned debug image (G1) or U-Boot `md`; hardened images block `/dev/mem`. The serial server's journal keeps metadata only: copy the output you need into the evidence file.
- A measurement answers a question stated beforehand and is stored under `docs/evidence/`, with board, image and boot stage. Record any read side effect (FIFO pop, write-1-to-clear).
- **Serial console** (`mcp-serial-rs`): the RZ/V2L is normally `/dev/ttyUSB0` @ 115200 8N1; confirm with `serial_list_ports`. For U-Boot `md` reads, open with `write_policy: "confirm"` and `deny_patterns` for state-changing commands (`mw`, `mm`, `nm`, `cp`, `mmc write`, `sf`, `env save`/`saveenv`, `reset`, `boot*`, `go`). Follow the per-register notes in `docs/evidence/requests.md` (never read the SCIF FIFO data registers). Ask before any command that writes registers, flash or boot media, or reboots.
- **Provenance:** every evidence file names its image or build. For images this project did not build, the operator keeps the raw originals and their SHA-256. Prefer re-measuring on G0/G1 images this project builds.

## Commit style

- **Project repo:** Conventional Commits, `<type>(<scope>): <subject>`, imperative, ≤72 characters. Scopes: `spec`, `docs`, `learning`, `research`, `evidence`, `tests`, `probe`, `acceptance`, `scripts`, `artifacts`, `qemu` (submodule bumps), `tooling`. Test changes use the type `test`.
- **QEMU fork:** upstream style, `<subsystem>: <subject>` (e.g. `hw/arm: add RZ/V2L SoC skeleton`), `scripts/checkpatch.pl --no-signoff` clean, one logical change per commit, never `Signed-off-by:` (the DCO cannot be given for AI-generated code).
- **Body:** about 5-6 lines: the subject, two lines of what and why, one `Verified:` line. A test never seen to fail is not verification.
- **Write for a reader who knows the hardware but not this project:** subjects name the hardware and the effect, never a unit ID. Every project word (G0, UNIMP, an EVK row ID like R71, gap N) gets its plain meaning the first time it appears, in commits, PRs and docs (`docs/README.md`).
- **Batch** small edits into one commit at a natural review point; a task that cannot be tested yet goes with the task that makes it testable.
- **No AI attribution** in either repo: no `Assisted-by:`, no `Co-Authored-By:`, no tool footers.
- `scripts/lint.py` before every commit: 0 errors; warnings are read.
- **Commits, pushes, PRs and submodule bumps** are the agent's normal cycle. Merges happen on the operator's word. Destructive remote actions (force-push, deleting branches or tags) are confirmed first.

## Branches and PRs

- **Project (`main`):** small docs and process changes go straight to `main`. A work unit gets `unit/<unit-id>` and merges through a PR after the review.
- **Fork:** `rzv2l-dev` is the integration branch; a unit gets `unit/<unit-id>`, merged by PR on the fork, never to upstream `qemu/qemu`. The project PR carries the submodule bump to the merged `rzv2l-dev` commit.
- **PR body:** **What** and **Verification**; **Not verified** only for a real gap; after review a short **Review fixes** list. No reviewer or model names, no provenance line, no tool footers, no PR comments.
