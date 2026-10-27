#!/usr/bin/env python3
"""Repository consistency checks for qemu-rzv2l.

Checks:
  layout   the AGENTS.md "Repo layout" block matches the tree
  links    relative links in Markdown files resolve
  reqs     requirements.md and traceability.md list the same REQ IDs,
           and every REQ ID cited in the docs exists
  commits  commit messages follow AGENTS.md "Commit style"
  skills   each .agents/skills/<name>/SKILL.md has name == <name> and a
           description; .claude/skills links to .agents/skills
  style    docs/learning/ prose follows docs/learning/STYLE.md (warnings only;
           not in the default set until every file is rewritten)

Usage: scripts/lint.py [--commits RANGE] [CHECK ...]
Exit status is 1 if any check reports an error. Warnings do not fail.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories whose immediate children the layout block must cover.
LAYOUT_PARENTS = ("docs", "tests")
LAYOUT_SKIP_TOP = {"docs", "tests"}  # covered through their children

SCOPES = {"spec", "docs", "learning", "research", "evidence", "tests", "probe", "acceptance", "scripts", "artifacts", "qemu", "tooling"}
TYPES = {"feat", "fix", "docs", "test", "chore", "refactor", "build", "ci", "revert"}

REQ_RE = re.compile(r"\bREQ-[A-Z]+-\d{3}\b")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_PATH_RE = re.compile(r"`((?:\.\./|\./|docs/|tests/|scripts/|artifacts/)[^`\s]*)`")
PLACEHOLDER_RE = re.compile(r"[<>*{}…]|NNN|\.\.\.")


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def error(self, check, msg):
        self.errors += 1
        print(f"ERROR   [{check}] {msg}")

    def warn(self, check, msg):
        self.warnings += 1
        print(f"warning [{check}] {msg}")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


def repo_files():
    """Tracked plus untracked-but-not-ignored files, repo-relative."""
    out = git("ls-files", "--cached", "--others", "--exclude-standard")
    files = [Path(p) for p in out.splitlines() if p]
    return [p for p in files if (ROOT / p).exists() or p == Path("qemu")]


def markdown_files():
    return [p for p in repo_files()
            if p.suffix == ".md" and p.parts[0] not in ("qemu",)]


# --- style ------------------------------------------------------------------

STYLE_MAX_WORDS = 25
# STYLE.md section 1.3-1.5: idioms, complex words, filler
STYLE_AVOID = ("carry on", "in order to", "utilize", "e.g.", "i.e.",
               "simply", "just", "basically", "obviously", "really")
SENT_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\[(\"])")


def prose_blocks(text):
    """(line, text) of each paragraph or list item, outside code, tables,
    headings and quotations."""
    blocks, cur, start, fence = [], [], 0, False
    for n, l in enumerate(text.splitlines(), 1):
        s = l.strip()
        if s.startswith("```"):
            fence = not fence
        new_item = re.match(r"([-*]|\d+\.) ", s)
        if (fence or not s or s.startswith(("```", "#", "|", '> "', "---"))
                or new_item):
            if cur:
                blocks.append((start, " ".join(cur)))
            cur = []
            if fence or not new_item:
                continue
        if not cur:
            start = n
        cur.append(s.lstrip("> "))
    if cur:
        blocks.append((start, " ".join(cur)))
    return blocks


def plain_words(sentence):
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sentence)   # link -> text
    s = re.sub(r"``.*?``|`[^`]*`", "X", s)                  # code = one word
    s = re.sub(r"\([^()]*\)", "", s)                       # citations
    return [w for w in re.split(r"\s+", s) if re.search(r"\w", w)]


def check_style(rep):
    for md in sorted((ROOT / "docs/learning").glob("*.md")):
        rel = md.relative_to(ROOT)
        for line, block in prose_blocks(md.read_text()):
            for sent in SENT_END_RE.split(block):
                n = len(plain_words(sent))
                if n > STYLE_MAX_WORDS:
                    rep.warn("style", f"{rel}:{line}: sentence of {n} words: "
                             f"{sent[:60]}...")
            low = re.sub(r"`[^`]*`|\"[^\"]*\"", "", block).lower()
            for w in STYLE_AVOID:
                if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                    rep.warn("style", f"{rel}:{line}: avoid '{w}'")


# --- layout -----------------------------------------------------------------

def check_layout(rep):
    text = (ROOT / "AGENTS.md").read_text()
    m = re.search(r"^## Repo layout\n.*?^```\n(.*?)^```", text, re.S | re.M)
    if not m:
        rep.error("layout", "AGENTS.md has no 'Repo layout' code block")
        return
    listed = set()
    for line in m.group(1).splitlines():
        if line.strip():
            listed.add(line.split()[0].rstrip("/"))

    for entry in sorted(listed):
        if not (ROOT / entry).exists():
            rep.error("layout", f"listed in AGENTS.md but missing: {entry}")

    present = set()
    for p in repo_files():
        top = p.parts[0]
        if len(p.parts) == 1:
            continue  # top-level files are not part of the layout block
        if top in LAYOUT_PARENTS:
            present.add("/".join(p.parts[:2]))
        elif top not in LAYOUT_SKIP_TOP:
            present.add(top)
    for entry in sorted(present):
        covered = entry in listed or any(l.startswith(entry + "/") for l in listed)
        if not covered:
            rep.error("layout", f"exists but not in AGENTS.md layout: {entry}")


# --- links ------------------------------------------------------------------

def resolve(md, target):
    target = target.split("#", 1)[0]
    target = re.sub(r":\d+(-\d+)?$", "", target)  # file:line
    if not target:
        return True
    for base in (ROOT / md.parent, ROOT, ROOT / "qemu"):
        if (base / target).exists():
            return True
    return False


def check_links(rep):
    for md in markdown_files():
        in_code = False
        for n, line in enumerate((ROOT / md).read_text().splitlines(), 1):
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for target in MD_LINK_RE.findall(line):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                if not resolve(md, target):
                    rep.error("links", f"{md}:{n}: broken link {target}")
            for target in CODE_PATH_RE.findall(line):
                if PLACEHOLDER_RE.search(target):
                    continue
                if not resolve(md, target):
                    rep.warn("links", f"{md}:{n}: path not found {target}")


# --- reqs -------------------------------------------------------------------

def table_ids(path):
    ids = []
    for line in (ROOT / path).read_text().splitlines():
        m = re.match(r"\|\s*(REQ-[A-Z]+-\d{3})\s*\|", line)
        if m:
            ids.append(m.group(1))
    return ids


def check_reqs(rep):
    req_path = Path("docs/spec/requirements.md")
    tr_path = Path("docs/spec/traceability.md")
    defined = table_ids(req_path)
    traced = table_ids(tr_path)
    for name, ids in ((req_path, defined), (tr_path, traced)):
        dups = sorted({i for i in ids if ids.count(i) > 1})
        for d in dups:
            rep.error("reqs", f"{name}: {d} appears in more than one row")
    for i in sorted(set(defined) - set(traced)):
        rep.error("reqs", f"{i} is in requirements.md but not traceability.md")
    for i in sorted(set(traced) - set(defined)):
        rep.error("reqs", f"{i} is in traceability.md but not requirements.md")
    known = set(defined)
    for md in markdown_files():
        for n, line in enumerate((ROOT / md).read_text().splitlines(), 1):
            for i in REQ_RE.findall(line):
                if i not in known:
                    rep.error("reqs", f"{md}:{n}: unknown requirement {i}")


# --- commits ----------------------------------------------------------------

def default_range():
    try:
        git("rev-parse", "--verify", "--quiet", "@{upstream}")
        return "@{upstream}..HEAD"
    except subprocess.CalledProcessError:
        return "HEAD"


def check_commits(rep, rng):
    out = git("log", "--format=%H%x00%B%x01", rng)
    for entry in out.split("\x01"):
        entry = entry.strip("\n")
        if not entry:
            continue
        sha, body = entry.split("\x00", 1)
        short = sha[:7]
        lines = body.strip("\n").splitlines()
        subject = lines[0] if lines else ""
        if len(subject) > 72:
            rep.error("commits", f"{short}: subject longer than 72 characters")
        m = re.match(r"([a-z]+)(?:\(([a-z-]+)\))?!?: \S", subject)
        if not m:
            rep.error("commits", f"{short}: subject is not <type>(<scope>): <subject>")
        else:
            if m.group(1) not in TYPES:
                rep.warn("commits", f"{short}: unusual type '{m.group(1)}'")
            if m.group(2) and m.group(2) not in SCOPES:
                rep.warn("commits", f"{short}: scope '{m.group(2)}' not in AGENTS.md list")
        for line in lines:
            if line.startswith("Assisted-by:"):
                rep.error("commits", f"{short}: AI attribution line '{line}'; "
                          "provenance is stated once in the README")
            if re.match(r"Co-Authored-By:", line, re.I) and \
                    re.search(r"claude|codex|anthropic|openai|gpt|\bai\b", line, re.I):
                rep.error("commits", f"{short}: AI tool credited with Co-Authored-By; "
                          "provenance is stated once in the README")


# --- skills -----------------------------------------------------------------

def check_skills(rep):
    skills = ROOT / ".agents" / "skills"
    link = ROOT / ".claude" / "skills"
    if not link.is_symlink() or link.resolve() != skills.resolve():
        rep.error("skills", ".claude/skills is not a symlink to .agents/skills")
    for md in sorted(skills.glob("*/SKILL.md")):
        name = md.parent.name
        m = re.match(r"---\n(.*?)\n---\n", md.read_text(), re.S)
        fields = dict(re.findall(r"^(\w[\w-]*):[ \t]*(.*)$", m.group(1), re.M)) if m else {}
        if fields.get("name") != name:
            rep.error("skills", f"{md.relative_to(ROOT)}: name is not '{name}'")
        if not fields.get("description"):
            rep.error("skills", f"{md.relative_to(ROOT)}: no description")


# --- main -------------------------------------------------------------------

CHECKS = {"layout": check_layout, "links": check_links, "reqs": check_reqs,
          "skills": check_skills, "style": check_style}
DEFAULT = ["layout", "links", "reqs", "skills", "commits"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checks", nargs="*", metavar="CHECK",
                    help="layout, links, reqs, commits, style "
                         "(default: all but style)")
    ap.add_argument("--commits", metavar="RANGE",
                    help="commit range for the commits check "
                         "(default: @{upstream}..HEAD, or HEAD with no upstream)")
    args = ap.parse_args()
    selected = args.checks or DEFAULT
    unknown = [c for c in selected if c not in (*CHECKS, "commits")]
    if unknown:
        ap.error(f"unknown check(s): {', '.join(unknown)}")

    rep = Report()
    for name in selected:
        if name == "commits":
            check_commits(rep, args.commits or default_range())
        else:
            CHECKS[name](rep)
    print(f"{rep.errors} error(s), {rep.warnings} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
