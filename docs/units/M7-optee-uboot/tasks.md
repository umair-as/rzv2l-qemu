# M7-optee-uboot — tasks

Branches `unit/M7-optee-uboot` (project and fork), rebased on M7-el3-platform once it merges.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | OP-TEE build: vendor commit, BSP flags, `CFG_RZ_SCE=n`, reproducible | new `build-optee.sh` in `tests/guests/fw/` | SHA-256 the same over two builds | done: `82a5cd3b`, effective `conf.mk` checked (`CFG_RZ_SCE=n`, TZDRAM `0x44100000`+`0x3D00000`, 2 cores); two builds, one SHA-256 |
| T2 | U-Boot build: vendor commit, `smarc-rzv2l_defconfig`, reproducible | new `build-u-boot.sh` in `tests/guests/fw/` | as T1 | done: `4eebfbaa4e`, effective `.config` kept (`u-boot.config`: `OPTEE_LIB`, `OF_LIBFDT`); two builds, one SHA-256 |
| T3 | SD card with `boot/Image` and the DTB on partition 2 | `tests/guests/sd/build-image.sh` | U-Boot's `ext4load` | done: U-Boot's `ext4load` reads both files |
| T4 | BL2 stand-in: BL32 and BL33 entries in the parameter block (BL32 `arg0` = `MODE_RW_64`, written explicitly), images loaded where BL2 puts them | fork `hw/arm/rzv2l-smarc.c` | firmware boot | done: `bl32=`/`bl33=` (operator's choice); BL2's device tree in `x1`; CPG as BL2 leaves it |
| T5 | Failure loop: OP-TEE, then U-Boot (OTP, RPC, DDR ECC read, USB), each window with its class | fork models and SoC; `docs/device-map.md` | firmware boot, `-d` log gate | done: see below |
| T6 | Acceptance: OP-TEE and U-Boot banners, Linux from the card, `MIGRATE_INFO_TYPE`, hotplug, reset, watchdog fed, lost boots counted; unit 1's boot and direct mode unchanged | `tests/acceptance/m7/` | M7 ACCEPTANCE | done: `bootloader.py`; log gate PASS |
| T7 | EVK-R80: DDR controller ECC enable as U-Boot reads it | `docs/evidence/` | — | done: `0x00000FFF`, bits 25:24 = 0 (EVK-2026-11-02) |
| T8 | Root by PARTUUID (DR-0007): the project's U-Boot environment on each card, distinct disk identifiers, the root checked by PARTUUID and card; root on the other card; a missing PARTUUID; the vendor default as a separate compatibility verdict | `tests/guests/sd/{boot.env,uboot-env.py,build-image.sh}`; `tests/acceptance/m7/{firmware,bootloader,tee,rootsel,compat}.py`, `run.sh` | M7 ACCEPTANCE; VENDOR-DEFAULT COMPATIBILITY | done |

## What the failure loop met (T5)

In boot order; each fix is the smallest one the guest's code and the hardware contract call for.

1. OP-TEE reads the OTP chip ID (`0x11861140`): unmapped, data abort. New OTP model, ID from properties (default 0, not silicon).
2. U-Boot reads the DDR controller's ECC bits (`0x1141018C`): unmapped, U-Boot's exception loop. Stub window, reads 0: the non-ECC tree; the board reads bits 25:24 = 0 (EVK-R80).
3. U-Boot's SPI-NOR probe: JEDEC ID 0, `Failed to set up SPI slave`, U-Boot carries on. Left failing (honest; design choice 2).
4. U-Boot's SD writes ignored: SDHI held in reset, the CPG at manual reset values. New `bl2-boot` CPG start state from BL2's `cpg_setup()` tables and its DDR set-up.
5. U-Boot's ACMD51 in normal mode had no data phase: the card never initialised. Normal mode decodes the data commands of Table 40.8.
6. CPU1 faulted in OP-TEE at S-EL1 (`cpu_on_handler`, level-1 translation fault): `MPIDR_EL1.MT` was 0, so OP-TEE took core 1 for core 4 and used empty tables; the spinning core slowed the whole boot and the 60 s watchdog reset it. The Cortex-A55 reports MT = 1; the SoC sets it through the new CPU property `mpidr-mt`, so other machines are unchanged.
7. WDT0, started by U-Boot, reset the QEMU board after 60 s when nothing fed it. On the board, Linux's unused-clock sweep stops WDT0_CLK and the board does not reset (EVK-L14). The WDT model now runs its counter only while WDTn_CLK runs (manual §21.1.1), driven by the CPG's `CLK_ON_WDT` bit 2n + 1; the acceptance checks both: no reset unfed for 75 s, no reset fed for 75 s.
8. Some boots wait for `/dev/mmcblk0p2` while the card is `mmcblk1`: no `mmc` aliases in the vendor device tree (device map gap 22). With the watchdog fixed such a boot waits for ever, as on the board. Not a model defect: the vendor command line names the root by a probe-order name. The project's boot configuration names it by PARTUUID (DR-0007, T8); the vendor default stays as a compatibility check that counts its lost boots.
9. U-Boot sometimes hangs at a console character in `sh_serial_putc` (CPU0 PC `0x5003a1fc`): when the frame ends between its FTDR write and FSR read on QEMU's host-time clock, it clears the TEND it needs. An independent review's traces of 12 stalled boots show FSR `0x60` read, `0x20` written, then `0x20` for ever; it reported none in 61 boots on a quiet host and 63 in 144 on a loaded one (its runs; logs not in the repository; device map gap 23). Unresolved; a stalled run is a FAIL.
10. With the first, minimal project environment, U-Boot took a synchronous abort after `Starting kernel`, before Linux, on each boot of a reset loop: the vendor's in-place `strcat` of ` wdt_overflow=0` to `bootargs` (`arch/arm/lib/bootm.c:208`) overran the string's heap allocation. Not a model defect: padding `bootargs` with spaces so the allocation fits removed it (DR-0007 item 6; `uboot-env.py` refuses an overrunning `bootargs`).

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | OTP: the chip ID at `0x1100` instead of `0x1140` | `rzv2l-smarc-test.c:347 test_otp_chip_id`: `0x00000000 == 0x03020100` |
| 2 | OTP: the chip-ID window one word wider | `rzv2l-smarc-test.c:353 test_otp_chip_id`: `0x46ad1d00 == 0x00000000` |
| 3 | SDHI: ACMD51 left out of the normal-mode reads | `rzv2l-sdhi-test.c:398 test_normal_mode`: `0x00000000 == 0x00004100` |
| 4 | SDHI: ACMD13 left out of the normal-mode reads | `rzv2l-sdhi-test.c:410 test_normal_mode`: `0x00000000 == 0x00004100` |
| 5 | SDHI: every normal-mode command decoded as an ACMD | `rzv2l-sdhi-test.c:422 test_normal_mode` (CMD6): `0x00000000 == 0x00004100` |
| 6 | CPG: `RST_SDHI` left out of the BL2 state | `rzv2l-cpg-test.c:217 check_values` (bl2-boot): `0x00000000 == 0x00000003` |
| 7 | CPG: `bl2-boot` ignored | `rzv2l-cpg-test.c:217 check_values` (bl2-boot): `0x00000000 == 0x00000100` |
| 8 | CPG: BL2's `WDTRST_SEL` left at the reset `0x88` | `rzv2l-cpg-test.c:217 check_values` (bl2-boot): `0x00000088 == 0x0000008f` |
| 9 | SoC: `mpidr-mt` not set | EL3 probe `probe.c:176`: `FAIL MPIDR_EL1 of core 0: 0x0000000080000000 (expected 0x0000000081000000)`; the boot-loader run also fails (CPU1 never online) |
| 10 | BL2 stand-in: BL32 `arg0` = 1 (`MODE_RW_32`) | firmware boot: BL31's banner only, no `Primary CPU switching to normal world boot` (`bootloader.py` boot 1 check 2) |
| 11 | BL2 stand-in: no BL32 entry | firmware boot: `Error initializing runtime service opteed_fast`, `MIGRATE_INFO_TYPE not supported.` (`bootloader.py` boot 1 checks 6-7) |
| 12 | CPG: `CLK_ON_WDT` writes do not reach the WDT (`wdt-clk` not updated) | `rzv2l-wdt-test.c:282 test_clock_stopped`: `0x00000000 == 0x0007ffff` (the board reset) |
| 13 | WDT: the `clk` input ignored | `rzv2l-wdt-test.c:282 test_clock_stopped`: `0x00000000 == 0x0007ffff` |
| 14 | WDT: counting resumes from 0, not the held count | `rzv2l-wdt-test.c:291 test_clock_stopped`: `0x00000000 == 0x00000001` |
| 15 | CPG: the bus clock bit (2n) taken for WDTn_CLK (2n + 1) | `rzv2l-wdt-test.c:282 test_clock_stopped`: `0x00000000 == 0x0007ffff` |
| 16 | WDT: a restart (WDTEN, INTDISP clear) arms the timer with WDTn_CLK stopped | `rzv2l-wdt-test.c:310 test_clock_stopped_start`: `0x00000000 == 0x00000001` (the board reset) |
| 17 | The card's environment names `root_partuuid=525a00ff-02`, which no card has (`bootloader.py` boot 1) | `FAIL boot 1: the card's init reaches the shell (the kernel does not find PARTUUID=525a00ff-02: VFS: Unable to mount root fs on unknown-block(0,0))` |
| 18 | `rootsel.py` other medium: the environment names sd-tee's partition 2 while the check expects sd's | `FAIL boot 1: / is PARTUUID 525a0002-02 on card sd-tee, boot 1 from it (Linux names it /dev/mmcblk0p2)` |
| 19 | `rootsel.py` missing root: the "missing" PARTUUID is the card's own `525a0001-02` | `FAIL missing root: the kernel waits for PARTUUID=525a0001-02, then stops with 'VFS: Unable to mount root fs' (no wrong root)` |
| 20 | `boot.env` with `root_wait=300` (a 57-character `bootargs`) | `uboot-env.py: bootargs of 57 characters: the vendor's append of 15 overruns its 72-byte allocation; pad it with spaces` |

The overflow taken before the clock stops (a stop after the overflow time, before the model's timer has run) is unverified. The model's timer deadline is the first virtual nanosecond at which the count reaches the overflow (`wdt_time_of()` rounds up), so in virtual time the two coincide; they come apart only when a CPU thread keeps executing past the deadline before the main loop runs the timer, in a real TCG run. qtest cannot reproduce that: `clock_step` and `clock_set` run every due timer before the next register access, so a deterministic boundary test is not feasible.
