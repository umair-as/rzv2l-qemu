#!/usr/bin/env python3
"""Workflow gate for qemu-rzv2l (DR-0004).

Entry points:
  claude                       Claude Code PreToolUse hook (Bash). Reads the hook
                               JSON on stdin. Denies builds inside qemu/.
                               Commits, pushes and PRs are the agent's normal
                               cycle and pass. Undecidable input -> ask.
  commit-msg --repo fork FILE  git hook for the fork. Denies Signed-off-by: and
                               commits on rzv2l-base.
  pre-commit --repo project    git hook for the project. Runs scripts/lint.py
                               (layout, links, reqs, skills).

Wire the git hooks locally; they are not tracked:
  .git/hooks/pre-commit        exec python3 "$(git rev-parse --show-toplevel)/.claude/hooks/git_gate.py" pre-commit --repo project
  qemu/.git/hooks/commit-msg   exec python3 "$(git rev-parse --show-toplevel)/../.claude/hooks/git_gate.py" commit-msg --repo fork "$1"

Tests: python3 .claude/hooks/test_git_gate.py -v
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

BUILD_TOOLS = {"configure", "ninja", "make", "meson"}
SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}
SHELLS = {"bash", "sh", "zsh", "dash"}
WRAPPERS = {"time", "env", "nohup", "sudo"}
SCISSORS = "# ------------------------ >8 ------------------------"


def project_root():
    return Path(__file__).resolve().parents[2]


def inside(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# --- Claude Code hook -------------------------------------------------------

HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_]\w*)\2")


def strip_heredocs(command):
    """Drop heredoc bodies: they are data (a commit message, a file), not
    commands, and their quotes would break shlex. An unquoted body that
    substitutes commands is kept as an error, so the hook asks."""
    lines = command.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for dash, quote, word in HEREDOC.findall(line):
            body = []
            while i < len(lines):
                end = lines[i].lstrip("\t") if dash else lines[i]
                i += 1
                if end == word:
                    break
                body.append(lines[i - 1])
            text = "\n".join(body)
            if not quote and ("$(" in text or "`" in text):
                raise ValueError("command substitution in a heredoc body")
    return "\n".join(out)


def segments(command):
    lex = shlex.shlex(strip_heredocs(command), posix=True, punctuation_chars=";&|\n")
    lex.whitespace = " \t\r"  # a newline separates commands, like ";"
    lex.whitespace_split = True
    seg = []
    for tok in lex:
        if tok in SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def strip_prefix(tokens):
    while tokens and (tokens[0] in WRAPPERS or re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0])):
        tokens = tokens[1:]
    return tokens


def dash_c(tokens, cwd):
    """Directory given by -C <dir> or -C<dir>, else cwd."""
    for i, tok in enumerate(tokens):
        if tok == "-C" and i + 1 < len(tokens):
            return cwd / tokens[i + 1]
        if tok.startswith("-C") and len(tok) > 2:
            return cwd / tok[2:]
    return cwd


def shell_script(tokens):
    """The script of `bash -c "<script>"` (also -lc, -ec ...), else None."""
    for i, tok in enumerate(tokens[1:], 1):
        if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", tok) and i + 1 < len(tokens):
            return tokens[i + 1]
    return None


def classify_command(command, cwd, root):
    """Return ("deny"|"ask", reason) or None."""
    cwd = Path(cwd)
    decisions = []
    for tokens in segments(command):
        tokens = strip_prefix(tokens)
        if not tokens:
            continue
        prog = os.path.basename(tokens[0])
        if prog == "cd":
            cwd = cwd / tokens[1] if len(tokens) > 1 else Path.home()
            continue
        if prog in BUILD_TOOLS and inside(dash_c(tokens, cwd), root / "qemu"):
            decisions.append(("deny", f"{prog} inside qemu/: build out of tree, "
                                      "under build/ (AGENTS.md 'Build and run')"))
        elif prog in SHELLS or prog == "eval":
            script = " ".join(tokens[1:]) if prog == "eval" else shell_script(tokens)
            d = classify_command(script, cwd, root) if script else None
            if d:
                decisions.append(d)
    for kind in ("deny", "ask"):
        for d in decisions:
            if d[0] == kind:
                return d
    return None


def hook_output(decision, reason):
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": f"git_gate: {reason}"}})


def main_claude(stdin_text):
    try:
        data = json.loads(stdin_text)
        command = (data.get("tool_input") or {}).get("command")
        if not command:
            return ""
        d = classify_command(command, Path(data.get("cwd") or os.getcwd()), project_root())
        return hook_output(*d) if d else ""
    except Exception as e:  # undecidable: ask, never allow silently
        return hook_output("ask", f"internal error ({e}); check the command by hand")


# --- git hooks --------------------------------------------------------------

def check_message(text, repo, branch):
    """Return a list of errors for a commit message; empty means OK."""
    lines = text.split(SCISSORS, 1)[0].splitlines()
    errors = []
    if repo == "fork":
        if branch == "rzv2l-base":
            errors.append("rzv2l-base is the pinned upstream base; never commit there")
        if any(l.startswith("Signed-off-by:") for l in lines):
            errors.append("no Signed-off-by: on fork commits; it certifies the DCO "
                          "(qemu/docs/devel/code-provenance.rst)")
    return errors


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    mode = argv[0]
    if mode == "claude":
        out = main_claude(sys.stdin.read())
        if out:
            print(out)
        return 0
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else "project"
    if mode == "commit-msg":
        text = Path(argv[-1]).read_text()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        errors = check_message(text, repo, branch)
        for e in errors:
            print(f"git_gate: {e}", file=sys.stderr)
        return 1 if errors else 0
    if mode == "pre-commit":
        lint = project_root() / "scripts" / "lint.py"
        return subprocess.run([sys.executable, str(lint), "layout", "links", "reqs", "skills"]).returncode
    print(f"git_gate: unknown mode {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
