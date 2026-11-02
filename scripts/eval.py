#!/usr/bin/env python3
"""Run a milestone's eval checks and prove each one with its mutations.

Usage: uv run scripts/eval.py m2 [--fork SHA] [--only ID ...] [--no-mutations]

For the fork commit (default: the commit checked out in qemu/), this:
  1. creates a fresh git worktree of the fork under build/eval/<m>/src
     (never the qemu/ checkout itself) and builds it out of tree in
     build/eval/<m>/build;
  2. runs every check in tests/eval/<m>/checks.yaml and requires it green;
  3. for each mutation: applies tests/eval/<m>/mutations/<id>.patch to the
     worktree, rebuilds, asserts that qemu-system-aarch64 was relinked,
     runs only that mutation's check, requires its red_line, and reverts;
  4. checks the worktree is clean again and writes build/eval/<m>/report.md.

Exit status 0 only when every check is green and every mutation is red on
its stated line.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FORK = ROOT / "qemu"
QTEST = "tests/qtest/rzv2l-scifa-test"
QEMU = "qemu-system-aarch64"
CHECK_TIMEOUT = 300


def run(cmd, cwd, env=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, text=True)


def must(cmd, cwd, what):
    r = run(cmd, cwd)
    if r.returncode:
        sys.exit("eval: %s failed (rc %d):\n%s%s" %
                 (what, r.returncode, r.stdout[-3000:], r.stderr[-3000:]))
    return r.stdout


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(src, build, sha):
    """A fresh worktree at `sha`, and an out-of-tree build directory."""
    if src.exists():
        run(["git", "worktree", "remove", "--force", str(src)], FORK)
        shutil.rmtree(src, ignore_errors=True)
    run(["git", "worktree", "prune"], FORK)
    must(["git", "worktree", "add", "--detach", str(src), sha], FORK,
         "git worktree add")
    build.mkdir(parents=True, exist_ok=True)
    if not (build / "build.ninja").exists():
        configure = [str(src / "configure"), "--target-list=aarch64-softmmu",
                     "--disable-docs"]
        if shutil.which("ccache"):
            configure.append("--cc=ccache " + os.environ.get("CC", "cc"))
        must(configure, build, "configure")


def ninja(build, fatal=True):
    """Build the emulator and the qtest; on failure exit, or return False."""
    if fatal:
        must(["ninja", QEMU, QTEST], build, "ninja")
        return True
    r = run(["ninja", QEMU, QTEST], build)
    if r.returncode:
        print(r.stdout[-1500:])
    return r.returncode == 0


def run_check(check, build):
    """Run one check against the eval build; return (rc, output)."""
    if check["kind"] == "qtest":
        env = dict(os.environ, QTEST_QEMU_BINARY=str(build / QEMU))
        cmd, cwd = [str(build / QTEST), "-p", check["test"]], build
    elif check["kind"] == "acceptance":
        env = dict(os.environ, QEMU=str(build / QEMU))
        cmd, cwd = ["bash", str(ROOT / check["run"])], ROOT
    else:
        sys.exit("eval: unknown check kind %r" % check["kind"])
    try:
        r = run(cmd, cwd, env, CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "timeout after %d s" % CHECK_TIMEOUT
    return r.returncode, r.stdout + r.stderr


def passed(check, rc, text):
    if rc != 0:
        return False
    if check["kind"] == "qtest":
        return bool(re.search(r"^ok \d+ " + re.escape(check["test"]) + "$",
                              text, re.M))
    return bool(re.search(check["pass"], text, re.M))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("milestone")
    ap.add_argument("--fork", help="fork commit (default: qemu/ HEAD)")
    ap.add_argument("--only", nargs="*", help="check IDs to run")
    ap.add_argument("--no-mutations", action="store_true")
    a = ap.parse_args()

    spec_dir = ROOT / "tests/eval" / a.milestone
    spec = yaml.safe_load((spec_dir / "checks.yaml").read_text())
    checks = {c["id"]: c for c in spec["checks"]}
    muts = spec.get("mutations", [])
    if a.only:
        checks = {k: v for k, v in checks.items() if k in a.only}
        muts = [m for m in muts if m["check"] in a.only]
    known = {c["id"] for c in spec["checks"]}
    for m in muts:
        if m["check"] not in known:
            sys.exit("eval: mutation %s names unknown check %s"
                     % (m["id"], m["check"]))

    sha = a.fork or must(["git", "rev-parse", "HEAD"], FORK, "rev-parse")
    sha = must(["git", "rev-parse", sha.strip()], FORK, "rev-parse").strip()
    out = ROOT / "build/eval" / a.milestone
    src, build = out / "src", out / "build"
    t0 = time.time()
    prepare(src, build, sha)
    ninja(build)

    rows, ok = [], True
    green = {}
    for cid, c in checks.items():
        rc, text = run_check(c, build)
        green[cid] = passed(c, rc, text)
        if not green[cid]:
            ok = False
            print("RED   check %s (%s)\n%s" % (cid, c.get("test", c.get("run")),
                                             text[-1500:]))
        else:
            print("green check %s" % cid)

    for m in ([] if a.no_mutations else muts):
        patch = spec_dir / "mutations" / (m.get("patch", m["id"]) + ".patch")
        before = sha256(build / QEMU)
        must(["git", "apply", str(patch)], src, "apply " + m["id"])
        rc, text, matched = None, "mutation did not build", False
        try:
            relinked = ninja(build, fatal=False) and \
                sha256(build / QEMU) != before
            if relinked:
                rc, text = run_check(checks[m["check"]], build)
                matched = bool(rc and re.search(m["red_line"], text, re.M))
        finally:
            must(["git", "apply", "-R", str(patch)], src, "revert " + m["id"])
        red = relinked and matched
        ok = ok and red
        rows.append((m["id"], m["check"], green.get(m["check"]), relinked,
                     rc, matched))
        print("%s mutation %s (check %s): relinked=%s rc=%s red_line=%s"
              % ("red " if red else "MISS", m["id"], m["check"], relinked,
                 rc, matched))
        if not red:
            print(text[-1500:])

    ninja(build)
    dirty = must(["git", "status", "--porcelain"], src, "git status")
    if dirty:
        ok = False
        print("eval: worktree not clean after the mutations:\n" + dirty)

    lines = ["# Eval report: %s" % a.milestone, "",
             "Fork commit `%s`; %d checks, %d mutations; %.0f s." %
             (sha, len(checks), len(rows), time.time() - t0), "",
             "| Check | Test | Green |", "|---|---|---|"]
    lines += ["| %s | `%s` | %s |" % (k, v.get("test", v.get("run")),
                                      "yes" if green[k] else
                                      "**NO**") for k, v in checks.items()]
    lines += ["", "| Mutation | Check | Check green | Relinked | Mutated rc |"
              " Red line matched |", "|---|---|---|---|---|---|"]
    lines += ["| %s | %s | %s | %s | %s | %s |" %
              (mid, cid, "yes" if g else "**NO**", "yes" if rl else "**NO**",
               rc, "yes" if mt else "**NO**")
              for mid, cid, g, rl, rc, mt in rows]
    lines += ["", "Result: **%s**" % ("PASS" if ok else "FAIL"), ""]
    (out / "report.md").write_text("\n".join(lines))
    print("EVAL %s: %s (report: build/eval/%s/report.md)"
          % (a.milestone, "PASS" if ok else "FAIL", a.milestone))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
