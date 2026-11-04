# M7-rpc-spinor — tasks

Branches `unit/M7-rpc-spinor` (project and fork).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: registers, guest sequences, flash, conflicts | `docs/research/rpc.md` | — | done |
| T2 | Flash part `mt25qu512a` (6-byte ID, 64 MiB, the board's SFDP); Micron Quad I/O Fast Read defaults to 10 dummy cycles (the board's SFDP) | fork `hw/block/m25p80.c`, `m25p80_sfdp.c` | qtest RDID, SFDP, quad I/O read | done |
| T3 | Controller model: registers, manual mode, external read mode with read cache, data byte-order rule, gates | fork `hw/ssi/renesas_rzv2l_rpc.c`, header, Kconfig, meson, trace | qtest `rzv2l-rpc-test` | done |
| T4 | SoC and board wiring: windows, SPI 41, CPG clock and reset, the flash with `-drive if=mtd` | fork `hw/arm/r9a07g054.c`, `hw/arm/rzv2l-smarc.c`, `hw/misc/renesas_rzv2l_cpg.c`, `docs/system/arm/rzv2l-smarc.rst`; M1 expected `qtree`/`mtree` | M1 ACCEPTANCE, U-Boot `sf probe` | done |
| T5 | qtest: reset values, manual mode, data lanes, read window, cache, DREAR, gates; mutations | fork `tests/qtest/rzv2l-rpc-test.c` | each assertion red under a mutation | done |
| T6 | Acceptance: U-Boot (no JEDEC/timeout lines, `sf probe/read`, the NVCR rewrite), Linux (`mt25qu512a`, SFDP, `/proc/mtd`, read matches, write survives reboot and restart); log gate | `tests/acceptance/m7/flash.py`, `run.sh`, `expected/sfdp.txt` | M7 ACCEPTANCE | done |
| T7 | Device map row and gap 25, walkthrough step (`-drive if=mtd`), milestones | `docs/` | the walkthrough commands run | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `CMNCR_RESET` `0x01557301` → `0x01557300` | `test_reset_values: assertion failed (rd(qts, CMNCR) == 0x01557301): (0x01557300 == 0x01557301)` |
| 2 | `DRENR_WMASK` `0xf333dff0` → `0xf333fff0` (reserved bit 13 writable) | `test_rw_bits: assertion failed (rd(qts, t[i].reg) == t[i].ones): (0xf333fff0 == 0xf333dff0)` |
| 3 | received byte i at `<< (8 * (3 - i))` (byte 0 at the top) | `test_manual_read: assertion failed (rd(qts, SMRDR0) == 0x1020bb20): (0x20bb2010 == 0x1020bb20)` |
| 4 | a 1- or 2-byte SMWDR0 write stored as written, not in the top bytes | `test_manual_write: assertion failed (qtest_readl(qts, RPC_BUS + 0x14) == 0x88776655): (0x00006655 == 0x88776655)` |
| 5 | dummy bits `(dmcyc + 1) * lanes` → `(dmcyc + 2) * lanes` | `test_normal_read: assertion failed (qtest_readl(qts, RPC_BUS + PAT1 + 0x80) == pat32(PAT1 + 0x80)): (0x00000000 == 0x4722fdd8)` |
| 6 | DREAR.EAV at flash bit 24, not 25 | `test_normal_read: assertion failed (qtest_readl(qts, RPC_BUS + 0x10) == pat32(PAT2 + 0x10)): (0xffffffff == 0xbf9a7550)` |
| 7 | DRCR.RBE ignored (every read bypasses the cache) | `test_read_cache: assertion failed (qtest_readl(qts, RPC_BUS + 0x04) == 0xffffffff): (0x00000000 == 0xffffffff)` |
| 8 | DRCR.RCF does not flush | `test_read_cache: assertion failed (qtest_readl(qts, RPC_BUS + 0x04) == 0x00000000): (0xffffffff == 0x00000000)` |
| 9 | CMNSR.TEND always 1 | `test_ssle: assertion failed (rd(qts, CMNSR) == CMNSR_SSLF): (0x00000003 == 0x00000002)` |
| 10 | the clock gate ignored (`in_reset` only) | `test_gates: assertion failed (rd(qts, SMADR) == 0x12345678): (0x9abcdef0 == 0x12345678)` |
| 11 | m25p80: Micron default 10 dummy cycles in the Quad I/O protocol only (the old rule) | `test_normal_read: assertion failed (qtest_readl(qts, RPC_BUS + PAT1 + 0x100) == pat32(PAT1 + 0x100)): (0xecc7a27d == 0xc7a27d58)` |
| 12 | SFDP byte `0x32` `0xfb` → `0xfa` | `test_manual_read: assertion failed (rd(qts, SMRDR0) == 0xfffb20e5): (0xfffa20e5 == 0xfffb20e5)` |
| 13 | CPG `spi-clk` from CLK1_ON alone (`!!(on & 0x2)`) | `test_gates: assertion failed (rd(qts, SMADR) == 0x12345678): (0x9abcdef0 == 0x12345678)` |
| 14 | mt25qu512a JEDEC ID `0x20bb20` → `0x20ba20` | `test_manual_read: assertion failed (rd(qts, SMRDR0) == 0x1020bb20): (0x1020ba20 == 0x1020bb20)` |
| 15 | a manual write sends SMWDR0 from bit 0 (`>> (8 * i)`) | `flash.py`: `FAIL U-Boot: reads the non-volatile configuration register as FFFFh and writes 0000h (the factory FFFFh with bit 4 cleared)` |
