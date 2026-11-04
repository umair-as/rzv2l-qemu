# M8-ddr-stub — tasks

Branches `unit/M8-ddr-stub` (project from `main` `f5c1fd1`, fork from `rzv2l-dev` `1b027a1b95`).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: the DDR contract checked against TF-A and its build: supported offsets from reads and writes, triggers, completions, acknowledgements, refusals | `docs/research/bl2.md` §6 | — | done |
| T2 | The stub device: two windows, the stored registers, the computed behaviours, the refusals; trace points for the triggers and acknowledgements | fork `hw/misc/renesas_rzv2l_ddr.c`, header, Kconfig, meson, trace-events | qtest `rzv2l-ddr-test` | done |
| T3 | SoC: the device in place of the `ddr-memc` stub and the unmapped PHY; M1 expected `qtree`/`mtree`; the log allow-lists | fork `hw/arm/r9a07g054.c`, `docs/system/arm/rzv2l-smarc.rst`; `tests/acceptance/` | M1, M7 acceptance | done |
| T4 | qtest: stub-contract tests per behaviour; mutations (completion missing, acknowledgement broken, storage lost, each computed bit, write leveling leaving `0x14C`, the `0x170` mirror lost on a read-modify-write); the guest probe's aborts: a controller hole, past the last register, a PHY offset outside the set, a 16-bit read, an unknown training and low-power command, and an ignored status write that does not abort | fork `tests/qtest/rzv2l-ddr-test.c`; `tests/probes/m1-skeleton/` | each assertion red under a mutation | done |
| T5a | QSPI read path as BL2 uses it: `0xEB` 1-4-4, `DRDMCR` 9, 32-line bursts across several bursts | fork `tests/qtest/rzv2l-rpc-test.c` | qtest, red under a mutation | done |
| T5 | Acceptance: BL2 through DDR to `Booting BL31` | `tests/acceptance/m8/bl2.py` | M8 ACCEPTANCE | done |
| T6 | Device map row and gap 26, walkthrough step, milestones | `docs/` | lint | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | controller START sets nothing (`init_done = false`) | `rzv2l-ddr-test.c:145:test_init_done: (mc_read(qts, MC_ST_INIT) == MC_INIT_DONE): (0x00000000 == 0x02000000)` |
| 2 | the init-done acknowledgement (`0x280` bit 25) clears nothing | `:151:test_init_done: (mc_read(qts, MC_ST_INIT) == 0): (0x02000000 == 0x00000000)` |
| 3 | rewriting START = 1 counts as a new start | `:155:test_init_done: (mc_read(qts, MC_ST_INIT) == 0): (0x02000000 == 0x00000000)` |
| 4 | START = 0 leaves init-done set | `:162:test_init_done: (mc_read(qts, MC_ST_INIT) == 0): (0x02000000 == 0x00000000)` |
| 5 | a mode-register request sets nothing | `:174:test_mode_register: (mc_read(qts, MC_ST_MODE) == MC_MRW_DONE): (0x00000000 == 0x00000008)` |
| 6 | the mode-register acknowledgement (`0x284` bit 3) clears nothing | `:178:test_mode_register: (mc_read(qts, MC_ST_MODE) == 0): (0x00000008 == 0x00000000)` |
| 7 | controller storage keeps 16 bits | `:102:test_storage: (mc_read(qts, 0x004) == 0xa5a5f00f): (0x0000f00f == 0xa5a5f00f)` |
| 8 | PHY storage lost | `:107:test_storage: (phy_read(qts, 0x058) == 0x0badcafe): (0x00000000 == 0x0badcafe)` |
| 9 | reset leaves the controller registers | `:112:test_storage: (mc_read(qts, 0x004) == 0): (0xa5a5f00f == 0x00000000)` |
| 10 | `ECC_ENABLE` bits 11:0 not computed | `:78:test_reset: (mc_read(qts, MC_ECC_ENABLE) == 0x00000fff): (0x00000000 == 0x00000fff)` |
| 11 | `LP_CMD` 0x11 gives `LP_STATE` 0x40 | `:191:test_low_power: (mc_read(qts, MC_LP_STATE) == 0xc8000005): (0xc0000005 == 0xc8000005)` |
| 12 | `LP_CMD` 0x02 gives 0x48 | `:196:test_low_power: (mc_read(qts, MC_LP_STATE) == 0xc0000005): (0xc8000005 == 0xc0000005)` |
| 13 | `LP_STATE` ORed over stored bits 30:24 | `:200:test_low_power: (mc_read(qts, MC_LP_STATE) == 0x40000000): (0x7f000000 == 0x40000000)` |
| 14 | `0x24C` bits 31:16 stored | `:209:test_low_power: (mc_read(qts, MC_ST_LOWPOWER) == 0x0000ffff): (0xffffffff == 0x0000ffff)` |
| 15 | an unknown `LP_CMD` stored | `:204:test_low_power: (mc_read(qts, MC_LP_CMD) == 0x00000200): (0x00000500 == 0x00000200)` |
| 16 | a write to `0x260` sets init-done | `:220:test_read_only: (mc_read(qts, MC_ST_INIT) == 0): (0x02000000 == 0x00000000)` |
| 17 | the low-power and BIST acknowledgements stored | `:230:test_read_only: (mc_read(qts, MC_ACK_LOWPOWER) == 0): (0xffffffff == 0x00000000)` |
| 18 | the init-done acknowledgement stored | `:150:test_init_done: (mc_read(qts, MC_ACK_INIT) == 0): (0x02000000 == 0x00000000)` |
| 19 | `SCL_START` busy (bit 28) stays set | `:255:test_training: (phy_read(qts, PHY_SCL_START) == 0x20800003): (0x30800003 == 0x20800003)` |
| 20 | `SCL_START` bits 1:0 not computed | `:81:test_reset: (phy_read(qts, PHY_SCL_START) == 0x00000003): (0x00000000 == 0x00000003)` |
| 21 | write leveling leaves `0x14C` | `:259:test_training: (phy_read(qts, PHY_WRLVL_TRIM) == 0xfffffffc): (0xffffffff == 0xfffffffc)` |
| 22 | an unknown training command stored | `:275:test_training: (phy_read(qts, PHY_SCL_START) == 0x00000007): (0x40200003 == 0x00000007)` |
| 23 | `0x148`/`0x160` read 1 | `:82:test_reset: (phy_read(qts, PHY_WRLVL_CTRL) == 0x00000003): (0x00000001 == 0x00000003)` |
| 24 | a write to `0x1D4` stored | `:238:test_read_only: (phy_read(qts, PHY_VREF_WINDOWS) == 0): (0xffffffff == 0x00000000)` |
| 25 | `0x170` stores its computed bits 3:2 (mirror lost on a read-modify-write) | `:293:test_io_calibration: (phy_read(qts, PHY_IO_1) == 0x00000100): (0x0000010c == 0x00000100)` |
| 26 | `0x170` bits 3:2 not computed | `:287:test_io_calibration: (phy_read(qts, PHY_IO_1) == 0x00000005): (0x00000001 == 0x00000005)` |
| 27 | controller hole `0x070` supported | probe: `FAIL DDR controller hole 0x070: access completed without an abort` |
| 28 | last controller register `0x7FC` | probe: `FAIL DDR controller 0x7fc: access completed without an abort` |
| 29 | PHY `0x000` supported | probe: `FAIL DDR PHY 0x000: access completed without an abort` |
| 30 | 16-bit accesses accepted | probe: `FAIL DDR controller 16-bit read: access completed without an abort` |
| 31 | an unknown training command completes (`MEMTX_OK`) | probe: `FAIL DDR PHY unknown training command: access completed without an abort` |
| 32 | an unknown `LP_CMD` completes | probe: `FAIL DDR controller unknown low-power command: access completed without an abort` |
| 33 | a write to PHY `0x148` is a bus error | probe: `FAIL DDR PHY status write ignored ESR: 0x0000000096000250 (expected 0x0000000000000000)` |
| 34 | read cache bursts capped at 16 lines (`MIN(RBURST + 1, 16)`) | `rzv2l-rpc-test.c:534:test_bl2_read: (qtest_readb(qts, RPC_BUS + HASH_BASE + 0x10f8) == hash(HASH_BASE + 0x10f8)): (0x00000000 == 0x00000011)`; `read-cache` (2-line bursts) green under the same change |
| 35 | BL2's last SL training command (`0x34200000`) refused | `:264:test_training: (phy_read(qts, PHY_SCL_START) == (commands[i] & ~(1u << 28)) \| 3): (0x01200003 == 0x24200003)` |
| 36 | a system reset keeps init-done, mode-register done and `LP_STATE` | `:131:test_reset_state: (mc_read(qts, MC_ST_INIT) == 0): (0x02000000 == 0x00000000)` |
