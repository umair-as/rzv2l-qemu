#!/usr/bin/env python3
"""M1 acceptance checks on captured QEMU output (M1-T06).

Usage: check.py mtree|qtree|roms|log|dtb <captured-file> [<expected-file>]
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


def dts_nodes(path):
    """Map node path -> property lines, from `dtc -I dtb -O dts -s` output.

    Assumes dtc prints each property on one line ending in ';' (true for
    DTB-U: every non-blank line is a node, a property or a '};').
    """
    nodes = {}
    stack = []
    for l in open(path):
        l = l.strip()
        m = re.match(r"(\S+) \{$", l)
        if m:
            name = m.group(1)
            stack.append("" if name == "/" else name)
            nodes["/".join(stack) or "/"] = []
        elif l == "};":
            stack.pop()
        elif l.endswith(";") and stack:
            nodes["/".join(stack) or "/"].append(l)
    return nodes


# QEMU's loader fixups on the REQ-GUEST-004 gap list (M1 spec AC08).
# /memory is rewritten from the board's binfo, /psci replaced outright;
# the replacement must keep the board's SMC conduit (AGENTS.md board facts)
# and the PSCI 1.0 binding Linux matches. QEMU's 0.1 function IDs are QEMU's
# own values, which Linux ignores; they are not checked.
DTB_FIXUP_NODES = ("/psci",)
DTB_PSCI_METHOD = 'method = "smc";'
DTB_PSCI_COMPAT = "arm,psci-1.0"
DTB_MEMORY = ("/memory@48000000",
              ['device_type = "memory";',
               "reg = <0x00 0x%x 0x00 0x%x>;"
               % (LINUX_MEM[0], LINUX_MEM[1] - LINUX_MEM[0])])


def check_dtb(captured, stock):
    """DTB QEMU passes on vs the stock DTB: only the listed fixups differ."""
    got, want = dts_nodes(captured), dts_nodes(stock)
    rc = 0
    for n in sorted(set(got) ^ set(want)):
        rc = fail("dtb: node %s %s" % (n, "added" if n in got else "removed"))
    path, props = DTB_MEMORY
    if got.get(path) != props:
        rc = fail("dtb: %s is %s, expected %s" % (path, got.get(path), props))
    if DTB_PSCI_METHOD not in got.get("/psci", []):
        rc = fail("dtb: /psci lacks '%s'" % DTB_PSCI_METHOD)
    compat = [l for l in got.get("/psci", []) if l.startswith("compatible = ")]
    if not compat or DTB_PSCI_COMPAT not in re.findall(
            r'([^"\\]+)(?:\\0|")', compat[0].split("=", 1)[1]):
        rc = fail("dtb: /psci compatible lacks '%s'" % DTB_PSCI_COMPAT)
    fixed = []
    for n in sorted(set(got) & set(want)):
        if got[n] == want[n]:
            continue
        if n in DTB_FIXUP_NODES:
            fixed.append(n)
        else:
            rc = fail("dtb: %s differs: -%s +%s"
                      % (n, sorted(set(want[n]) - set(got[n])),
                         sorted(set(got[n]) - set(want[n]))))
    if not rc:
        print("PASS dtb: %d nodes; %s as expected; only %s rewritten"
              % (len(got), path, ", ".join(fixed) or "nothing"))
    return rc


def main():
    what, captured = sys.argv[1], sys.argv[2]
    ref = sys.argv[3] if len(sys.argv) > 3 else None
    checks = {
        "mtree": lambda: check_mtree(captured, ref),
        "qtree": lambda: check_qtree(captured, ref),
        "roms": lambda: check_roms(captured),
        "log": lambda: check_log(captured, ref),
        "dtb": lambda: check_dtb(captured, ref),
    }
    return checks[what]()


if __name__ == "__main__":
    sys.exit(main())
