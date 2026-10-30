# M4-vendor-kernel — tasks

Fork branch `unit/M4-vendor-kernel` from `rzv2l-dev` `01168f7f3e`; project branch of the same name from `main`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | G1 kernel and DTB-V from public `rz_linux-cip` `212f6e88b7`, vendor `defconfig` | `tests/guests/g1/build-kernel.sh` | effective `.config` printed | done |
| T2 | Watchdog model WDT0-2 (Table 21.4), counter at 24 MHz, WDTINT, WDTRSTB, PEEN | fork `hw/watchdog/renesas_rzg2l_wdt.c` | qtest `/rzv2l-wdt/*` | done |
| T3 | CPG: `WDTRST_SEL`, `WDTOVF_RST`, PRESETN lines from `RST_WDT`, reset requests to QEMU's watchdog action; direct mode `WDTRST_SEL 0x8F` | fork `hw/misc/renesas_rzv2l_cpg.c` | qtest `/rzv2l-wdt/reset-request`, `/presetn` | done |
| T4 | SoC: WDT0-2 and their interrupts; stub windows for the drivers G1 builds in (device map class UNIMP) | fork `hw/arm/r9a07g054.c` | G1 boot | done |
| T6 | Review response: a held reset request acts when `CPG_WDTRST_SEL` unmasks it (WDTRSTB is a level); qtests for that and for a start value above the cycle; `WDTOVF_RST`/`WDTRST_SEL` reset behaviour cited to §7.2.4.182-183 | fork `renesas_rzv2l_cpg.c`, `rzv2l-wdt-test.c` | qtest 9/9; proofs 14-15 | done |
| T5 | Acceptance: G1 shell on two cold boots, WDT0 refresh / stop / expiry, log gate; `shell.py --tier g1 --watchdog` | `tests/acceptance/m4/`, `tests/acceptance/m3/shell.py` | M4 ACCEPTANCE: PASS | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `WDT_COUNT_SPAN` `0x100000` → `0x1` | `rzv2l-wdt-test.c:109 test_count`: `0 == 24000` |
| 2 | WDTSET keeps all bits written | `rzv2l-wdt-test.c:91 test_reset_values`: `0xffffffff == 0xfff00000` |
| 3 | WDT clock P0 100 MHz instead of 24 MHz | `rzv2l-wdt-test.c:109 test_count`: `100000 == 24000` |
| 4 | WDTSET and WDTTIM writable while running | `rzv2l-wdt-test.c:115 test_count`: `0x2ae00000 == 0x00000000` |
| 5 | INTDISP = 1 does not clear the running counter | `rzv2l-wdt-test.c:143 test_first_overflow`: `24023 == 0` |
| 6 | the second overflow resets whatever `WDTRST_SEL` says | `rzv2l-wdt-test.c:154 test_reset_request`: `0x00000000 == 0x00000001` |
| 7 | PEEN forces a reset whatever PECR says | `rzv2l-wdt-test.c:244 test_parity_force`: `'qtest_get_irq(qts, 1)' should be TRUE` |
| 8 | `WDTOVF_RST` clears without its write-enable bit | `rzv2l-wdt-test.c:176 test_reset_request`: `0x00000000 == 0x00000001` |
| 9 | `RST_WDT` does not drive PRESETN | `rzv2l-wdt-test.c:264 test_presetn`: `0x00000000 == 0xfff00000` |
| 10 | the system reset clears `WDTOVF_RST` | `rzv2l-wdt-test.c:171 test_reset_request`: `0x00000000 == 0x00000001` |
| 11 | the first overflow already resets | `rzv2l-wdt-test.c:163 test_reset_request`: `0x00000000 == 0x00000001` |
| 12 | `RST_WDT` does not drive PRESETN (Linux's stop-and-start timeout change cannot apply, so WDT0 keeps its 60 s default) | M4 acceptance: `FAIL WDT0 not pinged (timeout 3 s): the board resets within 20 s (new boot after 20.3 s)` |
| 13 | direct mode without `WDTRST_SEL 0x8F` (the system reset stays masked) | M4 acceptance: `FAIL WDT0 not pinged (timeout 3 s): the board resets within 20 s (new boot after 20.3 s)` |
| 14 | `CPG_WDTRST_SEL` write does not act on a held reset request | `rzv2l-wdt-test.c:192 test_masked_request`: `0x00000001 == 0x00000000` |
| 15 | a start value above the cycle waits a full 2^32 clocks before the first cycle | `rzv2l-wdt-test.c:213 test_start_above_period`: `0x00000000 == 0x00000001` |

Each mutation was built with a confirmed relink and run alone; the source was restored and rebuilt, and the full test passed after each. Proofs 12-13 run `shell.py --tier g1 --watchdog`. Proof 12 first passed a 60 s wait (the reset came at 60.3 s), so the expiry check now bounds the reset at 20 s: 3 s, then the boot back to the console (5.0 s measured).

## Boot evidence (fork `unit/M4-vendor-kernel`)

```
build/qemu/qemu-system-aarch64 -M rzv2l-smarc \
    -kernel tests/guests/out/g1/linux/arch/arm64/boot/Image \
    -dtb tests/guests/out/g1/r9a07g054l2-smarc.dtb \
    -initrd tests/guests/out/g0/initramfs.cpio.gz \
    -display none -nodefaults -serial mon:stdio \
    -d unimp,guest_errors,invalid_mem -D build/qemu.log
```

`Linux version 6.12.59-cip14-g212f6e88b724`, `legacy console [ttySC0] enabled`, `G0-INIT: ready, cpus online 0-1`. Before the stub windows the boot aborted in `rzg2l_mipi_dsi_dphy_init` (a write to `0x10850000`), then in `rcar_canfd_reset_controller` (`0x1005008C`). With BusyBox `watchdog -T 3 -t 1000` the board reset and came back with `CPG_WDTOVF_RST` = `0x00000001`.
