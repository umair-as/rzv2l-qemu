# CLAUDE.md

This file guides Claude Code (claude.ai/code) in this repository.

Project orientation, rules, layout, workflow and conventions live in the agent-agnostic file:

@AGENTS.md

The rest of this file covers Claude Code mechanics only.

## Attribution

- AGENTS.md "Commit style" overrides Claude Code's default commit and PR attribution: no `Co-Authored-By:` lines, no "Generated with Claude Code" footer, no `Assisted-by:` trailer.

## Skills, agents, hooks

- Skills come from `.claude/skills`, a symlink to `.agents/skills/` (shared with Codex). Add a skill there, never as a separate copy under `.claude/`.
- Subagents in `.claude/agents/` pin their own `model`. For the independent reviewer, use a non-forked subagent whose `model` differs from this session's.
- `.claude/hooks/git_gate.py` runs as a PreToolUse hook on Bash (`.claude/settings.json`). It denies builds inside `qemu/`; commits, pushes and PRs pass. A deny is a policy decision: do not rephrase the command around it.
