# M9-ab — spec

**Milestone:** M9 (platform behaviour; second unit). **Requirements:** REQ-BOOT-003 to REQ-BOOT-006 (proposed here). Statuses change at release closure. **Status:** implemented.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The slot state and the contracts are [DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md) decisions 5-7 and 9; U-Boot's half of decision 6 is M9-fit's. U-Boot paths are at `renesas-u-boot-cip` `4eebfbaa4e` with the M9 profile's patch.

## Scope

**No new block, and no QEMU change expected.** This unit adds Linux's half of the policy to the M9 card, and checks slot selection, commit, rollback and damaged environment copies on the chain from the QSPI flash.

- **`fw_printenv` / `fw_setenv`** from the M9 U-Boot source (`tools/env`, the `envtools` target), linked statically for the BusyBox root. They read and write the two copies as U-Boot does. The redundant format writes the copy that is not in use and gives it the next flag value. The configuration file names the card's whole device and both offsets. It is written at boot from the root partition's parent device, so the name Linux gives the card does not matter. The vendor device tree has no `mmc` aliases, so Linux numbers the two SD hosts in probe order and calls the card `mmcblk0` or `mmcblk1` (device map gap 22). Both names occurred in the acceptance runs, and the commit worked under each (O).
- **The health service** `/sbin/m9-health`, run last by each slot's `rcS` (DR-0008 decision 7):
  1. Read `m9_slot`, the slot U-Boot saved before it booted (M9-fit's boot command saves the environment after setting it).
  2. Check that `/` is that slot's partition (2 for A, 3 for B), that the PARTUUID of `/` is the one the kernel was given (`root=PARTUUID=` in `/proc/cmdline`). A root does not name its own slot, so one update image fits either slot (M9-update-failure).
  3. Run each check in `/etc/m9-health.d/`. The card's checks are that the root is writable and that `/proc` and `/sys` are mounted.
  4. If everything passes, write in one `fw_setenv -s` call: `BOOT_<slot>_LEFT=3`, `M9_GOOD=<slot>`, and, if `M9_PENDING` names this slot, `M9_PENDING` cleared (the update is committed). If `M9_PENDING` names the other slot and that slot's counter is 0, also `M9_ROLLBACK=<other>`, `M9_PENDING` cleared and `BOOT_ORDER=<slot> <other>`.
  5. If anything fails, print what failed, write nothing, and run `reboot`.

  It prints one `M9-HEALTH:` line for each result.
- **Pending state in the tests.** M9-update-failure adds the Linux updater. Here, the test harness sets a pending update directly in both copies before QEMU starts (`uboot-env.py m9-write`): `M9_PENDING=B`, `BOOT_ORDER=B A`, `BOOT_B_LEFT=3`. That is the state the updater will write (DR-0008 decision 8). A "bad" slot is slot B with one more health check that fails (`/etc/m9-health.d/90-fail`), written into a copy of the card with `debugfs`.
- **Damaged copies.** U-Boot uses the valid copy with the higher flag. If one copy's CRC fails, it uses the other one and prints no warning (`env_check_redund`, `env/common.c:447-493`; `env_import_redund`, `:494-519`). It names the second copy only in `Reading from redundant MMC(0)` (`env/mmc.c:439`). If both fail, it prints `*** Warning - bad CRC, using default environment` (`env/common.c:376-377`, `:508`) and uses its built-in default: the M9 policy. The next `saveenv` writes the copy that is not in use, which repairs a single bad copy (`env/mmc.c:277-302`; the damaged-copy cases show both copies valid afterwards).
- **Recorded consequences (DR-0008 decision 9):**
  - If both copies are lost, U-Boot warns, prints that it has no slot state and stops at its prompt. It boots no slot and saves nothing (operator's decision after the v2.0 release; before it, slot A booted from fresh counters).
  - `M9_ROLLBACK` stays set until the next update. The update tool clears it (M9-update-failure).
- **Not in this unit:** the update tool and interruptions (M9-update-failure), dm-verity, anti-rollback.

## What the guest needs

U-Boot: M9-fit's boot command, unchanged. Linux: the Renesas kernel exposes the whole card as `/dev/mmcblkN` and lets root write it, so `fw_setenv` can write both copies at `0x1F0000` and `0x210000` (I: the kernel's block layer; checked by the commit test). BusyBox: `sh`, `od`, `sed`, `reboot`.

## Exit criterion

New acceptance script `tests/acceptance/m9/ab.py`, on the chain from the QSPI flash as `fit.py`, with a fresh copy of the M9 card per case:

1. **Selection:** with `BOOT_ORDER=B A`, U-Boot saves B's attempt and boots slot B. `/` is partition 3 (PARTUUID `525a0003-03`). The health service commits B, and the card then holds `BOOT_B_LEFT=3` and `M9_GOOD=B`.
2. **A good update commits:** pending B, healthy. B boots, and the service commits it (`M9_PENDING` cleared, `M9_GOOD=B`). A second, fresh QEMU process on the same card boots B again.
3. **A bad update rolls back:** pending B, with B's health failing. B boots three times, and each time the service refuses the commit and reboots. U-Boot then boots A. The service commits A and records `M9_ROLLBACK=B`, `BOOT_ORDER=A B`, `M9_PENDING` cleared. In the middle, QEMU is stopped after one of B's attempts is saved, and a fresh QEMU continues on the same card from the saved counter.
4. **Both slots exhausted:** both slots' health failing. After three attempts each, U-Boot stops at the prompt: `M9: no slot has an attempt left: BOOT_ORDER=A B BOOT_A_LEFT=0 BOOT_B_LEFT=0`. No counter is replenished.
5. **Damaged copies:**
   - copy 1 damaged: U-Boot reads the other one (`Reading from redundant MMC(0)`) and boots A, and both copies are valid afterwards;
   - copy 2 damaged: U-Boot boots A, and both copies are valid afterwards;
   - both damaged: U-Boot prints the bad-CRC warning, then `M9: no valid environment copy on the card, so no slot state: not booting`, and stops at its prompt. No attempt is saved, no kernel starts, and both copies stay invalid. The vendor's unsigned boot command never runs.

   In each case the test first reads the card and asserts that exactly the damaged copies are invalid. U-Boot prints the same lines for a damaged copy 2 as for an undamaged card, so only that pre-boot check shows the case is real.
6. M9-fit's checks and M8's acceptance run unchanged. Each run directory keeps the hashes and records as in M9-fit.

## Evidence

DR-0008; the M9-fit unit page; U-Boot `env/common.c`, `env/mmc.c`, `tools/env/fw_env.c` at the pinned commit.

## Next blocker (fork `176d418966`)

None for this unit, and no model change. Two facts from the runs: `fw_printenv` needs `/run` for its lock file (`Error opening lock file /run/fw_printenv.lock` until each slot mounted a tmpfs there), and the single-copy repair (I above) holds: both copies are valid after each damaged-copy boot. Next: M9-update-failure (the update tool in Linux, and interruptions during the payload write, before the selection is saved, and during the environment write).
