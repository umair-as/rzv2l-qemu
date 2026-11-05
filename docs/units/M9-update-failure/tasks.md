# M9-update-failure — tasks

Project branch `unit/M9-update-failure` from `main` `3deacd1`. No fork branch: no QEMU change expected (fork `rzv2l-dev` `176d418966`).

| ID | Task | Test | Status |
|---|---|---|---|
| T1 | Slot-independent roots (`/etc/m9-version`; slot from the partition in `rcS` and `m9-health`); the version-2 payload and the update card (`build-image-m9.sh`) | build | done |
| T2 | `/sbin/m9-update`: protect the active slot, mark the target unbootable, write, verify by read-back, select in one `fw_setenv` | `update.py` success, refused | done |
| T3 | `m9/update.py`: success, refused payload, interrupted while writing (with retry), after verifying, while saving the selection (three delays) | `update.py` | done |
| T4 | `m9/run.sh` step and log gate; M9-ab docs without the `/etc/m9-slot` check; requirements REQ-BOOT-007/008 | M9 acceptance | done |
| T5 | Milestones, walkthrough; Next blocker | — | done |

## Proofs (each break: the exact change → the red line)

| # | Break | Red line |
|---|---|---|
| 1 | the tool's marking step sets only `M9_ROLLBACK` (slot B stays bootable); stopped while writing | `FAIL P1: the stopped card holds BOOT_B_LEFT=0, nothing pending ({… 'BOOT_B_LEFT': '3' …})` |
| 2 | the tool's verification always passes; refused payload | `FAIL refused payload: in order: M9-UPDATE: stopped: …`; `FAIL refused payload: no selection saved`. The bad slot was selected, and U-Boot's hash check then refused its kernel three times (`Bad hash value for 'hash-1' hash node in 'kernel' image node`) before slot A took over: the signed FIT is a second line of defence |
| 3 | `old_or_new` on two mixed states (pending B with `BOOT_ORDER=A B`; `BOOT_B_LEFT=0` with `BOOT_ORDER=B A`), offline | `FAIL P3 mixed: the active copy is the whole old or the whole new state` for each |
| 4 | the tool takes slot A's own partition as the target | `FAIL success: in order: M9-UPDATE: marking slot B not bootable`; the tool printed `M9-UPDATE: stopped: the target /dev/mmcblk1p2 is /` |

Proofs 1, 2 and 4 replace `/sbin/m9-update` in slot A of a card copy (`debugfs`); proof 3 runs the check on prepared states. The outputs are kept in the working area.

## Boot evidence (fork `176d418966`)

`tests/acceptance/m9/run.sh`, the cumulative run, at `1366472` (the review fixes): M1 to M8 (`M8 ACCEPTANCE: PASS`, `M7 ACCEPTANCE: PASS` inside), `fit.py` and `ab.py` passed. `update.py` stopped at its `interrupted-write` case: its run directory's serial socket path was 108 bytes, past the Unix limit (`sun_path`), because `run.sh` passes an absolute output directory. M7's start helper now moves a too-long socket path to a short temporary directory. With that fix, `update.py` alone, with the same absolute output directory, passes 97 checks. The log gate finds no unlisted line in all 35 M9 run logs. The other suites were not rerun: the fix applies only to socket paths over 100 bytes.

- The successful update printed `M9-UPDATE: slot B verified 1b8cd21a…295f`. With QEMU stopped right after the tool, the image file held the payload's bytes in slot B and slot A unchanged (version 1, signed FIT). A new QEMU booted `M9 slot B, version 2` and printed `M9-HEALTH: the update of slot B is committed`. The reverse update, from slot B to slot A, passed the same checks.
- The four stops while saving the selection found the old, old, new and new state (`+0.00`, `+0.05`, `+0.30`, `+1.00 s`), and each next boot followed it.
- Two test bugs were found on the way, and both failed loudly:
  - The copy parser split `M9_GOOD=A BOOT_B_LEFT=0` into `M9_GOOD='A B'` and `OOT_B_LEFT='0'`. That corrupts a value and loses a name. The M9-ab and M9-fit checks compare exact values or require those names, so the bug could make them fail but not pass a wrong state. They were rerun after the fix.
  - The card-copy helper tested the whole path for "update".
- A kernel message could land inside a marker line. The harness now quiets the console first.
