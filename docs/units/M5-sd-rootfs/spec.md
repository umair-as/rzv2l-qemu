# M5-sd-rootfs — spec

**Milestone:** M5 (storage; second unit). **Requirements:** REQ-SDHI-003 (proposed with this page).

## Scope

**Linux user space from an ext4 root file system on the SD card**, with both kernels (G0: mainline v6.12.59; G1: the Renesas kernel) and no initramfs. The SD host model from [M5-sdhi](../M5-sdhi/spec.md) is used as it is: this unit changes the guest image and the test tooling, and changes the QEMU model only if a boot shows that it must.

- **The card image** (`tests/guests/sd/build-image.sh`): two partitions in an MS-DOS table, as on the board's eSD card, which has a partition table and its root file system on `mmcblk0p2` (O, below). p1 keeps the M5-sdhi data partition (ext4, 16 MiB); p2 (ext4, the rest of the 64 MiB card) is the root: the project's static BusyBox 1.36.1 (built by `tests/guests/g0/build-initramfs.sh`), BusyBox `init` with an `inittab`, an `rcS` that mounts `proc`, `sysfs` and a `tmpfs` and counts the boots in `/var/boot-count`, and a login profile that prints a ready line. The files belong to root (`fakeroot` at image build time; no root rights needed).
- **The command line** is the one the board's U-Boot passes for an SD root: `rw rootwait earlycon root=/dev/mmcblk0p2` (O, below), given with `-append` (QEMU's loader writes it to `/chosen/bootargs`, as U-Boot does). The board adds `wdt_overflow=0` and, on the G2 image (a product built on the vendor stack), `rauc.slot=A`; both are already listed gaps or G2 only (device map §4 gap 8). The console comes from the device tree's `stdout-path`.
- **Shutdown and restart:** `poweroff` and `reboot` in the guest go through BusyBox `init`, which runs the inittab's `shutdown` action (`umount -a -r`: the root is busy, so it is remounted read-only), and then through PSCI `SYSTEM_OFF` / `SYSTEM_RESET`, which QEMU implements in direct mode. `SYSTEM_OFF` ends QEMU; `SYSTEM_RESET` resets the board and loads the kernel again from `-kernel`, and that kernel mounts the card again.
- **Not in this unit:** eMMC on SDHI0 (boot mode 1); a boot loader reading the kernel from the card (M7: U-Boot); power loss (only clean shutdown is claimed); `fsck` at boot (the root is mounted `rw` directly).

## What the guest needs

- **Built in, effective `.config`** (G0 and G1 alike): `CONFIG_EXT4_FS=y`, `CONFIG_MMC_BLOCK=y`, `CONFIG_MSDOS_PARTITION=y`, `CONFIG_DEVTMPFS_MOUNT=y` (the kernel mounts `/dev` on the card's root before it runs init), `CONFIG_INITRAMFS_SOURCE=""` and `CONFIG_CMDLINE=""` (nothing built in hides a missing root). No module is needed.
- **`rootwait`:** the SD card is found by an asynchronous probe; the kernel waits for `mmcblk0p2` instead of failing at once.
- **A stable name:** `mmcblk0` is SDHI0's card only because QEMU's loader adds the `mmc0`/`mmc1` aliases the stock device trees lack (M5-sdhi, device map §4 gap 8).
- **Init:** with a block-device root and no `init=`, the kernel runs `/sbin/init` (a BusyBox link); BusyBox `init` reads `/etc/inittab`.
- **PSCI:** `SYSTEM_OFF` and `SYSTEM_RESET` (the device tree's `/psci` node, replaced by QEMU, gap 7).

## Exit criterion

Per kernel, from a fresh copy of the card image (`tests/acceptance/m5/rootfs.py`):

1. Boot 1 without `-initrd`: the kernel logs `VFS: Mounted root (ext4 filesystem) on device 179:2` and `Run /sbin/init as init process`; `/` is `mmcblk0p2`, PID 1 is BusyBox `init`, `/proc/cmdline` is the board's command line, the card counts boot 1. A file of 1 MiB + 7 bytes is written; `poweroff` powers the board down and QEMU exits by itself with status 0.
2. On the host: the root file system's journal needs no recovery (it was left read-only), `e2fsck -fn` finds it clean, `debugfs` reads the file with the guest's MD5 and the boot count 1.
3. Boot 2 in a new QEMU: boot 2, the file reads back. A second file is written; `reboot` resets the board in the same QEMU process and the kernel boots from the card again (boot 3); both files read back; `poweroff`. On the host: clean, boot count 3, both files match.
4. The `-d` log of every boot lists only recorded stub windows; the M5-sdhi storage check still passes on the two-partition image; the M5 acceptance (which runs M1-M4 first) and the serial-port regression suite pass.

## Evidence

- **Board command line and root (O, G2 image on the EVK, eSD boot):** capture `tio_ttyUSB0_2026-04-17T21:41:08.log` (SHA-256 `edc6781d0e031d5348a5492145b22f60a2eb40372bb3694f9d7dbf49878e9202`, kept by the operator): `Kernel command line: rw rootwait earlycon root=/dev/mmcblk0p2 rauc.slot=A wdt_overflow=0`, `mmcblk0: p1 p2 p3 p4`, `EXT4-fs (mmcblk0p2): mounted filesystem … r/w`, `VFS: Mounted root (ext4 filesystem) on device 179:2`, `Run /sbin/init as init process`, and at shutdown `EXT4-fs (mmcblk0p2): re-mounted … ro`. The G2 image is a sample, not a dependency: this unit takes from it only the command line and the partition role.
- **Card topology (O):** SDHI0 carries the SD card, mmc0, at 50 MHz high speed (EVK evidence §8).
- **Kernel configuration (F):** the effective `.config` of both builds (`tests/guests/out/g{0,1}/linux/.config`), lines named above.
- **Shutdown path (F):** QEMU's built-in PSCI: `SYSTEM_OFF` requests a guest shutdown, `SYSTEM_RESET` a reset (`qemu/target/arm/tcg/psci.c`).

## For the operator

- **No QEMU change was needed.** Both kernels mount the card's root and power off and reset through PSCI on the merged model (fork `rzv2l-dev` `10df946cc8`).
- **The console needs a reader (O, model; harness only).** QEMU's serial model waits for the chardev to accept each byte (backpressure, as a UART with flow control). With the console socket unread, QEMU had not exited 90 s after `poweroff`; read, it exited at once (O). The cause is very likely QEMU's one-byte writes filling the socket buffer, so the guest's console stalls before PSCI (I, not measured). The acceptance script reads the console until QEMU exits. This is QEMU's chardev behaviour, not a model fault.
- **The image keeps p1 for the M5-sdhi data checks**, so one card serves both runs; on the board p1 is the boot partition. A FAT boot partition only matters once U-Boot loads the kernel from the card (M7).
