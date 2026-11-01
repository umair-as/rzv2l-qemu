# M7-el3-platform — tasks

Fork branch `unit/M7-el3-platform` from `rzv2l-dev` `10df946cc8`; project branch of the same name from `main` `f15f61e`.

SYC direct-mode start state (`CNTCR` 1, `CNTFID0` 24 MHz, EVK-R50): the M1 device check sees `direct-boot = true`; no direct-mode guest reads the values, so no mutation proves them.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | BL31 build at the BSP's commit and flags, reproducible (the banner's build time is the commit) | `tests/guests/fw/build-tf-a.sh` | SHA-256 the same over two builds | done |
| T2 | Register evidence: BL2's hand-off, the registers BL31 touches, the core power sequences | `docs/research/el3-platform.md` | review of the page | done |
| T3 | SYC: CoreSight timestamp generator control frame | fork `hw/timer/coresight_tsgen.c` | qtest `/rzv2l-smarc/syc` | done |
| T4 | TZC-400 register file; TZC0-3 in the SoC; the two SRAMs | fork `hw/misc/arm_tzc400.c`, `hw/arm/r9a07g054.c` | qtest `/rzv2l-smarc/tzc`; M1 memory map | done |
| T5 | SYSC: Cortex-A55 reset vectors, sleep request flags | fork `hw/misc/renesas_rzg2l_sysc.c` | qtest `/rzv2l-smarc/sysc/ca55` | done |
| T6 | CPG: core P-Channels, core run lines; the SoC starts and stops the cores from them | fork `hw/misc/renesas_rzv2l_cpg.c`, `hw/arm/r9a07g054.c` | qtests `/cpg/pchannel`, `/cpg/ca55-run`; firmware boot | done |
| T7 | GIC-600 `GICR_PWRR`; Cortex-A55 `CPUPWRCTLR_EL1` | fork `hw/intc/arm_gicv3_*`, `target/arm/tcg/cpu64.c` | firmware boot, hotplug | done |
| T8 | Firmware mode (`-bios`): BL2's hand-off, CPU0 start stub, BL33 kernel and DTB; QEMU board doc | fork `hw/arm/rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` | firmware boot | done |
| T10 | EL3 probe: `GICR_PWRR` rules from EL3 and RAZ/WI from Non-secure EL1; TZC refuses Non-secure accesses (EVK-R79) | `tests/probes/el3-secure/`, fork `hw/misc/arm_tzc400.c` | EL3 probe, 16 checks | done |
| T9 | Acceptance: firmware boot, CPU1 hotplug, reset; M1 expectations for the new devices; `run.sh --firmware` | `tests/acceptance/m7/`, `tests/acceptance/m1/expected/`, `scripts/run.sh` | M7 ACCEPTANCE | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | SYSC: a sleep request sets its flag whatever `LP_CTL6` masks | `rzv2l-smarc-test.c:238 test_sysc_ca55`: `0x00000300 == 0x00000200` |
| 2 | SYSC: `RVALn` keeps bits 1:0 | `rzv2l-smarc-test.c:228 test_sysc_ca55`: `0xffffffff == 0xfffffffc` |
| 3 | CPG: `PACCEPT` never rises | `rzv2l-cpg-test.c:350 test_pchannel`: `0x00000000 == 0x00000001` |
| 4 | TZC: `NO_OF_FILTERS` holds the count, not count - 1 | `rzv2l-smarc-test.c:269 test_tzc`: `2 == 1` |
| 5 | TZC: the gate keeper takes 4 filters on every controller | `rzv2l-smarc-test.c:276 test_tzc`: `0x000f000f == 0x00010001` |
| 6 | SYC: `CNTCR` keeps every bit written | `rzv2l-smarc-test.c:303 test_syc`: `0xffffffff == 0x00000003` |
| 7 | SoC: a starting core takes core 0's reset vector | `firmware.py:93 boot_checks`: `FAIL boot 1: CPU1 booted through BL31's CPU_ON; CPUs online 0-1` |
| 8 | CPG: a P-Channel OFF request is ignored | `rzv2l-cpg-test.c:395 test_ca55_run`: `'qtest_get_irq(qts, 1)' should be FALSE` (the firmware boot stayed green: BL31's `CPU_ON` also applies the core's reset, which stops it; the qtest was added for this) |
| 9 | GIC: `GICR_PWRR.RDPD = 0` writes ignored | `firmware.py:82 boot_checks`: `FAIL boot 1: the card's init reaches the shell` (BL31 waits for the Redistributor) |
| 10 | CPU: no `CPUPWRCTLR_EL1` on the Cortex-A55 | `firmware.py:131 main`: `FAIL hotplug 1: CPU1 offline (BL31 CPU_OFF): CPUs online 0` |
| 11 | Board: BL33's entry point at offset 48 (the R-Car layout) | `firmware.py:82 boot_checks`: `FAIL boot 1: the card's init reaches the shell` |
| 12 | CPG: a core runs with `CA55_RST3_n` applied | `rzv2l-cpg-test.c:389 test_ca55_run`: `'qtest_get_irq(qts, 1)' should be FALSE` (green until the test applied `CA55_RST3_1` alone) |

| 13 | SYSC: `RVAL1` resets to 0 | `rzv2l-smarc-test.c:228 test_sysc_ca55`: `0x00000000 == 0x00020000` |
| 14 | SoC: the TZCs accept Non-secure accesses | `probe.c:228`: `FAIL TZC0 BUILD_CONFIG read from Non-secure: external abort: 0x…0 (expected 0x…1)` |
| 15 | GIC: `GICR_PWRR` RAZ/WI to every access | `probe.c:174`: `FAIL GICR1_PWRR RDG/RDGO: 0x…0 (expected 0x…100)` (the firmware boot stayed green: BL31 reads RAZ as powered up) |
| 16 | GIC: `GICR_PWRR` open to Non-secure accesses | `probe.c:221`: `FAIL GICR1_PWRR from Non-secure: RAZ: 0x…100 (expected 0x…0)` |
| 17 | GIC: `RDPD = 1` taken without `ProcessorSleep` | `probe.c:184`: `FAIL RDPD 1 without ProcessorSleep: ignored: 0x…1 (expected 0x…0)` |
| 18 | GIC: `RDGPD` never follows the group | `probe.c:195`: `FAIL RDPD 1 on both: GICR0 state: 0x…1 (expected 0x…d)` |
| 19 | GIC: `RDAG` ignored | `probe.c:202`: `FAIL RDAG with RDPD 0 from core 0: GICR1 state: 0x…1 (expected 0x…0)` |

Each mutation was applied to a copy-backed file, built with a confirmed relink, run alone, and restored; the build and the full tests were run again after the last one.

## Boot evidence (fork `55a1e7877a`; the last fork commit adds the SYC direct-mode start state only)

`QEMU=build/qemu/qemu-system-aarch64 python3 -I tests/acceptance/m7/firmware.py OUT`: 16 checks PASS. BL31 `8f8837388094b930…` (`tests/guests/fw/build-tf-a.sh`); the serial log, in order:

```
NOTICE:  BL31: v2.10.5(release):2.10.5/rz_1.1.0
ERROR:   Error initializing runtime service opteed_fast
[    0.000000] psci: PSCIv1.1 detected in firmware.
[    0.000000] psci: SMC Calling Convention v1.4
[    0.096036] CPU1: Booted secondary processor 0x0000000100 [0x412fd050]
[    0.099643] smp: Brought up 1 node, 2 CPUs
SD-ROOT: ready, root /dev/mmcblk0p2, boot 1
[    7.276972] psci: CPU1 killed (polled 0 ms)
[    7.332880] CPU1: Booted secondary processor 0x0000000100 [0x412fd050]
[    7.427166] psci: CPU1 killed (polled 0 ms)
[    7.477940] CPU1: Booted secondary processor 0x0000000100 [0x412fd050]
[    9.662733] reboot: Restarting system
NOTICE:  BL31: v2.10.5(release):2.10.5/rz_1.1.0
[    0.107622] smp: Brought up 1 node, 2 CPUs
SD-ROOT: ready, root /dev/mmcblk0p2, boot 2
```

The `-d` log holds only the recorded stub windows of `tests/acceptance/m4/expected/log-allow.txt`. qtests: `rzv2l-smarc-test` 9/9, `rzv2l-cpg-test` 7/7, the other RZ/V2L qtests unchanged and passing; M1 acceptance PASS with the new devices.

## Not covered (later scope, from the review)

- `LP_CTL1`, `LP_CTL2` and `LP_CTL5` are never cleared by BL31, so from the second `CPU_OFF` on, BL31's poll is met by the flag the first one left; the model's rule (the flag rises with an unmasked request) is exercised once per boot. The rule is an assumption from §6.3.56; the second hotplug round proves the `CPU_ON` path from the off state, not the sleep flag again.
- The P-Channel `OFF_EMU` request (`PSTATE` 1, the manual's §2.2.2 flows) has no test; BL31 uses OFF (0).
- `CPUPWRCTLR_EL1` (RAZ/WI) is checked only by the firmware boot; the Cortex-A55 TRM is not in the repo, so its reset value is not checked.
- The kernel's `rcar_canfd ... reset controller failed: -ETIMEDOUT` and the clock `WARNING` after it appear in direct mode too: not from this unit; a lead for the CAN-FD window.
