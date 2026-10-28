# SPDX-License-Identifier: GPL-2.0-or-later
"""The coverage list must count every -d log line, in the right row.

The lines are the formats QEMU prints (qemu v11.1.2): system/memory.c,
system/physmem.c, hw/misc/unimp.c, and a device's own LOG_UNIMP message.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import classify  # noqa: E402

CASES = [
    ("Invalid read at addr 0x10000000, size 4, region '(null)', reason: rejected",
     ("invalid_mem", "read", "0x10000000", "4", "rejected")),
    ("Invalid write at addr 0x11020A01, size 1, region 'sysc', reason: invalid size (min:4 max:4)",
     ("invalid_mem", "write", "0x11020a01", "1", "invalid size (min:4 max:4)")),
    ("Invalid read at addr 0x11020A02, size 4, region 'sysc', reason: unaligned",
     ("invalid_mem", "read", "0x11020a02", "4", "unaligned")),
    ("Invalid access to non-RAM device at addr 0x12000000, size 64, region 'scif0'",
     ("invalid_mem", "access", "0x12000000", "64", "scif0")),
    ("gpio: unimplemented device read  (size 4, offset 0x0010)",
     ("unimp", "read", "gpio+0x10", "4", "")),
    ("gpio: unimplemented device write (size 2, offset 0x0024, value 0x0001)",
     ("unimp", "write", "gpio+0x24", "2", "")),
    ("rzg2l_sysc_read: unimplemented read at offset 0x0",
     ("unimp", "read", "rzg2l_sysc_read+0x0", "", "")),
    ("arm_gicv3: guest wrote a reserved bit",
     ("other", "", "arm_gicv3: guest wrote a reserved bit", "", "")),
]


def test_every_form_lands_in_its_row():
    for line, want in CASES:
        assert classify(line) == want, line


def test_no_line_is_dropped():
    # classify always returns a row; unknown text is kept verbatim
    assert all(classify(line) is not None for line, _ in CASES)
    assert classify("anything at all")[0] == "other"
