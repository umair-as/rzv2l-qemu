# EVK 2026-11-02: the vendor kernel on the board, unfed watchdog and SD names (EVK-L14)

**Board:** RZ/V2L SMARC EVK, console on SCIF0 (115200 8N1), boot mode eSD (`SYS_LSI_MODE: 0x10200`). Module slot (SDHI0): the board's 119 GiB boot card. Carrier slot (SDHI1): a 16 GB card with the project's `tests/guests/sd/build-image.sh` image (`/boot/Image`, 25963008 bytes, and the vendor DTB on partition 2).

**Firmware:** the board's product chain from the module card (a G2 image: BL2/BL31 `rz_1.1.0-dirty`, OP-TEE `82a5cd3b-dev`, U-Boot 2024.07 with the product's device-tree edits, `[EDGE]` lines). **Kernel and DTB:** the project's G1 build, the vendor `rz_linux-cip` `212f6e88b7` with its own `defconfig` and DTB (`6.12.59-cip14-g212f6e88b724`), the one QEMU runs.

**Method:** the agent drove the console (`mcp-serial-rs`) with the operator's approval. The product U-Boot was stopped at its prompt (it takes the word `edge`); its environment was read, not saved. Commands at the prompt: `ext4load mmc 1:2 0x48080000 boot/Image; ext4load mmc 1:2 0x48000000 boot/r9a07g054l2-smarc.dtb; setenv bootargs rw rootwait earlycon root=/dev/mmcblk1p2; booti 0x48080000 - 0x48000000`. U-Boot had started WDT0 (`Started watchdog@12800800 ... (60s timeout)`) and serviced it until `booti`. Linux mounted the carrier card's root; nothing fed the watchdog. The module card was detected, not mounted.

**Questions:** (1) does the board reset when nothing feeds the WDT0 that U-Boot started, under the vendor kernel? (2) what names do the two SD hosts get without `mmc` aliases?

**Observations (O):**

```
[    2.638532] renesas_sdhi_internal_dmac 11c00000.mmc: mmc0 base at 0x0000000011c00000, max clock rate 100 MHz
[    2.638530] renesas_sdhi_internal_dmac 11c10000.mmc: mmc1 base at 0x0000000011c10000, max clock rate 100 MHz
[    2.706234] mmcblk0: mmc0:aaaa SR128 119 GiB
[    2.826497] clk: Disabling unused clocks
[    2.859114] Waiting for root device /dev/mmcblk1p2...
[    3.072680] mmcblk1: mmc1:aaaa SC16G 14.8 GiB
[    3.139203] EXT4-fs (mmcblk1p2): mounted filesystem ... r/w with ordered data mode.
# ls /proc/device-tree/aliases/mmc*        -> none
# grep wdt /sys/kernel/debug/clk/clk_summary
                wdt0_pclk            0       1        0        100000000 ...  12800800.watchdog  pclk
       wdt0_clk                      0       1        0        24000000  ...  12800800.watchdog  oscclk
# devmem 0x11010548 32    (CPG_CLKON_WDT)
0x000000F0
# devmem 0x110106C8 32    (CPG_CLKMON_WDT)
0x00000030
# cat /proc/uptime
110.64 216.91
```

**Reading:**
1. With nothing feeding it, WDT0 did not reset the board: at 110 s of uptime the board was still running, well past the 60 s U-Boot programmed. Linux's unused-clock sweep (2.83 s) stopped WDT0's clocks: enable count 0 for `wdt0_pclk` and `wdt0_clk`, `CLKON_WDT` bits 3:0 = 0, `CLKMON_WDT` = `0x30`. The manual has the counter operate with WDTn_CLK (§21.1.1), so a stopped clock stops the count (I, consistent with O). QEMU read the same register values but reset at 60 s; the model now holds the count while WDTn_CLK is off.
2. The device tree Linux received has no `mmc` aliases (the product U-Boot added none to the vendor DTB). The two hosts probed 2 µs apart; on this boot SDHI0 became `mmc0` and SDHI1 `mmc1`. One boot is one sample: whether the order varies on silicon is not established.

**Side effects:** none on the board's media. One earlier, missed attempt to stop U-Boot booted the product image normally, whose U-Boot saves its boot counter to the module card's environment on every boot.
