#!/usr/bin/env python3
"""M9 acceptance for rzv2l-smarc: A/B slots, Linux's commit, rollback and
damaged environment copies on the M9 profile (docs/units/M9-ab/spec.md,
DR-0008 decisions 5-7 and 9).

Usage: ab.py OUTDIR

The chain from the QSPI flash as fit.py, with a fresh copy of the M9
card per case. A case's starting state is written into both
environment copies before QEMU starts (uboot-env.py m9-write); a "bad"
slot gets one more health check that fails (/etc/m9-health.d/90-fail),
written into its partition with debugfs. "The card as it was left" is
a copy of the card a stopped QEMU wrote. Checks, on the serial line
(each line searched from the end of the one before), then on the
card's environment copies after QEMU stops:
  selection: BOOT_ORDER=B A: slot B's attempt saved, its FIT verified,
          / is partition 3 (525a0003-03), the health service commits B;
          newest copy: BOOT_B_LEFT=3, M9_GOOD=B
  good update: pending B, healthy: B boots and the update is
          committed (M9_PENDING gone); a new QEMU on the card as it was
          left boots B again
  bad update: pending B, B unhealthy: B refused by its health check,
          QEMU stopped once B's second attempt is saved, a new QEMU
          continues on the card as it was left: B's last attempt, then
          slot A, which commits and records the rollback (M9_ROLLBACK=B,
          BOOT_ORDER=A B, M9_PENDING gone)
  both exhausted: both slots unhealthy: three attempts each, then the
          U-Boot prompt with every counter at 0
  damaged copies: copy 1, copy 2, then both, damaged before the boot:
          U-Boot reads the other copy (or warns and uses its default
          environment, the M9 policy), boots A from the signed FIT, and
          both copies are valid afterwards
Exit 0 only if every check passes. QEMU binary: $QEMU.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fit  # noqa: E402
import bootloader  # noqa: E402  (fit puts ../m7 on the path)
import firmware  # noqa: E402
from firmware import check  # noqa: E402

PART = {"A": (40960, 98304), "B": (139264, 122880)}   # build-image-m9.sh
SIGNED = r"Verifying Hash Integrity \.\.\. sha256,rsa2048:m9-dev\+ OK"


def unhealthy(img, slot, out):
    """Add a failing health check to slot's root on img"""
    start, n = PART[slot]
    part = os.path.join(out, "part.img")
    fail = os.path.join(out, "90-fail")
    open(fail, "w").write("#!/bin/sh\n# a failing health check (ab.py)\n"
                          "exit 1\n")
    with open(img, "rb") as f:
        f.seek(start * 512)
        open(part, "wb").write(f.read(n * 512))
    for req in ("write %s /etc/m9-health.d/90-fail" % fail,
                "sif /etc/m9-health.d/90-fail mode 0100755"):
        subprocess.run(["debugfs", "-w", "-R", req, part], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(img, "r+b") as f:
        f.seek(start * 512)
        f.write(open(part, "rb").read())
    os.unlink(part)


def copies(out, img):
    """The card's environment copies after the run: [(valid, flag, vars)]"""
    res = []
    for line in fit.env_after(out, img).splitlines():
        m = re.match(r"copy \d: (valid|invalid) flag (\d+) ?(.*)$", line)
        if m:
            res.append((m.group(1) == "valid", int(m.group(2)),
                        dict(v.split("=", 1) for v in
                             re.findall(r"(\w+=(?:A B|B A|\S+))", m.group(3)))))
    return res


def newest(out, img):
    valid = [c for c in copies(out, img) if c[0]]
    return max(valid, key=lambda c: c[1])[2] if valid else {}


def left(out, img):
    """The card a stopped run left, as the next run's source card"""
    return os.path.join(out, "slot0-" + os.path.basename(img))


def committed(s, pos, slot, puuid, what):
    return fit.in_order(s, [r"M9-HEALTH: slot %s committed, / is %s" %
                            (slot, puuid)], pos, what)


def selection(out):
    img = fit.card(out, None, ["BOOT_ORDER=B A"])
    proc, s, log = fit.start(out, img)
    try:
        pos = fit.in_order(s, [r"M9: slot B: attempt saved: BOOT_A_LEFT=3 "
                               r"BOOT_B_LEFT=2", SIGNED, r"Starting kernel"],
                           0, "selection")
        if pos is not None:
            committed(s, pos, "B", "525a0003-03", "selection")
    finally:
        bootloader.stop(proc, log)
    env = newest(out, img)
    check(env.get("BOOT_B_LEFT") == "3" and env.get("M9_GOOD") == "B",
          "selection: newest copy BOOT_B_LEFT=3, M9_GOOD=B (%s)" % env)


def good_update(out):
    state = ["BOOT_ORDER=B A", "M9_PENDING=B"]
    img = fit.card(os.path.join(out, "1"), None, state)
    proc, s, log = fit.start(os.path.join(out, "1"), img)
    try:
        pos = fit.in_order(s, [r"M9: slot B: attempt saved", SIGNED,
                               r"M9-HEALTH: slot B committed, / is "
                               r"525a0003-03",
                               r"M9-HEALTH: the update of slot B is "
                               r"committed"], 0, "good update")
    finally:
        bootloader.stop(proc, log)
    env = newest(os.path.join(out, "1"), img)
    check("M9_PENDING" not in env and env.get("M9_GOOD") == "B" and
          env.get("BOOT_B_LEFT") == "3",
          "good update: M9_PENDING gone, M9_GOOD=B, BOOT_B_LEFT=3 (%s)" % env)
    # A new QEMU on the card as it was left
    proc, s, log = fit.start(os.path.join(out, "2"),
                             left(os.path.join(out, "1"), img))
    try:
        pos = fit.in_order(s, [r"M9: slot B: attempt saved: BOOT_A_LEFT=3 "
                               r"BOOT_B_LEFT=2", SIGNED], 0,
                           "good update, new QEMU")
        if pos is not None:
            committed(s, pos, "B", "525a0003-03", "good update, new QEMU")
    finally:
        bootloader.stop(proc, log)
    env = newest(os.path.join(out, "2"), left(os.path.join(out, "1"), img))
    check("M9_PENDING" not in env and env.get("M9_GOOD") == "B" and
          env.get("BOOT_B_LEFT") == "3",
          "good update, new QEMU: M9_PENDING still gone, B committed again "
          "(%s)" % env)


def bad_update(out):
    o1, o2 = os.path.join(out, "1"), os.path.join(out, "2")
    img = fit.card(o1, None, ["BOOT_ORDER=B A", "M9_PENDING=B"])
    unhealthy(img, "B", o1)
    proc, s, log = fit.start(o1, img)
    try:
        fit.in_order(s, [r"M9: slot B: attempt saved: BOOT_A_LEFT=3 "
                         r"BOOT_B_LEFT=2", SIGNED,
                         r"M9-HEALTH: slot B: health check 90-fail failed; "
                         r"not committed; rebooting",
                         r"M9: slot B: attempt saved: BOOT_A_LEFT=3 "
                         r"BOOT_B_LEFT=1"], 0, "bad update")
    finally:
        bootloader.stop(proc, log)   # stopped once that attempt is saved
    env = newest(o1, img)
    check(env.get("BOOT_B_LEFT") == "1",
          "bad update: the stopped run left BOOT_B_LEFT=1 (%s)" % env)
    proc, s, log = fit.start(o2, left(o1, img))
    try:
        pos = fit.in_order(s, [r"M9: slot B: attempt saved: BOOT_A_LEFT=3 "
                               r"BOOT_B_LEFT=0",
                               r"M9-HEALTH: slot B: health check 90-fail",
                               r"M9: slot A: attempt saved: BOOT_A_LEFT=2 "
                               r"BOOT_B_LEFT=0", SIGNED,
                               r"M9-HEALTH: slot A committed, / is "
                               r"525a0003-02",
                               r"M9-HEALTH: rollback: slot B gave up, slot A "
                               r"runs"], 0, "bad update, new QEMU")
    finally:
        bootloader.stop(proc, log)
    env = newest(o2, left(o1, img))
    check(env.get("M9_ROLLBACK") == "B" and env.get("BOOT_ORDER") == "A B"
          and "M9_PENDING" not in env and env.get("M9_GOOD") == "A" and
          env.get("BOOT_A_LEFT") == "3",
          "bad update: M9_ROLLBACK=B, BOOT_ORDER=A B, M9_PENDING gone, "
          "M9_GOOD=A, BOOT_A_LEFT=3 (%s)" % env)


def both_exhausted(out):
    img = fit.card(out, None)
    unhealthy(img, "A", out)
    unhealthy(img, "B", out)
    proc, s, log = fit.start(out, img)
    try:
        pats = []
        for a, b in ((2, 3), (1, 3), (0, 3), (0, 2), (0, 1), (0, 0)):
            slot = "A" if b == 3 else "B"
            pats += [r"M9: slot %s: attempt saved: BOOT_A_LEFT=%d "
                     r"BOOT_B_LEFT=%d" % (slot, a, b),
                     r"M9-HEALTH: slot %s: health check 90-fail failed" % slot]
        pats += [r"M9: no slot has an attempt left: BOOT_ORDER=A B "
                 r"BOOT_A_LEFT=0 BOOT_B_LEFT=0", r"=> "]
        fit.in_order(s, pats, 0, "both exhausted")
    finally:
        bootloader.stop(proc, log)
    env = newest(out, img)
    check(env.get("BOOT_A_LEFT") == "0" and env.get("BOOT_B_LEFT") == "0",
          "both exhausted: the counters stay at 0 (%s)" % env)


def damaged(out, which):
    what = "damaged copy %s" % which
    img = fit.card(out, None)
    for n in which.split("+"):
        subprocess.run([sys.executable, "-I", fit.UENV, "m9-damage", img, n],
                       check=True)
    before = subprocess.run([sys.executable, "-I", fit.UENV, "m9-read", img],
                            capture_output=True, text=True).stdout
    check(all(re.search(r"copy %d: (in)?valid" % n, before) and
              ("copy %d: invalid" % n in before) == (str(n) in which)
              for n in (1, 2)),
          "%s: before the boot, exactly copy %s is invalid (%s)"
          % (what, which, " | ".join(before.splitlines())))
    first = {"1": r"Reading from redundant MMC\(0\)\.\.\. OK",
             "2": r"Loading Environment from MMC\.\.\. Reading from MMC\(0\)"
                  r"\.\.\. OK",
             "1+2": r"\*\*\* Warning - bad CRC, using default environment"}
    proc, s, log = fit.start(out, img)
    try:
        pos = fit.in_order(s, [first[which],
                               r"M9: slot A: attempt saved: BOOT_A_LEFT=2 "
                               r"BOOT_B_LEFT=3", SIGNED, r"Starting kernel",
                               r"M9-HEALTH: slot A committed, / is "
                               r"525a0003-02"], 0, what)
        if pos is not None:
            check(s.buf.count("NOTICE:  BL2: v2") == 1,
                  "%s: one boot, no reset" % what)
    finally:
        bootloader.stop(proc, log)
    state = copies(out, img)
    check(len(state) == 2 and all(c[0] for c in state),
          "%s: both copies valid afterwards (%s)" % (what, state))


def main():
    out = sys.argv[1]
    shutil.rmtree(out, ignore_errors=True)
    selection(os.path.join(out, "selection"))
    good_update(os.path.join(out, "good-update"))
    bad_update(os.path.join(out, "bad-update"))
    both_exhausted(os.path.join(out, "both-exhausted"))
    for which in ("1", "2", "1+2"):
        damaged(os.path.join(out, "damaged-" + which.replace("+", "-")),
                which)
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
