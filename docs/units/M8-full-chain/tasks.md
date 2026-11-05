# M8-full-chain — tasks

Project branch `unit/M8-full-chain` from `main` `8ac2294`. No fork branch: no QEMU change (fork `rzv2l-dev` `176d418966`).

| ID | Task | Test | Status |
|---|---|---|---|
| T1 | `bootloader.start` takes the firmware source (staged `-bios`/`bl32=`/`bl33=`, or boot mode 3/4 with a fresh copy of the flash image) and records each run's command and the SHA-256 of the images it used | M7 acceptance | done |
| T2 | `m8/chain.py`: BL2 to the kernel's start in order, M7's boot checks, `reboot` back through BL2 in the same QEMU | `chain.py` chain | done |
| T3 | FIP negatives: BL33 removed, BL31 removed; each run's command line stages nothing | `chain.py` fip | done |
| T4 | M7's Linux and OP-TEE checks on the chain path with the TEE card | `chain.py` tee | done |
| T5 | Boot mode 4: BL2 prints `0x10004`, BL31 and U-Boot start from the FIP | `chain.py` mode 4 | done |
| T6 | Log gate: `m8/expected/log-allow-chain.txt`, M7's four lines re-checked at source with BL2 in front | `run.sh` log gate | done |
| T7 | Milestones, walkthrough step; Next blocker | M8 acceptance | todo |

## Proofs (each break: the exact change → the red line)

No model code changed, so each check is seen red by breaking its input:

| # | Break | Red line |
|---|---|---|
| 1 | `chain(3)` with OP-TEE's switch to the normal world expected after the U-Boot banner | `FAIL …: in order: I/TC: Primary CPU switching to normal world boot` |
| 2 | boot mode 3 checked against `bl2(4)` | `FAIL …: in order: NOTICE:  BL2: SYS_LSI_MODE: 0x10004` |
| 3 | `unstaged` on M7's staged run directory | `FAIL …: the command line stages nothing: rzv2l-smarc,bl32=…,bl33=… -bios` |
| 4 | `case_fip` given the unmodified flash image | `FAIL fip without --nt-fw: BL2 cannot load image id 5` |
| 5 | the gate without `^sdhi_write: undefined offset 0x8$` | the chain run's `sdhi_write: undefined offset 0x8` outside the list |

## Boot evidence
Written at the end.
