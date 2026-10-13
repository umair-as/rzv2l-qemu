#!/usr/bin/env python3
"""Compare the facts in two versions of a Markdown file (docs/learning/STYLE.md §4).

A rewrite for style must keep every fact. This script lists what is in one
version only:
  code    each `code span`
  number  each decimal or hex number outside code (0x11020A04, 24, 6.3.43)
  ref     each section reference (§N) and each link target
  quote   each "quoted text" of four words or more (quotes from sources)
  block   each fenced code block, compared whole

Usage: scripts/doc-facts.py OLD NEW
       scripts/doc-facts.py REV:PATH PATH    (OLD from git, e.g. HEAD:docs/...)
Exit status is 1 if any fact is in one version only.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(arg):
    if ":" in arg and not Path(arg).exists():
        return subprocess.run(["git", "show", arg], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout
    return Path(arg).read_text()


def facts(text):
    found = {"code": set(), "number": set(), "ref": set(), "quote": set(),
             "block": set()}
    blocks = re.findall(r"^[ \t]*```.*?^[ \t]*```", text, flags=re.S | re.M)
    found["block"] = {b.strip() for b in blocks}
    prose = re.sub(r"^[ \t]*```.*?^[ \t]*```", "", text, flags=re.S | re.M)
    found["code"] = set(re.findall(r"`([^`]+)`", prose))
    rest = re.sub(r"`[^`]+`", " ", prose)
    found["ref"] = set(re.findall(r"§\d+(?:\.\d+)*", rest))
    found["ref"] |= set(re.findall(r"\]\(([^)\s]+)\)", rest))
    rest = re.sub(r"\]\([^)\s]+\)", "]", rest)
    found["quote"] = {q for q in re.findall(r'"([^"]+)"', rest)
                      if len(q.split()) >= 4}
    found["number"] = set(re.findall(
        r"(?<![\w.])(?:0x[0-9A-Fa-f_]+|\d+(?:\.\d+)*)(?![\w])", rest))
    return found


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    old, new = facts(read(sys.argv[1])), facts(read(sys.argv[2]))
    rc = 0
    for kind in old:
        for side, a, b in (("only in OLD", old, new), ("only in NEW", new, old)):
            for item in sorted(a[kind] - b[kind]):
                rc = 1
                shown = item if kind != "block" else item.splitlines()[0] + " …"
                print(f"{side:12} {kind:6} {shown}")
    if not rc:
        print("same facts: %s" % ", ".join(f"{len(v)} {k}" for k, v in new.items()))
    return rc


if __name__ == "__main__":
    sys.exit(main())
