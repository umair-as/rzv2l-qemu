# SPDX-License-Identifier: GPL-2.0-or-later
"""Coverage export: addresses grouped by docs/device-map.md window.

Expected windows are read off the device map by hand (section 1 tables)."""

import collections
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

WINDOWS, WARNINGS = server.load_device_map()

CASES = [
    (0x1004B800, ("SCIF0", 0x1004B800, 0x400)),
    (0x1004BBFF, ("SCIF0", 0x1004B800, 0x400)),        # last byte
    (0x1004BC00, ("SCIF1", 0x1004BC00, 0x400)),        # next window
    (0x11020A04, ("SYSC", 0x11020000, 0x10000)),
    (0x12801400, ("OSTM0-2", 0x12801400, 0x400)),
    (0x10058C10, ("RIIC3", 0x10058C00, 0x400)),        # "+ n×`0x400`" row
    (0x11990000, ("GIC area remainder", 0x11980000, 0x80000)),
    (0x48000000, ("DDR", 0x40000000, 0x80000000)),
    (0x0C000000, None),
    (0x11960000 + 0x20000 + 0x80000, None),            # past the GIC area
]


def test_addresses_land_in_their_window():
    for addr, want in CASES:
        w = server.find_window(WINDOWS, addr)
        got = (w["name"], w["base"], w["size"]) if w else None
        assert got == want, hex(addr)


def test_unpaired_rows_are_reported():
    # Rows whose sizes do not pair with their bases are named, not hidden
    assert any(w.startswith("DMAC secure") for w in WARNINGS)


def test_csv_groups_by_window():
    cov = collections.Counter({
        ("invalid_mem", "read", "0x1004b804", "4", "rejected"): 2,
        ("invalid_mem", "read", "0x1004b808", "2", "rejected"): 3,
        ("invalid_mem", "write", "0x1004b808", "2", "rejected"): 1,
        ("invalid_mem", "read", "0x0c000000", "4", "rejected"): 1,
        ("unimp", "write", "wdt0+0x14", "4", ""): 4,
        ("other", "", "arm_gicv3: something", "", ""): 2,
    })
    rows = list(csv.reader(io.StringIO(server.coverage_csv(cov, WINDOWS))))
    assert rows[0] == ["name", "base", "size", "kind", "access", "count"]
    assert sorted(rows[1:]) == sorted([
        ["SCIF0", "0x1004b800", "0x400", "invalid_mem", "read", "5"],
        ["SCIF0", "0x1004b800", "0x400", "invalid_mem", "write", "1"],
        ["unmapped", "0x0c000000", "4", "invalid_mem", "read", "1"],
        ["wdt0", "", "", "unimp", "write", "4"],
        ["other", "", "", "other", "", "2"],
    ])
