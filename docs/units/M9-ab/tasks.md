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
| 1 | (removed) slot B's `/etc/m9-slot` naming the wrong slot: the check went with M9-update-failure, whose payload does not name its slot; proofs 5 and 6 cover the two identity checks that remain | — |
| 2 | no `/sbin/m9-health` in slot B (selection case) | `FAIL selection: in order: M9-HEALTH: slot B committed, …`; the card keeps `BOOT_B_LEFT=2` |
| 3 | the bad update without `M9_PENDING` | `FAIL bad update, new QEMU: in order: M9-HEALTH: rollback: slot B gave up, slot A runs`; no `M9_ROLLBACK` on the card |
| 4 | copy 2 damaged, checked as the copy-1 case | `FAIL proof 4: in order: Reading from redundant MMC(0)... OK` |

| 5 | slot B's health service expects the swapped partitions (A: 3, B: 2) | `FAIL selection: in order: M9-HEALTH: slot B committed, …`; the service printed `U-Boot booted slot B (partition 2), but / is partition 3` |
| 6 | slot B's health service reads a command line naming `root=PARTUUID=525a0003-02` | `FAIL selection: in order: M9-HEALTH: slot B committed, …`; the service printed `the kernel's root=PARTUUID=525a0003-02 is not / (525a0003-03); not committed; rebooting` |

| 7 | `fit.py`'s accepted-state check on a card whose two copies both hold `BOOT_A_LEFT=2` (no commit), then on one whose two copies both hold the commit (no saved attempt) | `FAIL accepted: active copy BOOT_A_LEFT=3, M9_GOOD=A (Linux's commit); the copy before it BOOT_A_LEFT=2 (U-Boot's saved attempt)` for each; the accepted run's own card passes |

Proof 7 runs the check on prepared cards, without a boot. The check picks the copy U-Boot would use (the valid one with the higher flag, 0 after 255) before asserting. Before the second review it searched for any copy with `BOOT_A_LEFT=2`, which after Linux's commit matched the older copy.

| 8 | the both-damaged case on a U-Boot whose built-in default boot command still runs the policy (the behaviour before the operator's decision) | `FAIL damaged copy 1+2: in order: M9: no valid environment copy on the card, so no slot state: not booting`; `FAIL … no attempt saved, no kernel` (slot A booted from fresh counters) |

Proofs 5 and 6 change the service under test on a copy of the card. That is the only way to drive these checks: U-Boot sets the partition and the command line together.
Each break is made on a copy of the card; the outputs are kept in the working area's proof log.

## Boot evidence (fork `176d418966`)

`tests/acceptance/m9/ab.py`: 65 checks pass (after the review fixes); `fit.py` passes again on the card with the health service. The bad update's second QEMU printed `M9-HEALTH: slot B: health check 90-fail failed; not committed; rebooting`, then `M9-HEALTH: slot A committed, / is 525a0003-02: BOOT_A_LEFT 3;M9_GOOD A;M9_ROLLBACK B;M9_PENDING;BOOT_ORDER A B;` and `M9-HEALTH: rollback: slot B gave up, slot A runs`. With both copies damaged, U-Boot printed `Loading Environment from MMC... *** Warning - bad CRC, using default environment`, then `M9: slot A: attempt saved: BOOT_A_LEFT=2 BOOT_B_LEFT=3`, and booted the signed FIT.
