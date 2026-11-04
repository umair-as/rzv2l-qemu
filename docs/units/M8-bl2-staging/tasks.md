# M8-bl2-staging — tasks

Branches `unit/M8-bl2-staging` (project from `main` `7e704a8`, fork from `rzv2l-dev` `fe92a06227`).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: the boot ROM, the image layout, BL2's accesses, the DDR block | `docs/research/bl2.md` | — | done |
| T2 | BL2 and `fiptool` builds; the SPI flash image (boot parameter block, BL2, FIP) | `tests/guests/fw/build-tf-a.sh`, `build-spi-image.sh` | header (size `0xE924`, `0x200`, `0x12000`, `55 AA`), FIP header `0xAA640001` at `0x20000`, `fiptool info`; BL31 unchanged; the image reproducible | done |
| T3 | CPG: PLL4, PLL6 (standby, clock settings, monitors) and the SRC clock and reset registers; both start states | fork `hw/misc/renesas_rzv2l_cpg.c` (`23a5f8dcbf`) | qtest `rzv2l-cpg-test` `/cpg/reset-values`, `/cpg/pll`, `/cpg/src` | done |
| T4 | SYSC: master and slave access-control registers, Secure only; both start states | fork `hw/misc/renesas_rzg2l_sysc.c` (`d4bedd2d32`); M1 probe comment and log allow-list | qtest `rzv2l-smarc-test` `/sysc/access-control`; M1 probe (Non-secure read aborts) | done |
| T5 | Boot-ROM stand-in: boot modes 3 and 4 without `-bios`/`-kernel`: size block, copy to `0x12000`, core 0 at EL3; errors | fork `hw/arm/rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` (`74752923ce`) | acceptance `tests/acceptance/m8/bl2.py` | done |
| T6 | Acceptance: BL2's banner, the stop at the first DDR access, the stand-in's errors; M7 unchanged; log gate | `tests/acceptance/m8/run.sh`, `bl2.py`, `expected/log-allow.txt` | M8 ACCEPTANCE | done |
| T7 | Device map rows and gap 9 (the access-control registers were not stored), research corrections (`boot-chain-firmware.md`: the BL33 EL file), walkthrough step, milestones | `docs/` | lint; the walkthrough step run | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `SAMPLL4_STBY` reset `0x4` → `0x5` | `rzv2l-cpg-test.c:243:check_values: assertion failed (got == v[i].value): (0x00000005 == 0x00000004)` |
| 2 | `SAMPLL4_STBY` a plain register (no write enables) | `rzv2l-cpg-test.c:306:test_pll: assertion failed (cpg_read(qts, SAMPLL4_STBY) == 0x00000004): (0x00000001 == 0x00000004)` |
| 3 | the PLL monitor without `LOCK` | `rzv2l-cpg-test.c:311:test_pll: assertion failed (cpg_read(qts, SAMPLL4_MON) == 0x00000011): (0x00000001 == 0x00000011)` |
| 4 | `SAMPLL4_CLK2` all bits writable | `rzv2l-cpg-test.c:323:test_pll: assertion failed (cpg_read(qts, SAMPLL4_CLK2) == 0x00ff3f07): (0xffffffff == 0x00ff3f07)` |
| 5 | the direct-mode overlay leaves PLL4 in standby (`0x4`) | `rzv2l-cpg-test.c:330:test_pll: assertion failed (cpg_read(qts, SAMPLL4_STBY) == 0x00000005): (0x00000004 == 0x00000005)` |
| 6 | `RST_SRC` reset `0x1` (reset released) | `rzv2l-cpg-test.c:243:check_values: assertion failed (got == v[i].value): (0x00000001 == 0x00000000)` |
| 7 | `CLKON_SRC` with no writable bit | `rzv2l-cpg-test.c:346:test_src: assertion failed (cpg_read(qts, CLKON_SRC + MON) == 0x1): (0x00000000 == 0x00000001)` |
| 8 | `SYS_MSTACCCTL0` reset `0x00aaaa00` → `0x00aaaa0a` | `rzv2l-smarc-test.c:170:test_sysc_accctl: assertion failed (qtest_readl(qts, SYSC_BASE + r[i].offset) == r[i].reset): (0x00aaaa0a == 0x00aaaa00)` |
| 9 | access-control writes dropped | `rzv2l-smarc-test.c:175:test_sysc_accctl: assertion failed (qtest_readl(qts, SYSC_BASE + 0x118) == 0x00000008): (0x00000000 == 0x00000008)` |
| 10 | the Non-secure read check removed | M1 probe: `FAIL SYSC offset 0x0: read completed without an abort` |
| 11 | the ROM stand-in copies BL2 to `0x12100` | `bl2.py`: `FAIL boot: BL2 banner line 1 on SCIF0`, `FAIL boot: BL2 stops at its first DDR access (none)` |
| 12 | the signature check removed | `bl2.py`: `FAIL errors: no loader signature: QEMU stops (exit None) with "no loader on the QSPI flash (signature ff ff at 0x1fe"` |
