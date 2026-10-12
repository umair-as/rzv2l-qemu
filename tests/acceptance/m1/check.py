#!/usr/bin/env python3
"""M1 acceptance checks on captured QEMU output (M1-T06).

Usage: check.py mtree|qtree|roms|log <captured-file> [<expected-file>]
Prints what differs and exits 1 on a mismatch, 0 when the check passes.
"""
import re
import sys

# Firmware-reserved DDR (docs/device-map.md, DDR row; M1 spec AC07)
RESERVED = (0x40000000, 0x48000000)
# Linux memory window given by the board firmware
LINUX_MEM = (0x48000000, 0x48000000 + 0x78000000)


def expected_lines(path):
    with open(path) as f:
        return [l.rstrip("\n") for l in f
                if l.strip() and not l.startswith("#")]


def fail(msg):
    print("FAIL " + msg)
    return 1


def check_mtree(captured, expected):
    """Exact match on the flat view that serves the "memory" address space."""
    text = open(captured).read()
    views = re.split(r"\nFlatView #\d+\n", text)
    view = next((v for v in views if 'AS "memory",' in v), None)
    if view is None:
        return fail('mtree: no flat view for AS "memory"')
    got = [l.strip() for l in view.splitlines()
           if re.match(r"\s*[0-9a-f]{16}-[0-9a-f]{16} ", l)]
    want = [l.strip() for l in expected_lines(expected)]
    if got != want:
        print("FAIL mtree: memory map differs")
        print("  expected:\n    " + "\n    ".join(want))
        print("  got:\n    " + "\n    ".join(got))
        return 1
    print("PASS mtree: %d windows, nothing else" % len(got))
    return 0


def check_qtree(captured, expected):
    """Exact device set; listed lines present in each device's block."""
    blocks = {}
    cur = None
    for l in open(captured):
        m = re.match(r"\s*dev: ([^,]+), id", l)
        if m:
            cur = m.group(1)
            if cur in blocks:
                return fail("qtree: device %s appears twice" % cur)
            blocks[cur] = []
        elif cur:
            blocks[cur].append(l.strip())
    want = {}
    cur = None
    for l in expected_lines(expected):
        if l.startswith("dev: "):
            cur = l[5:]
            want[cur] = []
        else:
            want[cur].append(l.strip())
    rc = 0
    if set(blocks) != set(want):
        rc = fail("qtree: devices %s, expected %s"
                  % (sorted(blocks), sorted(want)))
    for dev, lines in want.items():
        for l in lines:
            if l not in blocks.get(dev, []):
                rc = fail("qtree: %s: missing '%s'" % (dev, l))
    if not rc:
        print("PASS qtree: %d devices, %d properties"
              % (len(want), sum(len(v) for v in want.values())))
    return rc


def check_roms(captured):
    """Every blob inside the Linux window; none in reserved DDR."""
    rc = 0
    n = 0
    for l in open(captured):
        m = re.match(r"addr=([0-9a-f]+) size=0x([0-9a-f]+) mem=(\w+) "
                     r'name="(.*)"', l.strip())
        if not m:
            continue
        n += 1
        addr, size = int(m.group(1), 16), int(m.group(2), 16)
        end = addr + size
        name = m.group(4)
        if addr < RESERVED[1] and end > RESERVED[0]:
            rc = fail("roms: %s at 0x%x-0x%x overlaps reserved 0x%x-0x%x"
                      % (name, addr, end - 1, RESERVED[0], RESERVED[1] - 1))
        elif not (LINUX_MEM[0] <= addr and end <= LINUX_MEM[1]):
            rc = fail("roms: %s at 0x%x-0x%x outside the Linux window"
                      % (name, addr, end - 1))
    if n == 0:
        rc = fail("roms: no blobs listed")
    if not rc:
        print("PASS roms: %d blobs, none in 0x%x-0x%x"
              % (n, RESERVED[0], RESERVED[1] - 1))
    return rc


def check_log(captured, allowed):
    """Every -d line must be on the allow-list."""
    allow = set(expected_lines(allowed))
    bad = [l.rstrip("\n") for l in open(captured)
           if l.strip() and l.rstrip("\n") not in allow]
    if bad:
        print("FAIL log: %d unexpected line(s):" % len(bad))
        for l in bad:
            print("    " + l)
        return 1
    print("PASS log: only the %d allowed line(s)" % len(allow))
    return 0


def main():
    what, captured = sys.argv[1], sys.argv[2]
    ref = sys.argv[3] if len(sys.argv) > 3 else None
    checks = {
        "mtree": lambda: check_mtree(captured, ref),
        "qtree": lambda: check_qtree(captured, ref),
        "roms": lambda: check_roms(captured),
        "log": lambda: check_log(captured, ref),
    }
    return checks[what]()


if __name__ == "__main__":
    sys.exit(main())
