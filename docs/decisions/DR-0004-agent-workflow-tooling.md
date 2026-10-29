# DR-0004: Agent workflow tooling (skills, agents, hooks)

- **Status:** Accepted (operator, 2026-10-27)
- **Date:** 2026-10-27

## Context

M0 and M1 ran on the workflow in [AGENTS.md](../../AGENTS.md) "How work flows" and the unit lifecycle in [docs/units/README.md](../units/README.md). The process works, but each session re-typed the same procedures as prompts: the review prompt, finding dispositions, the evidence packet, the mutation check, research briefs, EVK read rules. A few rules lived only as text the agent had to remember, for example no commits on `rzv2l-base` and no builds inside `qemu/`.

The operator works with two agents, Claude Code and Codex. Both follow the same workflow.

## Decision

The workflow procedures become committed skills, agents and hooks, shared by both agents.

- **Layout.**
  - Skills live in `.agents/skills/<name>/SKILL.md`, which Codex reads. `.claude/skills` is a symlink to them, which Claude Code reads.
  - Agents are in `.claude/agents/`, hooks in `.claude/hooks/`, and the hook wiring in `.claude/settings.json`.
  - `.claude/settings.local.json` stays uncommitted. Committed files refer to the operator's working area only as `$RZV2L_WORKAREA`.
- **Skills** hold procedure; the rules stay in AGENTS.md and the templates.
  - `/onboard new|plan|close` covers the unit lifecycle.
  - `/emulate` does one task.
  - `/debug` applies the failure policy.
  - `/review` runs the independent review and the dispositions.
  - `/qemu-cov` builds the device coverage map in `docs/coverage.md`: device map × fidelity class × the windows G0/G1 guests touch, as measured by `-d unimp`.
  - `/evk-read` does EVK console reads, always in the main session.
  - `learning-docs` already exists.
  - Each skill stops at the existing operator checkpoints. None commits or pushes.
- **Agents:** `manual-researcher`, `guest-researcher` and `reviewer`, all on Sonnet. The reviewer runs on a model different from the implementer's. Researcher reports are leads, and the implementer verifies them before recording anything.
- **Hooks.** One gate script.
  - As a Claude Code hook (Claude Code only), it denies builds inside `qemu/` and asks before a push, a PR or a submodule bump. Codex follows these two rules from AGENTS.md.
  - As plain git hooks, it denies commits on `rzv2l-base` and fork commits with `Signed-off-by:`, and runs `scripts/lint.py` before each project commit. Wired locally in each clone, these cover every committer.
- **Provenance** is stated once, in the [README](../../README.md). Commits carry no AI attribution lines.
- **AGENTS.md** has a Workflow section that both agents follow. **CLAUDE.md** keeps only Claude Code mechanics.
- **Verification.** Each hook check is mutation-checked, and each skill is replayed on past M1 work before it is relied on.
- **Rollout** in six phases: foundation, review, coverage, onboarding, emulation and debug, EVK. Each is committed to `main` after operator review.

## Amendment (2026-10-28)

The skills are split in two layers. The procedure in each lives in one place.

- **Technical skills** do one piece of modelling or testing work and can be used at any time: `register-evidence`, `device-model`, `soc-wiring`, `qtest-golden`, `guest-probe`, `mutation-check`, `guest-bringup`, `learning-docs`. They draw on this repo's M1 work and on the method of the qemu-imx95 and qemu-imxrt1180 ports (method only, no RZ/V2L facts).
- **Process skills are not built** (operator, 2026-10-28): the agent harness's own review, plan and commit flow is good enough, and effort goes to the model. The rules for review and commits stay in AGENTS.md.
- `/debug` is replaced by `guest-bringup`. `/qemu-cov` becomes one coverage parser shared by `guest-bringup`, the acceptance log gate and the bench.
- Verification is unchanged: each skill is replayed on past work before it is relied on. The technical skills were not replayed yet.
- The Claude Code hook keeps only the build deny inside `qemu/`. Commits, pushes, PRs and submodule bumps are the agent's normal cycle; the push/PR/bump asks are removed. The git hooks (fork sign-off, `rzv2l-base`, lint) stay.

## Consequences

- One copy of each procedure serves both agents, versioned and reviewed.
- The branch and sign-off rules are enforced by code for every committer, and the build rule (no builds inside `qemu/`) for Claude Code. Pushes are not gated (2026-10-28).
- The tree shows the agent tooling; private paths and the working area stay out of it.
- Skills point to the rules in AGENTS.md instead of restating them, so the two do not drift.
