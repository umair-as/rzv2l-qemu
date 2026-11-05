# M9-fit — tasks

Project branch `unit/M9-fit` from `main`. No fork branch: no QEMU change (fork `rzv2l-dev` `176d418966`).

| ID | Task | Test | Status |
|---|---|---|---|
| T1 | `build-u-boot-m9.sh` + `u-boot-m9.cfg` + the backport `patches/u-boot-m9/`: the M9 profile, banner `U-Boot 2024.07-m9`; effective `.config` kept; build fails on a missing option | build check | done |
| T2 | One key per profile, made once and reused (`out/m9/keys/`); `key2dtsi.py` + `CONFIG_DEVICE_TREE_INCLUDES` put it into both control DTBs (`required = "conf"`); the build reads it back and checks that `u-boot.bin` ends in those DTBs | build check | done |
| T3 | `build-fit-m9.sh`: the signed FIT; six negatives from it and the same key (kernel byte, DTB byte, unsigned, other key, upstream's `fakeroot` and `kernel@`); host `fit_check_sign` accepts the signed FIT and refuses each negative | build check | done |
| T4 | `build-spi-image.sh --m9` (`spi-m9.img`, its own FIP and record; the vendor image unchanged: same SHA-256); `build-image-m9.sh` (`sd-m9.img`: p1 at `0x400000`, slots A and B); `uboot-env.py m9-write/m9-read/m9-damage` (two copies, places checked against the M9 build, bounds asserted); the boot policy `u-boot-m9.env` as default and stored environment | `fit.py` accepted | done |
| T5 | `m9/fit.py`: accepted in the first boot, the attempt saved before the FIT loads, `BOOT_A_LEFT=2` on the card after; six refusals, each attempt saved (2, 1, 0), refused with its reason, reset, then the prompt with the counters; hashes per run | `fit.py` | done |
| T6 | `m9/run.sh` (M8 first), log gate (`m9/expected/log-allow.txt`: no new line); milestones, walkthrough; Next blocker | M9 acceptance | done |

## Proofs (each break: the exact change → the red line)

No model code changed, so each check is seen red by breaking its input:

| # | Break | Red line |
|---|---|---|
| 1 | the accepted case with the unsigned FIT in slot A (U-Boot refuses A three times, then boots slot B's FIT) | `FAIL accepted: all of it in the first boot, no reset before the kernel starts`; `FAIL accepted: / is slot A, PARTUUID 525a0003-02` |
| 2 | the accepted case with `BOOT_A_LEFT=5` stored | `FAIL accepted: in order: M9: slot A: attempt saved: BOOT_A_LEFT=2 BOOT_B_LEFT=3`; the card holds `BOOT_A_LEFT=4` |
| 3 | a negative case given the signed FIT | `FAIL refused signed, attempt 1: in order: Failed to verify required signature 'key-m9-dev'` |
| 4 | the key check on the vendor build's control DTB | `Error at '/signature/key-m9-dev': FDT_ERR_NOTFOUND` |
| 5 | the host check asked to accept the other-key FIT | `Signature check bad (error 1)`: `Failed to verify required signature 'key-m9-dev'` |
| 6 | the gate without `^sdhi_write: undefined offset 0x8$` | the accepted run's `sdhi_write: undefined offset 0x8` outside the list |

Proof 1 first passed the ordered lines: they matched across the three resets and slot B's boot, and only the slot check caught it. The first-boot check was added then.

## Boot evidence (fork `176d418966`)

`tests/acceptance/m9/run.sh`: `M9 ACCEPTANCE: PASS`, with `M8 ACCEPTANCE: PASS` and `M7 ACCEPTANCE: PASS` inside it (the vendor-default U-Boot profile). The accepted run used `spi-m9.img` (SHA-256 `6a2cafb5…b2ea`) and a fresh copy of `sd-m9.img`; its command line names no `-bios`, `-kernel`, `bl32=` or `bl33=`. Its serial log shows `U-Boot 2024.07-m9`, `Writing to redundant MMC(0)... OK`, `M9: slot A: attempt saved: BOOT_A_LEFT=2 BOOT_B_LEFT=3`, `Verifying Hash Integrity ... sha256,rsa2048:m9-dev+ OK`, `Starting kernel ...` and `SD-ROOT: ready, ... partuuid 525a0003-02, card sd-m9`. Each refused run ends with `M9: no slot has an attempt left: BOOT_ORDER=A BOOT_A_LEFT=0 BOOT_B_LEFT=3` and `=>`.
