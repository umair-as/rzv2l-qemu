# M7-rpc-spinor — tasks

Branches `unit/M7-rpc-spinor` (project and fork).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: registers, guest sequences, flash, conflicts | `docs/research/rpc.md` | — | done |
| T2 | Flash part `mt25qu512a` (6-byte ID, 64 MiB; SFDP per design choice 1) | fork `hw/block/m25p80.c` (+ `m25p80_sfdp.c`) | qtest RDID, SFDP | open |
| T3 | Controller model: registers, manual mode, external read mode with read cache, data byte-order rule, gates | fork `hw/ssi/renesas_rzv2l_rpc.c`, header, Kconfig, meson, trace | qtest `rzv2l-rpc-test` | open |
| T4 | SoC and board wiring: windows, SPI 41, CPG clock and reset, the flash with `-drive if=mtd` | fork `hw/arm/r9a07g054.c`, `hw/arm/rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` | `info qtree`, U-Boot `sf probe` | open |
| T5 | qtest: reset values, manual mode, data lanes, read window, cache, DREAR, gates; mutations | fork `tests/qtest/rzv2l-rpc-test.c` | each assertion red under a mutation | open |
| T6 | Acceptance: U-Boot (no JEDEC/timeout lines, `sf probe/read`), Linux (`mt25qu512a`, `/proc/mtd`, read matches, write survives reboot and restart); log gate | `tests/acceptance/m7/` | M7 ACCEPTANCE | open |
| T7 | Device map row, walkthrough step (`-drive if=mtd`), milestones | `docs/` | — | open |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
