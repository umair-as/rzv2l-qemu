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
| Operator | the human owner | designs and reviews specs, unit specs, decisions; approves EVK actions | write the model code |
| Implementer | an agent (usually Claude Code) | writes research, unit tasks, model code, tests, per an operator-reviewed unit spec | start a unit before its spec is reviewed |
| Reviewer | a *different* model (Codex, or another Claude model) | tries to disprove the implementer's claims: checks every manual citation (page, register, bit, reset value) and every guest `file:line` against the source; keeps verified and inferred apart | edit source; review its own work |

- The operator sees only what review cannot settle: source conflicts, inferences, assumptions and design choices. Do not ask the operator to proofread citations.
- The reviewer works from `docs/units/templates/review-prompt.md`. Its findings are leads too: the implementer re-checks each one before acting on it.
- The independent reviewer starts from a fresh context with only the filled-in review prompt, on a model different from the implementer's: Codex, or another Claude model. A forked agent, or one on the implementer's model, does not count.
- Delegate broad source reading (TF-A, U-Boot, kernel drivers, the hardware manual) to research agents. They write findings to a working file and return a summary. Their reports are leads, not evidence: verify surprising claims against the effective build configuration before relaying or recording them.
- **Record each proof once** (operator, 2026-10-29). The qtest is the record. Its mutation goes in one place: one line in the unit's `tasks.md` (the exact code change → the red line). No patch files, no eval entries, no mutation tables in learning docs, no repeat in the PR body (the PR links `tasks.md`). `scripts/eval.py` and `tests/eval/m2/` stay as M2's regression suite: run once before a PR opens, not after every fix; not extended for later units. A unit that does not touch the serial-port (SCIFA) code runs it with `--no-mutations` (operator, 2026-10-29).
- **Unit paperwork is one page.** `spec.md`: scope, what the guest needs, exit criterion, the evidence it rests on. No `design.md`. `tasks.md`: a short table. One learning doc per unit, one page, written at the unit's end. Traceability and requirement statuses are updated once at v1.0, not per unit.
- **Windows found by the boot loop.** A window the guest touches is mapped with the class `docs/device-map.md` records for it, with no stop. If the boot shows a window needs a different class (an UNIMP whose read-as-zero is not honest, an unmapped window the guest touches), the implementer lists it for the operator at the unit's end and does not change the class itself.
- **Quiet commands** (implementer and reviewer). Build, test and boot commands send their output to a file; read only the tail or the failing lines (`ninja … >log 2>&1; tail -5 log`). Never read a full build or boot log into context. `set -o pipefail` when a check is piped.
- **Review budget: one round, plus at most one recheck limited to the fixes.** Doc-only findings (counts, wording) are fixed without another round. The review report stays in the operator's working area; only a short **Review fixes** list goes into the PR body.
- **The implementer prepares the review build** at PR time: a git worktree of the fork at the PR head and a separate build directory `build/review-<short-sha>/`, configured and built once; path and commit go in the review prompt. The reviewer's first commands are `ninja` there (it must report nothing to do) and `git status` in the worktree (clean, at the PR SHA). The reviewer does not clone, configure or build from scratch, does not run `scripts/eval.py` and does not rebuild the G0 kernel. It reads the code against the manual and the evidence, runs the existing qtest binary, and makes about three mutations of its own with incremental `ninja` in the review build, plus follow-ups to any that stays green, reversing each after. The implementer's boot log and command are the boot evidence; the reviewer re-runs a boot only if it doubts that log, and says why. When Codex quota is short, a non-forked Sonnet subagent given only the review prompt is an accepted reviewer. Review prompts are short: commits, review build path, claims to disprove, this budget.

**Session state** (the current handoff and task board) is kept outside the tracked tree, in the operator's local working area. At the start of a session, read the handoff the operator points you to; at the end, update it with the current state and the next step. Durable results are promoted into `docs/`; working material stays out of tracked files. Keep both files short: the handoff about one page, rewritten each session (never appended); the task board current state only. Never delete working-area material (research, reviews, source trees) without operator approval.

**Public terms only.** Tracked files and commit messages describe this project in its own public terms: repo-relative paths, and public upstream sources cited as repository + commit + `file:line`. Committed tooling names the operator's working area only as `$RZV2L_WORKAREA`.

## Workflow (skills, agents, gates)

The procedures above are packaged as skills, so every agent runs them the same way ([DR-0004](docs/decisions/DR-0004-agent-workflow-tooling.md)). Skills hold steps; the rules stay in this file and in the templates.

| Stage | Skill | What it does |
|---|---|---|
| Before modelling a block | `register-evidence` | the consumer-scoped register table: offsets, reset values, field classes, start states, cites |
| Writing the model | `device-model` | register file, field classes, IRQ equations, virtual-time completion, honest faults (patterns in its `reference.md`) |
| Into the machine | `soc-wiring` | SoC child, memory map, GIC SPI wiring, chardev, Kconfig; acceptance expectations from the device map |
| Register tests | `qtest-golden` | qtests that assert manual values, by field class |
| CPU-side tests | `guest-probe` | bare-metal probes for aborts, PSCI, IRQ delivery, firmware access order, console output |
| Proving a test | `mutation-check` | plausible wrong value, confirmed rebuild, the right red line, restore |
| Running guests | `guest-bringup` | the rule 5 loop in practice: triage by symptom, hangs, allowed fixes, coverage list |
| Explanations for the operator | `learning-docs` | writes or rewrites `docs/learning/` per `docs/learning/STYLE.md` |
| Seeing the model run | `bench-drive` | runs the web bench and drives a session through Playwright MCP or its HTTP API |

Each skill does one piece of modelling or testing work. Process (review, planning, commits, handoff) follows this file and the agent harness's own flow; no process skills are planned (DR-0004).

- **Skills** live in `.agents/skills/<name>/SKILL.md`. Codex reads them there; Claude Code reads them through the `.claude/skills` symlink. A skill stops at the operator checkpoints above and never commits or pushes.
- **Agent briefs** would go in `.claude/agents/*.md` as Claude Code subagents (none planned). Codex reads them as task briefs.
- **Gates.** What is enforced depends on who runs the command:
  - **Every committer** (git hooks, wired locally in each clone; see the docstring of `.claude/hooks/git_gate.py`): commits on `rzv2l-base` and fork commits with `Signed-off-by:` are refused; `scripts/lint.py` runs before each project commit.
  - **Claude Code only** (tool hook): builds inside `qemu/` are refused.
  - **Codex** follows the build and push rules from this file; nothing enforces them for it.

## Upstream provenance: read this before writing QEMU code

QEMU's policy (`qemu/docs/devel/code-provenance.rst`, section "Use of AI-generated content") is to **decline contributions that include or derive from AI-generated content**. It **allows** AI for research, API/algorithm investigation, static analysis and debugging, provided that output is not included in the contribution.

Consequences for this project:
- Device-model code an agent writes on `rzv2l-dev` is **not upstreamable as-is**. Agent-written code serves as the working prototype and test oracle. Human authorship would be necessary for any submission but is **not sufficient**: the policy also declines contributions *derived from* AI-generated content. Upstream submission is not a goal (operator, 2026-10-28): the project shows what agent-driven QEMU modelling can do.
- Agents can contribute freely to the parts upstream never sees: evidence packets, research notes, device maps, test plans, guest build scripts, oracle captures, validation reviews and debugging.
- Provenance is stated once, project-wide, in the README. Everything on `rzv2l-dev` beyond `rzv2l-base` counts as agent-assisted. A commit the operator writes by hand says so in its message.

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
- CPG monitors: `CLK_MON` = `CLK_ON` (same polarity) for implemented bits; reserved bits can differ (WDT b7:6 read 1 in `CLK_ON`, 0 in `CLK_MON`; EVK-X01). `RSTMON` = `~RST & implemented_mask` (inverted, 1 = in reset). Linux and TF-A poll both; getting either wrong makes drivers time out (U-Boot SDHI, Linux `sh-sci`).
- The production OP-TEE panics without TSIP, a closed crypto IP. Emulation uses an OP-TEE rebuilt with `CFG_RZ_SCE=n`; TSIP is honest-fault.

## Repo layout

Each directory is described by its purpose, not its contents. `scripts/lint.py` checks this block against the tree: add or remove a line here when a directory is created or removed.

```
docs/README.md      index of docs/ and reading order
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
tests/eval/         M2's eval checks and mutation patches (regression suite; later units record proofs in tasks.md)
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
- **Serial console** (the `mcp-serial-rs` tools). The RZ/V2L is normally `/dev/ttyUSB0` @ 115200 8N1; confirm it with `serial_list_ports` instead of assuming. Ask before any command that writes registers, flash or boot media, or reboots the board.
  - Make the policy server-enforced, not a promise. `write_policy: "deny"` refuses every write, so it suits only passive listening (capturing a boot log). For U-Boot `md` reads, open with `write_policy: "confirm"` plus `deny_patterns` that block state-changing commands (`mw`, `mm`, `nm`, `cp`, `mmc write`, `sf`, `env save`/`saveenv`, `reset`, `boot*`, `go`).
  - `md` itself can have side effects: follow the per-register notes in `docs/evidence/requests.md` (never read the SCIF FIFO data registers).
  - The server's journal records metadata only. Copy the console output you need into the evidence file, with board, image and boot stage noted.
- **Provenance.** Every evidence file names the image or build it came from. When the image was not built by this project, the operator keeps the raw originals and their SHA-256 privately, so an excerpt can always be checked against its source. Over time, prefer re-measuring on G0/G1 images this project builds; such evidence replaces downstream-image evidence.

## Commit style

- **Project repo:** Conventional Commits, `<type>(<scope>): <subject>`, imperative mood, ≤72 chars. Scopes: `spec`, `docs`, `learning`, `research`, `evidence`, `tests`, `probe`, `acceptance`, `scripts`, `artifacts`, `qemu` (submodule bumps), `tooling` (skills, agents, hooks). Test changes use the type `test` (e.g. `test(acceptance): …`), not `tests`.
- **QEMU fork (`rzv2l-dev`):** upstream QEMU style, `<subsystem>: <subject>` (e.g. `hw/arm: add RZ/V2L SoC skeleton`), `scripts/checkpatch.pl --no-signoff` clean, one logical change per commit. No `Signed-off-by:` on agent-written commits: it certifies the DCO, which QEMU holds cannot be given for AI-generated code (`qemu/docs/devel/code-provenance.rst`). The fork's `commit-msg` hook refuses every sign-off; a human-authored submission, if ever prepared, is a separate operator decision.
- **Commit body: short.** About 5–6 lines in all: the subject, two lines of what and why, and one `Verified:` line (how it was verified; add what was not, if it matters). Do not restate the diff. Test counts and full detail go in the PR body. A test that has never been seen to fail does not count as verification (rule 7).
- **Subject names the change,** so it still reads well months later in `git log --oneline`. Review dates and finding IDs go in the body, if anywhere.
- **Write for a reader who knows the hardware but not this project's IDs** (operator, 2026-10-29). Commit and PR subjects name the hardware and the effect, never a milestone or unit ID. A milestone or unit ID appears at most once in a body, as a link. An EVK row ID always comes with its meaning: "the EVK reads CLK_MON_WDT as `0x3F` (X01)". Project terms (G0, `direct-boot`, UNIMP class, device-map row) get a one-line gloss the first time they appear in a PR; the glossary is `docs/learning/glossary.md`.
- **What goes in one commit** is decided per case. Batch small edits into one commit at a natural review point instead of proposing a commit per edit. Group a task that cannot be tested yet with the task that makes it testable.
- **No AI attribution lines, both repos:** no `Assisted-by:`, no `Co-Authored-By:`, no tool-generated footers. Provenance is in the README (see Upstream provenance).
- Run `scripts/lint.py` before every commit; it must report 0 errors. Warnings are reviewed, not ignored.
- **Commits, pushes, PRs and submodule bumps are the agent's normal cycle** (operator, 2026-10-28): no confirmation needed. Destructive remote actions (force-push, deleting branches or tags) are still confirmed first.

## Branches and PRs

- **Project repo (`main`):** small docs and process changes are committed straight to `main`. Each work unit gets a branch `unit/<unit-id>` (e.g. `unit/M1-machine-skeleton`) and merges to `main` through a PR, after the independent reviewer pass.
- **QEMU fork:** `rzv2l-dev` is the integration branch; never commit to `rzv2l-base`. Each unit gets a topic branch `unit/<unit-id>`, merged into `rzv2l-dev` through a PR on the fork, with `scripts/checkpatch.pl` clean. PRs target the fork only, never upstream `qemu/qemu`.
- **Linking the two:** a unit's project-repo PR carries the submodule bump to the merged `rzv2l-dev` commit, so `main` only ever points at reviewed fork code.
- **PR body: short and to the point** (operator, 2026-10-29). Sections **What** and **Verification**; **Not verified** only when a real gap remains, in a line or two; after review, a short **Review fixes** list (what changed, not who found it). No Scope section (the diff shows it), no reviewer or model names, no provenance line (the README states it once), no tool-generated footers. No PR comments; review dialogue stays in the working area.
