# M9-ab — tasks

Project branch `unit/M9-ab` from `unit/M9-fit` `2b2d791`. No fork branch: no QEMU change expected (fork `rzv2l-dev` `176d418966`).

| ID | Task | Test | Status |
|---|---|---|---|
| T1 | `fw_printenv`/`fw_setenv` from the M9 source, static (`build-u-boot-m9.sh`) | build check | done |
| T2 | `/sbin/m9-health` and `/etc/m9-health.d/` in both slots (`build-image-m9.sh`) | `ab.py` | done |
| T3 | `m9/ab.py`: selection, good update, bad update with a restart, both exhausted, damaged copies | `ab.py` | done |
| T4 | `m9/run.sh` step; milestones, walkthrough; Next blocker | M9 acceptance | done |

## Proofs (each break: the exact change → the red line)

| # | Break | Red line |
|---|---|---|
| 1 | slot B's `/etc/m9-slot` says `A` (selection case) | `FAIL selection: in order: M9-HEALTH: slot B committed, / is 525a0003-03`; the service printed `/etc/m9-slot names A, U-Boot booted B; not committed; rebooting`, and the card ends with `BOOT_B_LEFT=0`, `M9_GOOD=A` |
| 2 | no `/sbin/m9-health` in slot B (selection case) | `FAIL selection: in order: M9-HEALTH: slot B committed, …`; the card keeps `BOOT_B_LEFT=2` |
| 3 | the bad update without `M9_PENDING` | `FAIL bad update, new QEMU: in order: M9-HEALTH: rollback: slot B gave up, slot A runs`; no `M9_ROLLBACK` on the card |
| 4 | copy 2 damaged, checked as the copy-1 case | `FAIL proof 4: in order: Reading from redundant MMC(0)... OK` |

Each break is made on a copy of the card; the outputs are kept in the working area's proof log.

## Boot evidence (fork `176d418966`)

`tests/acceptance/m9/ab.py`: 61 checks pass; `fit.py` passes again on the card with the health service. The bad update's second QEMU printed `M9-HEALTH: slot B: health check 90-fail failed; not committed; rebooting`, then `M9-HEALTH: slot A committed, / is 525a0003-02: BOOT_A_LEFT 3;M9_GOOD A;M9_ROLLBACK B;M9_PENDING;BOOT_ORDER A B;` and `M9-HEALTH: rollback: slot B gave up, slot A runs`. With both copies damaged, U-Boot printed `Loading Environment from MMC... *** Warning - bad CRC, using default environment`, then `M9: slot A: attempt saved: BOOT_A_LEFT=2 BOOT_B_LEFT=3`, and booted the signed FIT.
