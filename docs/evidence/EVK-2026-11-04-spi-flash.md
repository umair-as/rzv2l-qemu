# EVK 2026-11-04: the SPI flash's ID and SFDP tables (EVK-L16)

**Board:** RZ/V2L SMARC EVK, console on SCIF0 (115200 8N1), boot mode eSD (`SYS_LSI_MODE: 0x10200`, `SYS_LSI_DEVID: 0x18447447`). Module slot (SDHI0): the board's boot card. Carrier slot (SDHI1): the project's `tests/guests/sd/build-image.sh` card, as in EVK-L14/L15 ([evidence](EVK-2026-11-02-vendor-kernel-on-board.md)). The flash is the module's QSPI NOR on the SPI multi I/O bus controller (`docs/research/rpc.md`).

**Firmware:** the board's product chain from the module card (a G2 image, that is a product built on the Renesas stack: BL2/BL31 `v2.10.5(release):2.10.5/rz_1.1.0-dirty` built Sep 25 2025, OP-TEE `82a5cd3b-dev`, U-Boot 2024.07 built Sep 22 2025). **Kernel and DTB:** the project's G1 build (the Renesas vendor kernel) from the carrier card: `boot/Image` 25963008 bytes, `Linux version 6.12.59-cip14-g212f6e88b724 ... #1 SMP PREEMPT Fri Oct 30 14:24:46 CET 2026`; `boot/r9a07g054l2-smarc.dtb` 39457 bytes; the same image as EVK-L15, with the same assumption that the card holds that build.

**Method:** the agent drove the console (`mcp-serial-rs`, `/dev/ttyUSB0`) under the operator's authorization for reads; the operator pressed reset once. The product U-Boot was stopped at its prompt (`edge`); the EVK-L14 boot commands (`ext4load` of Image and DTB from `mmc 1:2`, `setenv bootargs rw rootwait earlycon root=/dev/mmcblk1p2`, `booti`). At the shell: reads of `dmesg`, `/proc/mtd` and the `spi-nor` sysfs attributes only. No `saveenv`, no flash write, no further reset; the session was closed at the shell.

**Question:** which JEDEC ID and SFDP tables does the board's flash return, so that the model's `mt25qu512a` makes Linux name and size the part as on the board?

**Observations (O):**

```
SF: Detected mt25qu512a with page size 256 Bytes, erase size 4 KiB, total 64 MiB     (product U-Boot start)
[    2.570842] 3 fixed-partitions partitions found on MTD device spi1.0
[    2.580402] Creating 3 MTD partitions on "spi1.0":
[    2.585228] 0x000000000000-0x00000001d000 : "bl2"
[    2.599269] 0x00000001d000-0x000002000000 : "fip"
[    2.605563] 0x000002000000-0x000004000000 : "user"
# cat /proc/mtd
dev:    size   erasesize  name
mtd0: 0001d000 00001000 "bl2"
mtd1: 01fe3000 00001000 "fip"
mtd2: 02000000 00001000 "user"
# ls /sys/bus/spi/devices/            -> spi1.0
# readlink /sys/bus/spi/devices/spi1.0/driver   -> .../bus/spi/drivers/spi-nor
jedec_id: 20bb20104400
partname: mt25qu512a
manufacturer: st
# wc -c < /sys/bus/spi/devices/spi1.0/spi-nor/sfdp
136
# od -An -tx1 -v /sys/bus/spi/devices/spi1.0/spi-nor/sfdp
 53 46 44 50 06 01 01 ff 00 06 01 10 30 00 00 ff
 84 00 01 02 80 00 00 ff ff ff ff ff ff ff ff ff
 ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
 e5 20 fb ff ff ff ff 1f 29 eb 27 6b 27 3b 27 bb
 ff ff ff ff ff ff 27 bb ff ff 29 eb 0c 20 10 d8
 0f 52 00 00 24 4a 99 00 8b 8e 03 e1 ac 01 27 38
 7a 75 7a 75 fb bd d5 5c 4a 0f 82 ff 81 bd 3d 36
 ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff
 ff e7 ff ff 21 dc ff ff
```

`dmesg | grep -i -e spi-nor -e rpc` printed only the five SunRPC transport lines: the vendor `spi-nor` and `rpc-if` drivers print nothing on a successful probe.

**Reading:**
1. The ID and name match the spec's expectation: `20 BB 20 10 44 00`, `mt25qu512a` (Micron, reported under the legacy `st` manufacturer). The three partitions match the vendor DTB.
2. The sysfs `sfdp` file holds SFDP addresses `0x00`-`0x87` as read from the flash in one transfer: the kernel reads from address 0 up to the end of the last parameter table it found (`drivers/mtd/spi-nor/sfdp.c:1438-1509` and `sysfs.c:60-63`, `rz_linux-cip` `212f6e88b7`; code). The `0xFF` bytes between the tables (`0x18`-`0x2F`, `0x70`-`0x7F`) are flash content too (I).
3. Decoded (JESD216; I): header `SFDP`, revision 1.6, two parameter headers. BFPT (basic flash parameters): revision 1.6, 16 dwords at `0x30`; 4K erase `0x20`; 3- or 4-byte addresses; density `0x1FFFFFFF` = 512 Mbit (64 MiB); fast reads 1-1-2 `0x3B`, 1-2-2 `0xBB`, 1-1-4 `0x6B`, 1-4-4 `0xEB` (8 or 10 clocks of mode + dummy), 2-2-2 `0xBB`, 4-4-4 `0xEB`; erase types 4 KiB `0x20`, 64 KiB `0xD8`, 32 KiB `0x52`; page size 256 bytes (DW11); no quad-enable bit (DW15 QER = 0). Second table: ID `0x84` (4-byte address instruction table), revision 1.0, 2 dwords at `0x80`; 4-byte erase opcodes `0x21` (4 KiB) and `0xDC` (64 KiB).
4. Addresses above `0x87` were not read: what the flash returns there is unknown (A: the model returns `0xFF`).

**Side effects:** the product U-Boot saved its boot counter to the module card's environment on the reset (its own behaviour); the project card's root was mounted read-write. No register, flash or eMMC write by the agent.
