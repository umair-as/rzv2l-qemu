# SPDX-License-Identifier: GPL-2.0-or-later
"""Map and Devices tabs, and profile readiness, without QEMU.

The fixtures are `info mtree -f` and `info qtree` from rzv2l-smarc (M1 probe
profile, paused at start); the UNIMP case follows hw/misc/unimp.c, whose
region takes the device's "name" property.
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
MTREE = (FIX / "rzv2l-smarc-mtree.txt").read_text()
QTREE = (FIX / "rzv2l-smarc-qtree.txt").read_text()
WINDOWS, _ = server.load_device_map()


def by_base(rows):
    return {r["base"]: r for r in rows}


def test_flat_view_reads_the_memory_address_space_only():
    regions = server.parse_flat_mtree(MTREE)
    assert len(regions) == 9                    # the I/O FlatView is not memory
    sysc = [r for r in regions if r["name"] == "renesas-rzg2l-sysc"][0]
    assert (sysc["base"], sysc["end"], sysc["kind"]) == (0x11020000, 0x1102FFFF, "i/o")


def test_windows_against_the_live_map():
    rows, extra, unplaced = server.memory_map(WINDOWS, MTREE, QTREE, collections.Counter())
    w = by_base(rows)
    assert (w["0x1004b800"]["status"], w["0x1004b800"]["regions"]) == \
        ("modelled", ["renesas-rz-scifa"])                              # SCIF0
    assert w["0x11020000"]["status"] == "modelled"                     # SYSC
    assert w["0x40000000"]["status"] == "ram"                          # DDR
    # GIC-600 distributor: 128 KiB window, QEMU backs 64 KiB (device map §1.1)
    assert w["0x11900000"]["status"] == "modelled" and w["0x11900000"]["partial"]
    assert not w["0x11940000"]["partial"]                              # redistributors
    assert w["0x11980000"]["status"] == "missing"                      # GIC remainder
    assert w["0x1004b800"]["milestone"].startswith("M2")
    assert extra == [] and unplaced == []


UNIMP_MTREE = """FlatView #0
 AS "memory", root: system
 Root memory region: system
  0000000012800800-0000000012800bff (prio 0, i/o): wdt0
  0000000012900000-0000000012900fff (prio 0, i/o): mystery
"""
UNIMP_QTREE = """bus: main-system-bus
  type System
  dev: unimplemented-device, id ""
    size = 1024 (0x400)
    name = "wdt0"
    mmio 0000000012800800/0000000000000400
"""


def test_unimp_windows_hits_and_unlisted_regions():
    cov = collections.Counter({
        ("unimp", "write", "wdt0+0x14", "4", ""): 4,           # device offset
        ("invalid_mem", "read", "0x12800804", "4", "x"): 1,    # absolute address
    })
    rows, extra, _ = server.memory_map(WINDOWS, UNIMP_MTREE, UNIMP_QTREE, cov)
    wdt0 = by_base(rows)["0x12800800"]
    assert (wdt0["status"], wdt0["hits"]) == ("unimp", 5)
    assert extra == [{"name": "mystery", "base": "0x12900000", "size": "0x1000",
                      "kind": "i/o"}]


def test_device_tree():
    tree = server.parse_qtree(QTREE)
    assert [n["label"] for n in tree] == ["main-system-bus"]
    devs = tree[0]["children"]
    assert len(devs) == 8 and all(d["kind"] == "dev" for d in devs)
    sysc = [d for d in devs if d["label"].startswith("renesas-rzg2l-sysc")][0]
    assert "lsi-devid = 407139399 (0x18447447)" in sysc["props"]
    found = server.qtree_devices(tree)
    assert {"type": "renesas-rzg2l-sysc", "name": None,
            "mmio": [(0x11020000, 0x10000)]} in found


def test_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.delenv("BENCH_QEMU", raising=False)    # it replaces path QEMUs
    qemu = tmp_path / "qemu"
    qemu.write_text("#!/bin/sh\n")
    qemu.chmod(0o755)
    (tmp_path / "img").write_text("x")

    def p(args, prepare=(), q=str(qemu)):
        return server.profile_assets({"qemu": q, "args": args, "prepare": list(prepare)})

    assert p(["-kernel", "img"])["status"] == "ready"
    assert p(["-kernel", "gone"], prepare=["make"])["status"] == "builds"
    assert p(["-kernel", "gone"])["status"] == "missing"
    assert p(["-kernel", "img"], q=str(tmp_path / "no-qemu"))["status"] == "missing"
    qemu.chmod(0o644)                                   # present, not executable
    assert p(["-kernel", "img"])["status"] == "missing"


SPAN_MTREE = """FlatView #0
 AS "memory", root: system
 Root memory region: system
  0000000010000000-000000003efeffff (prio 0, i/o): gpex_mmio_window @0000000010000000
  0000000040000000-0000000047ffffff (prio 0, ram): mach-virt.ram
"""


def test_a_larger_region_only_covers_a_window():
    """virt's PCIe window lies across the RZ/V2L peripherals: "covered", not
    "modelled"; and it is listed, since no window holds it."""
    rows, extra, _ = server.memory_map(WINDOWS, SPAN_MTREE, "", collections.Counter())
    w = by_base(rows)
    assert (w["0x1004b800"]["status"], w["0x1004b800"]["regions"]) == \
        ("covered", ["gpex_mmio_window"])
    assert not w["0x1004b800"]["partial"]
    assert w["0x40000000"]["status"] == "ram" and w["0x40000000"]["partial"]
    assert [e["name"] for e in extra] == ["gpex_mmio_window"]


def test_hits_the_map_cannot_place_are_listed():
    """A device's own LOG_UNIMP line names a function and an offset (SYSC in
    the M1 probe): no address, so it is listed, never dropped."""
    cov = collections.Counter({
        ("unimp", "read", "rzg2l_sysc_read+0x0", "", ""): 1,
        ("invalid_mem", "read", "0x0c000000", "4", "rejected"): 2,
        ("other", "", "free text", "", ""): 3,
    })
    _, _, unplaced = server.memory_map(WINDOWS, MTREE, QTREE, cov)
    assert unplaced == [
        {"where": "0x0c000000", "why": "in no window", "count": 2},
        {"where": "rzg2l_sysc_read+0x0", "why": "no address in the log line", "count": 1},
    ]
