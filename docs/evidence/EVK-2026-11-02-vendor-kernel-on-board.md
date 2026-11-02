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

## Repeat: WDT0 before `booti`, the clocks after the sweep, 3 minutes unfed (EVK-L15)

**Board and firmware:** as above: the same board, cards and slots, and the same product chain (BL2/BL31 `v2.10.5 rz_1.1.0-dirty` built Sep 25 2025, OP-TEE `82a5cd3b-dev`, U-Boot 2024.07 built Sep 22 2025, `SYS_LSI_MODE: 0x10200`, `SYS_LSI_DEVID: 0x18447447`). **Kernel and DTB:** the project's G1 build, read from the carrier card: `boot/Image` 25963008 bytes, `Linux version 6.12.59-cip14-g212f6e88b724 ... #1 SMP PREEMPT Fri Oct 30 14:24:46 CET 2026`; `boot/r9a07g054l2-smarc.dtb` 39457 bytes. The local build output with that version string and size has SHA-256 `0d41afbb43338e1858c398be15401b888e9fec13588235948ae87dbff23269c6` (the card was written from it; the card itself was not re-hashed, A).

**Method:** the agent drove the console (`mcp-serial-rs`, `/dev/ttyUSB0`) under the operator's authorization for reads, the same boot commands as above, and a read-write mount of the project card's root. No `saveenv`, no flash and no WDT register write. The operator pressed the reset button twice: the first stop of autoboot came too late and the product image booted (no login, nothing typed); the second stopped at the prompt.

**Questions:** (1) is WDT0 running and its system reset enabled at the U-Boot prompt, before `booti`? (2) after Linux's unused-clock sweep, do WDT0's clocks stay off and does the board stay up for 3 minutes unfed? (3) which names do the SD hosts get on a second boot?

**Observations (O):** at the U-Boot prompt (`md.l`, reads only):

```
11010548: 000000ff     CPG_CLKON_WDT
110106c8: 0000003f     CPG_CLKMON_WDT
11010848: 0000000f     CPG_RST_WDT
11010b14: 0000008f     CPG_WDTRST_SEL
11010b10: 00000000     CPG_WDTOVF_RST
12800800: 00000001 2ae00000 00c0330d 00000000    WDTCNT WDTSET WDTTIM WDTINT
12800808: 00c260e3     WDTTIM, the same command line, 61 ms for the whole line
12800808: 0095dae5     WDTTIM, the next command, a few seconds later
```

In Linux (kernel command line as received: `rw rootwait earlycon root=/dev/mmcblk1p2 wdt_overflow=0`; the product U-Boot appends `wdt_overflow=0`, which the vendor kernel reports as unknown and passes to user space):

```
[    2.642476] renesas_sdhi_internal_dmac 11c10000.mmc: mmc1 base at 0x0000000011c10000, max clock rate 100 MHz
[    2.646046] renesas_sdhi_internal_dmac 11c00000.mmc: mmc0 base at 0x0000000011c00000, max clock rate 100 MHz
[    2.744524] mmcblk0: mmc0:aaaa SR128 119 GiB
[    2.822477] clk: Disabling unused clocks
[    2.853476] Waiting for root device /dev/mmcblk1p2...
[    3.087429] mmcblk1: mmc1:aaaa SC16G 14.8 GiB
[    3.142506] EXT4-fs (mmcblk1p2): mounted filesystem ... r/w with ordered data mode. Quota mode: none.
# ls /proc/device-tree/aliases/      -> ethernet0 ethernet1 i2c0 i2c1 i2c3 name serial0 serial1 (no mmc)

uptime     CPG_CLKON_WDT  CPG_CLKMON_WDT
 47.37 s   0x000000F0     0x00000030
 84.86 s   0x000000F0     0x00000030
151.79 s   0x000000F0     0x00000030
186.54 s   0x000000F0     0x00000030
```

The board was still running at the shell after the last read; the session was closed there (no reboot).

**Reading:**
1. Before `booti`, WDT0 runs (`WDTCNT` = 1) with the period of EVK-R40 (`WDTSET` `0x2AE00000`), its clocks are on (`CLKON_WDT` bits 1:0 set, `CLKMON_WDT` bits 1:0 set), it is out of reset (`RST_WDT` bit 0 set), and its system reset is enabled (`WDTRST_SEL` `0x8F`, bit 0 set, as EVK-R73). `WDTOVF_RST` = 0: the last reset was the reset button, not a watchdog. `WDTTIM` rose within one command and was lower at the next one: consistent with a counter that U-Boot restarts on each service (I).
2. After the sweep, `CLKON_WDT` = `0xF0` and `CLKMON_WDT` = `0x30` at every read from 47 s to 186 s (WDT0 and WDT1 bits 3:0 off), and the board did not reset in 186 s, three times U-Boot's 60 s timeout. With (1), this rules out the reading that the watchdog was never armed or could not reset the board: it was armed with its reset enabled, and the reset did not come once its clock stopped. That the count holds, and would resume where it stopped, remains an inference (I): no WDT0 register was read while its clocks were off.
3. Second boot: SDHI0 again `mmc0`, SDHI1 `mmc1`, no `mmc` aliases. SDHI1's probe message came 3.6 ms before SDHI0's this time, yet the names did not swap. Two boots, the same names; whether the names ever differ on silicon is not established.

**Side effects:** the product U-Boot saved its boot counter to the module card's environment on both resets (its own behaviour); the project card's root was mounted read-write. No register, flash or eMMC write by the agent.
