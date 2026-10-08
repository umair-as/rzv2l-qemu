# CLAUDE.md

This file guides Claude Code (claude.ai/code) in this repository.

Project orientation, rules, layout and conventions live in the agent-agnostic file:

@AGENTS.md

The rest of this file is Claude-Code-specific.

## Attribution mechanics

- The operator's convention (AGENTS.md "Commit style") **overrides** Claude Code's default commit and PR footers. Use `Assisted-by: claude-code:<model-id>` with the model this session is actually running as. Never add `Co-Authored-By:` or the "Generated with Claude Code" footer.
- On `rzv2l-dev` (the QEMU fork) the trailer matters doubly: it marks commits that must be human-rewritten before any upstream submission (QEMU code-provenance policy).

## Serial console MCP (physical EVK)

- The `mcp-serial-rs` tools reach the EVK console. The RZ/V2L is normally `/dev/ttyUSB0` @ 115200 8N1. Confirm with `serial_list_ports` and don't assume.
- The read-only oracle policy in AGENTS.md applies. Ask before any command that writes registers, flash or boot media, or that reboots the board.
- Capture logs into `docs/evidence/` with board, image and boot stage noted.

## Subagents

- Use subagents for broad source reading: TF-A, U-Boot, kernel drivers, the hardware manual text. Have them write findings to a local working file and return a summary.
- **Verify their surprising claims yourself** against the effective build configuration before relaying or recording them. Subagent reports are leads, not evidence.
