# M8-ddr-stub — tasks

Branches `unit/M8-ddr-stub` (project from `main` `f5c1fd1`, fork from `rzv2l-dev` `1b027a1b95`).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: the DDR contract checked against TF-A and its build: supported offsets from reads and writes, triggers, completions, acknowledgements, refusals | `docs/research/bl2.md` §6 | — | done |
| T2 | The stub device: two windows, the stored registers, the computed behaviours, the refusals; trace points for the triggers and acknowledgements | fork `hw/misc/renesas_rzv2l_ddr.c`, header, Kconfig, meson, trace-events | qtest `rzv2l-ddr-test` | open |
| T3 | SoC: the device in place of the `ddr-memc` stub and the unmapped PHY; M1 expected `qtree`/`mtree`; the log allow-lists | fork `hw/arm/r9a07g054.c`; `tests/acceptance/` | M1, M7 acceptance | open |
| T4 | qtest: stub-contract tests per behaviour; mutations (completion missing, acknowledgement broken, storage lost, each computed bit, write leveling leaving `0x14C`, the `0x170` mirror lost on a read-modify-write) | fork `tests/qtest/rzv2l-ddr-test.c` | each assertion red under a mutation | open |
| T5a | QSPI read path as BL2 uses it: `0xEB` 1-4-4, `DRDMCR` 9, 32-line bursts across several bursts | fork `tests/qtest/rzv2l-rpc-test.c` | qtest, red under a mutation | open |
| T5 | Acceptance: BL2 through DDR to `Booting BL31` | `tests/acceptance/m8/bl2.py` | M8 ACCEPTANCE | open |
| T6 | Device map row and gap, walkthrough step, milestones | `docs/` | lint | open |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
