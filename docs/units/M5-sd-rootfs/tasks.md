# M5-sd-rootfs — tasks

Project branch `unit/M5-sd-rootfs` from `main` `ad5a190`. No fork branch: the QEMU model is used as merged (`rzv2l-dev` `10df946cc8`).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | The card image gets a root partition: p2 ext4 with the project's static BusyBox, `init`, `inittab` (shutdown: `umount -a -r`), `rcS` with a boot count, a ready line; p1 stays the data partition; files owned by root via `fakeroot` | `tests/guests/sd/build-image.sh` | `rootfs.py` | done |
| T2 | Root file system acceptance: both kernels without `-initrd`, the board's command line; root device, PID 1, command line; `poweroff` ends QEMU; host superblock (no journal recovery), `e2fsck`, `debugfs`; a second QEMU; `reboot` in the same QEMU | `tests/acceptance/m5/rootfs.py`, `run.sh` | M5 ACCEPTANCE | done |
| T3 | The M5-sdhi storage check reads p1 by its size from the partition table (the image now has p2 after it) | `tests/acceptance/m5/storage.py` | M5 ACCEPTANCE | done |
| T4 | Walkthrough step, milestones, the device map's command-line note, requirement REQ-SDHI-003 | `docs/` | — | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `rootfs.py` `boot()`: the initramfs passed after all (`-initrd tests/guests/out/g0/initramfs.cpio.gz`) | `rootfs.py:193 boot_checks`: `FAIL boot 1: the card's init reaches the shell` (the initramfs `/init` runs instead) |
| 2 | `build-image.sh` inittab: `::shutdown:/bin/true` (no read-only remount before power-off) | `rootfs.py:165 host_checks`: `FAIL host after boot 1: the journal needs no recovery …` (`e2fsck -fn` alone stays green: it skips the journal) |
| 3 | `build-image.sh` `rcS`: the boot count written to `/tmp` (tmpfs) instead of the card | `rootfs.py:200 boot_checks`: `FAIL boot 1: / is /dev/mmcblk0p2, boot 0 from this card` |
| 4 | `rootfs.py` `boot()`: QEMU started with `-no-reboot` (the reset ends QEMU instead of restarting the board) | `rootfs.py:248 main`: `FAIL boot 3 (after the reset, same QEMU): / is None, boot None` |

Each mutation was run alone on G0 with the image rebuilt, against the final `rootfs.py` and `build-image.sh`; the files were restored from a copy and the image rebuilt afterwards. Mutation 2 shows why the superblock check exists: a power-off with the root still mounted read-write passes `e2fsck -fn` (found while writing the check).

## Boot evidence (fork `10df946cc8`, project `unit/M5-sd-rootfs`)

`QEMU=build/qemu/qemu-system-aarch64 python3 -I tests/acceptance/m5/rootfs.py OUT --tier g0|g1`: 26 checks PASS on each kernel. G1, second QEMU (boot 2, `reboot`, boot 3, `poweroff`):

```
[    6.413240] VFS: Mounted root (ext4 filesystem) on device 179:2.
[    6.468936] Run /sbin/init as init process
SD-ROOT: ready, root /dev/mmcblk0p2, boot 2
[   10.828891] reboot: Restarting system
[    6.447712] VFS: Mounted root (ext4 filesystem) on device 179:2.
[    6.503321] Run /sbin/init as init process
SD-ROOT: ready, root /dev/mmcblk0p2, boot 3
[    9.781813] reboot: Power down
```

The `-d` logs of the six boots (four log files) hold only the recorded stub windows of `tests/acceptance/m4/expected/log-allow.txt`. The M5-sdhi storage check passes on the two-partition image with both kernels (16 checks each). The walkthrough step ran through `scripts/run.sh` on one image copy: G1 boot 1, `reboot`, boot 2, `poweroff`; then G0 boot 3; the superblock had no `needs_recovery` and `e2fsck -fn` exited 0.
