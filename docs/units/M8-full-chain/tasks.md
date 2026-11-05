# M8-full-chain — tasks

Project branch `unit/M8-full-chain` from `main` `8ac2294`. No fork branch: no QEMU change expected (fork `rzv2l-dev` `176d418966`); one is opened only if a check exposes a model gap.

| ID | Task | Commit | Test | Status |
|---|---|---|---|---|
| T1 | `bootloader.start` takes the firmware source (staged `-bios`/`bl32=`/`bl33=`, or boot mode 3/4 with the flash image); M7 runs unchanged | | M7 acceptance | todo |
| T2 | `m8/chain.py`: the chain to the shell, both CPUs, `reboot` back through BL2 | | `chain.py` boot 1, boot 2 | todo |
| T3 | FIP negatives: BL33 removed, BL31 removed; the run's own command line and `build.txt` hashes | | `chain.py` fip | todo |
| T4 | `tee_checks` on the chain path with the TEE card | | `chain.py` tee | todo |
| T5 | Boot mode 4: BL2 prints `0x10004` and loads the FIP from the flash | | `chain.py` / `bl2.py` | todo |
| T6 | Log gate: the post-BL31 section of `m8/expected/log-allow.txt`, each line checked at source on this path | | `run.sh` log gate | todo |
| T7 | `run.sh`, milestones, walkthrough step; Next blocker | | M8 acceptance | todo |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|

Acceptance-script checks are seen red by breaking the input, not the model (a FIP entry removed, a wrong boot mode, an allow-list line removed); each one is listed here when run.

## Boot evidence
Written at the end.
