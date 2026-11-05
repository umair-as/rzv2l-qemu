#!/usr/bin/env python3
"""M9 acceptance for rzv2l-smarc: a slot update and its interruptions on
the M9 profile (docs/units/M9-update-failure/spec.md, DR-0008 decisions
8 and 10).

Usage: update.py OUTDIR

The chain from the QSPI flash as fit.py, with fresh copies of the M9
card (module slot) and the update card (carrier slot,
tests/guests/out/sd/sd-m9-update.img: the version-2 payload and its
SHA-256) per case. Slot A (version 1) runs /sbin/m9-update, which
targets slot B. An interruption stops the QEMU process at a console
line, then a new QEMU starts on the image files the stopped one left,
unchanged: a process interruption, not a power loss of the card.
Checks, on the serial line (each line searched from the end of the one
before) and on the card's active environment copy after each run:
  success: the tool marks B unbootable, writes, verifies and selects it;
          after reboot B boots version 2 as the pending update and
          commits it; then M9_GOOD=B, BOOT_ORDER=B A, BOOT_B_LEFT=3, no
          M9_PENDING, no M9_ROLLBACK
  reverse: from the media the success case left, slot B (version 2)
          runs the tool, which updates slot A; A then boots version 2
  media: after both, on the image file: the written slot holds the
          payload's bytes, and the running slot keeps its version and
          its signed FIT
  refused payload: one payload byte changed: the tool stops at the
          verification; BOOT_B_LEFT=0, nothing pending; after reboot,
          slot A (version 1) boots
  interrupted while writing / after verifying: the stopped card holds
          BOOT_B_LEFT=0 and nothing pending; a new QEMU boots slot A
          (version 1), which commits; after the write interruption the
          tool runs again to completion and B boots version 2
  interrupted while saving the selection (four runs, stopped 0, 0.05,
          0.3 and 1.0 s after the line; at 1.0 s the save has finished, so
          the new state is reached on every run): the active copy is the whole old
          state or the whole new state, the boot follows it, and the run
          prints which (NOTE line)
Exit 0 only if every check passes. QEMU binary: $QEMU.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ab  # noqa: E402
import fit  # noqa: E402
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check, run  # noqa: E402

UPDATE = os.path.join(fit.GUESTS, "out", "sd", "sd-m9-update.img")
PAYLOAD = os.path.join(fit.GUESTS, "out", "sd", "m9-payload.img")
UPDATE_P1 = 8192                       # build-image-m9.sh
WAIT = 300                             # seconds for the tool to finish
SIGNED = r"Verifying Hash Integrity \.\.\. sha256,rsa2048:m9-dev\+ OK"


def start(out, card, update):
    bootloader.IMAGE = card
    return bootloader.start(out, carrier=update, flash=fit.FLASH)


def left(out, img):
    name = os.path.basename(img)
    return os.path.join(out, "slot%d-%s" % (1 if "update" in name else 0,
                                            name))


def cards(out, payload=None):
    """Fresh copies of the M9 card and the update card (its payload
    replaced by payload, if given)"""
    os.makedirs(out, exist_ok=True)
    card = fit.card(out, None)
    upd = os.path.join(out, "source-sd-m9-update.img")
    shutil.copyfile(UPDATE, upd)
    if payload:
        part = os.path.join(out, "upd-p1.img")
        with open(upd, "rb") as f:
            f.seek(UPDATE_P1 * 512)
            open(part, "wb").write(f.read())
        for req in ("rm /m9-payload.img", "write %s /m9-payload.img" % payload):
            subprocess.run(["debugfs", "-w", "-R", req, part], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(upd, "r+b") as f:
            f.seek(UPDATE_P1 * 512)
            f.write(open(part, "rb").read())
        os.unlink(part)
    return card, upd


def slot_bytes_sha(img, slot, size):
    """SHA-256 of the first size bytes of slot's partition in img"""
    start, _ = ab.PART[slot]
    with open(img, "rb") as f:
        f.seek(start * 512)
        return hashlib.sha256(f.read(size)).hexdigest()


def slot_file(img, slot, path, out):
    """A file from slot's root file system in img (debugfs)"""
    start, n = ab.PART[slot]
    part = os.path.join(out, "check-part.img")
    with open(img, "rb") as f:
        f.seek(start * 512)
        open(part, "wb").write(f.read(n * 512))
    data = subprocess.run(["debugfs", "-R", "cat %s" % path, part],
                          capture_output=True).stdout
    os.unlink(part)
    return data


def media(out, img, written, kept, what):
    """On the image file the stopped QEMU left: the written slot holds the
    payload's bytes; the kept (running) slot still holds version 1 or 2
    as before and the signed FIT"""
    want = open(PAYLOAD + ".sha256").read().split()[0]
    check(slot_bytes_sha(img, written, os.path.getsize(PAYLOAD)) == want,
          "%s: on the card, slot %s holds the payload's bytes" % (what, written))
    fit_sha = hashlib.sha256(open(os.path.join(fit.FITS, "fitImage"),
                                  "rb").read()).hexdigest()
    got = hashlib.sha256(slot_file(img, kept, "/boot/fitImage",
                                   out)).hexdigest()
    check(got == fit_sha, "%s: on the card, slot %s's FIT is unchanged"
          % (what, kept))
    return slot_file(img, kept, "/etc/m9-version", out).decode().strip()


def state(out, card):
    act = fit.active(fit.parse(fit.env_after(out, card)))
    return act[2] if act else {}


def booted(s, pos, slot, version, what, pending=False):
    """slot boots version and commits; returns the position after"""
    pats = [r"M9: slot %s: attempt saved" % slot, SIGNED,
            r"M9 slot %s, version %d," % (slot, version),
            r"M9-HEALTH: slot %s committed" % slot]
    if pending:
        pats.append(r"M9-HEALTH: the update of slot %s is committed" % slot)
    return fit.in_order(s, pats, pos, what, timeout=180)


def up(s, what):
    """The shell is up; kernel messages are kept off the console from here
    on, so that none lands inside a line the test waits for"""
    m = firmware.wait_root(s, 0, what)
    return m is not None and run(s, "dmesg -n 1") is not None


def update_ok(s, what):
    pos = len(s.buf)
    out = run(s, "m9-update; echo rc=$?", WAIT) or ""
    p = fit.in_order(s, [r"M9-UPDATE: marking slot B not bootable",
                         r"M9-UPDATE: writing slot B",
                         r"M9-UPDATE: slot B verified",
                         r"M9-UPDATE: saving the selection",
                         r"M9-UPDATE: slot B selected as a pending update",
                         r"rc=0"], pos, what, timeout=10)
    return p is not None and "rc=0" in out


def update_then_boot(out, card, upd, running, target, version_before,
                     what):
    """Run 1: running boots, the tool updates target, QEMU stops right
    after it; the image file then holds the payload in target and
    running's version and FIT unchanged. Run 2, a new QEMU on that
    media: target boots version 2 as the pending update and commits.
    Returns the card run 2 left."""
    o1, o2 = os.path.join(out, "1"), os.path.join(out, "2")
    proc, s, log = start(o1, card, upd)
    try:
        ok = booted(s, 0, running, version_before, what) is not None and \
            up(s, what)
        if ok:
            res = run(s, "m9-update; echo rc=$?", WAIT) or ""
            ok = check(("updating slot %s (" % target) in res and
                       "rc=0" in res and
                       ("slot %s selected as a pending update" % target)
                       in res, "%s: slot %s runs, the tool updates slot %s"
                       % (what, running, target))
    finally:
        bootloader.stop(proc, log)      # stopped right after the tool
    left1 = left(o1, card)
    v = media(o1, left1, target, running, what)
    check(v == str(version_before), "%s: on the card, slot %s still holds "
          "version %d (%r)" % (what, running, version_before, v))
    env = state(o1, card)
    check(env.get("M9_PENDING") == target and
          env.get("BOOT_%s_LEFT" % target) == "3" and
          env.get("BOOT_ORDER") == "%s %s" % (target, running),
          "%s: the stopped card selects slot %s as pending (%s)"
          % (what, target, env))
    proc, s, log = start(o2, left1, left(o1, upd))
    try:
        booted(s, 0, target, 2, "%s, new QEMU" % what, pending=True)
    finally:
        bootloader.stop(proc, log)
    return o2, left(o2, left1)


def success(out):
    card, upd = cards(out)
    o2, last = update_then_boot(out, card, upd, "A", "B", 1, "success")
    acts = fit.active(fit.parse(fit.env_of(last)))
    env = acts[2] if acts else {}
    check(env.get("M9_GOOD") == "B" and env.get("BOOT_ORDER") == "B A" and
          env.get("BOOT_B_LEFT") == "3" and "M9_PENDING" not in env and
          "M9_ROLLBACK" not in env,
          "success: M9_GOOD=B, BOOT_ORDER=B A, BOOT_B_LEFT=3, nothing "
          "pending (%s)" % env)


def reverse(out, before):
    """From the media success() left (B runs version 2): the tool now
    targets slot A, and A then boots version 2"""
    card = os.path.join(before, "2", "slot0-slot0-source-sd-m9.img")
    upd = os.path.join(before, "1", "slot1-source-sd-m9-update.img")
    update_then_boot(out, card, upd, "B", "A", 2, "reverse")


def refused(out):
    os.makedirs(out, exist_ok=True)
    bad = os.path.join(out, "m9-payload.img")
    data = bytearray(open(PAYLOAD, "rb").read())
    data[len(data) // 2] ^= 0x01
    open(bad, "wb").write(data)
    card, upd = cards(out, bad)
    proc, s, log = start(out, card, upd)
    try:
        if up(s, "refused payload"):
            pos = len(s.buf)
            res = run(s, "m9-update; echo rc=$?", WAIT) or ""
            fit.in_order(s, [r"M9-UPDATE: verifying slot B",
                             r"M9-UPDATE: stopped: slot B holds \w+, the "
                             r"payload's checksum is \w+; nothing selected",
                             r"rc=1"], pos, "refused payload", timeout=10)
            check("saving the selection" not in res,
                  "refused payload: no selection saved")
            env = None
            pos = len(s.buf)
            s.send("reboot")
            booted(s, pos, "A", 1, "refused payload, reboot")
    finally:
        bootloader.stop(proc, log)
    env = state(out, card)
    check(env.get("BOOT_B_LEFT") == "0" and "M9_PENDING" not in env and
          env.get("BOOT_ORDER") == "A B",
          "refused payload: BOOT_B_LEFT=0, nothing pending, BOOT_ORDER=A B "
          "(%s)" % env)


def interrupted(out, marker, delay, what, retry=False):
    """Stop QEMU delay s after marker; then a new QEMU on the media it
    left. Returns the stopped card's active environment."""
    o1, o2 = os.path.join(out, "1"), os.path.join(out, "2")
    card, upd = cards(o1)
    proc, s, log = start(o1, card, upd)
    try:
        if up(s, what):
            pos = len(s.buf)
            s.send("m9-update")
            hit = s.wait(marker, WAIT, pos)
            check(hit is not None, "%s: the tool reaches '%s'" % (what, marker))
            time.sleep(delay)
    finally:
        bootloader.stop(proc, log)      # the process interruption
    env = state(o1, card)
    return env, o1, o2, card, upd


def interrupted_early(out, marker, what, retry):
    env, o1, o2, card, upd = interrupted(out, marker, 1.0 if retry else 0,
                                         what)
    check(env.get("BOOT_B_LEFT") == "0" and "M9_PENDING" not in env,
          "%s: the stopped card holds BOOT_B_LEFT=0, nothing pending (%s)"
          % (what, env))
    proc, s, log = start(o2, left(o1, card), left(o1, upd))
    try:
        if booted(s, 0, "A", 1, "%s, new QEMU" % what) is not None and retry:
            if up(s, "%s, retry" % what) and \
                    update_ok(s, "%s, retry" % what):
                pos = len(s.buf)
                s.send("reboot")
                booted(s, pos, "B", 2, "%s, retry, reboot" % what,
                       pending=True)
    finally:
        bootloader.stop(proc, log)


OLD = {"BOOT_B_LEFT": "0", "BOOT_ORDER": "A B"}
NEW = {"BOOT_B_LEFT": "3", "BOOT_ORDER": "B A", "M9_PENDING": "B"}


def old_or_new(env, what):
    """The active copy after an interrupted selection save must be the
    whole old state or the whole new state; returns (is_old, is_new)"""
    is_old = all(env.get(k) == v for k, v in OLD.items()) and \
        "M9_PENDING" not in env
    is_new = all(env.get(k) == v for k, v in NEW.items())
    check(is_old != is_new, "%s: the active copy is the whole old or the "
          "whole new state (%s)" % (what, env))
    return is_old, is_new


def interrupted_env(out, delay):
    what = "interrupted saving the selection (+%.2f s)" % delay
    env, o1, o2, card, upd = interrupted(
        out, r"M9-UPDATE: saving the selection", delay, what)
    is_old, is_new = old_or_new(env, what)
    print("NOTE %s: the stopped card holds the %s state"
          % (what, "new" if is_new else "old" if is_old else "MIXED"))
    proc, s, log = start(o2, left(o1, card), left(o1, upd))
    try:
        if is_new:
            booted(s, 0, "B", 2, "%s, new QEMU" % what, pending=True)
        else:
            booted(s, 0, "A", 1, "%s, new QEMU" % what)
    finally:
        bootloader.stop(proc, log)


def main():
    out = sys.argv[1]
    for f in (fit.FLASH, fit.CARD, UPDATE, PAYLOAD):
        if not os.path.exists(f):
            print("FAIL missing %s (tests/guests/sd/build-image-m9.sh)" % f)
            return 1
    only = sys.argv[2:]
    shutil.rmtree(out, ignore_errors=True)
    cases = [("success", lambda o: success(o)),
             ("reverse", lambda o: reverse(o, os.path.join(out, "success"))),
             ("refused", lambda o: refused(o)),
             ("interrupted-write", lambda o: interrupted_early(
                 o, r"M9-UPDATE: writing slot B",
                 "interrupted while writing", True)),
             ("interrupted-verified", lambda o: interrupted_early(
                 o, r"M9-UPDATE: slot B verified",
                 "interrupted after verifying", False))] + \
        [("interrupted-env-%s" % d, lambda o, d=d: interrupted_env(o, d))
         for d in (0, 0.05, 0.3, 1.0)]
    for name, fn in cases:
        if not only or name in only:
            fn(os.path.join(out, name))
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
