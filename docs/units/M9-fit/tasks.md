# M9-fit — tasks

Project branch `unit/M9-fit` from `main`. No fork branch: no QEMU change expected (fork `rzv2l-dev` `176d418966`).

| ID | Task | Test | Status |
|---|---|---|---|
| T1 | `build-u-boot-m9.sh` + `u-boot-m9.cfg`: the M9 profile; effective `.config` kept; build fails on a missing option | build check | todo |
| T2 | `m9-key.sh`: one key per profile, reused; public key into both control DTBs (`required = "conf"`), read back from the binary | build check | todo |
| T3 | `build-fit-m9.sh`: kernel + vendor DTB, signed configuration; the negative FITs from the same key (and a second key) | build check | todo |
| T4 | `spi-m9.img` and `sd-m9.img` (slots A and B, both environment copies, bounds asserted); the boot policy (DR-0008 decision 6) as the default and stored environment | `fit.py` accepted | todo |
| T5 | `m9/fit.py`: accepted, the four rejections, counters to 0 and the prompt; hashes per run | `fit.py` | todo |
| T6 | `m9/run.sh` (M8 first), log gate; milestones, walkthrough, learning; Next blocker | M9 acceptance | todo |

## Proofs (each break: the exact change → the red line)

| # | Break | Red line |
|---|---|---|

## Boot evidence
Written at the end.
