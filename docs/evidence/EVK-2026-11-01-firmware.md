# EVK 2026-11-01: firmware services seen from Linux, TZC access from U-Boot

**Board:** RZ/V2L SMARC EVK, console on SCIF0 (115200 8N1).

**Image:** EDGE AI OS 0.1.0, the same image as [`EVK-2026-10-30-linux.md`](EVK-2026-10-30-linux.md) (a G2 image: a product built on the Renesas BSP). `uname -r`: `6.12.59-cip14-yocto-standard-gfb76169f9315`. Firmware banners on this boot: BL2/BL31 `v2.10.5(release):2.10.5/rz_1.1.0-dirty` (built 13:04:30, Sep 25 2025), OP-TEE `82a5cd3b-dev`, U-Boot 2024.07 (Sep 22 2025).

**Method:** the operator typed the commands; the output was copied from the console. A: Linux root shell, read-only `dmesg` and `/sys`. B: U-Boot prompt, four `md.l` reads. The raw console output is kept by the operator.

All values are **hardware observations (O)** for this image.

## A. PSCI and SMCCC as Linux finds them (EVK-L07)

**Question:** what does the board's firmware answer to `MIGRATE_INFO_TYPE` (gap 5), and do the CPU vulnerability reports that depend on the SMC Calling Convention version differ from QEMU's (gap 1)?

```
$ dmesg | grep -iE 'trusted os|migrat|smccc|psci'
[    0.000000] psci: probing for conduit method from DT.
[    0.000000] psci: PSCIv1.1 detected in firmware.
[    0.000000] psci: Using standard PSCI v0.2 function IDs
[    0.000000] psci: Trusted OS migration not required
[    0.000000] psci: SMC Calling Convention v1.4
[    0.054086] Timer migration: 1 hierarchy levels; 8 children per group; 1 crossnode level
[    0.545784] SMCCC: SOC_ID: ARCH_SOC_ID not implemented, skipping ....
$ grep . /sys/devices/system/cpu/vulnerabilities/*
```

All 17 files read `Not affected`, except `spectre_v1`: `Mitigation: __user pointer sanitization`.

The same commands in QEMU, with the Renesas kernel `6.12.59-cip14-g212f6e88b724` (G1) booted from the SD card (the kernels differ: product kernel on the board, vendor kernel in QEMU):

| Line | EVK (BL31 + OP-TEE) | QEMU firmware mode (BL31, no OP-TEE) | QEMU direct mode (QEMU's PSCI) |
|---|---|---|---|
| PSCI version, function IDs | 1.1, v0.2 IDs | same | same |
| SMCCC | v1.4 | v1.4 | v1.0 |
| `MIGRATE_INFO_TYPE` | `Trusted OS migration not required` | `MIGRATE_INFO_TYPE not supported.` | `Trusted OS migration not required` |
| `SMCCC: SOC_ID` line | `ARCH_SOC_ID not implemented` | same | absent (needs SMCCC 1.1) |
| `vulnerabilities/*` | as above | identical | identical |

**Reading (I, from TF-A `f59ed5a31`):** BL31 answers `MIGRATE_INFO_TYPE` through the Secure OS dispatcher's hook, and returns NOT_SUPPORTED without one (`lib/psci/psci_common.c:1084`). The OP-TEE dispatcher registers the hook only after OP-TEE has initialised (`services/spd/opteed/opteed_main.c:568`); it then answers "not present or MP" (2, `services/spd/opteed/opteed_private.h:49,55`), which Linux prints as "Trusted OS migration not required". QEMU's firmware mode has no OP-TEE yet, so the line differs until it has.

## B. TZC-400 `BUILD_CONFIG` from U-Boot (EVK-R79)

**Question:** the address width of each TrustZone controller (`BUILD_CONFIG` bits 13:8), which the manual does not give.

```
=> md.l 0x11040000 1
"Synchronous Abort" handler, esr 0x96000010, far 0x11040000
...
Resetting CPU ...
```

The same for `0x11050000`, `0x11060000` and `0x11070000`, each on a fresh boot: every read aborted with `esr 0x96000010` and `far` at the register.

**Reading:** `ESR` `0x96000010` is a data abort at the current exception level (EC `0x25`) with fault status `0x10`, a synchronous external abort: the access was answered with a bus error, not refused by the MMU. U-Boot runs in the Non-secure world, so the four controllers' registers do not take Non-secure reads (O). Which layer refuses them, the controller's own register interface or the SoC's slave access control in front of it (SYSC `SLVACCCTL`), is not known. The address widths stay unread: only Secure software could read them.

**Side effect:** U-Boot's abort handler resets the CPU, so each read rebooted the board into BL2.

## C. The boot chain's banners (U-Boot `reset` after each read in B)

The order the next unit's firmware boot should follow, from one of B's reboots (G2 firmware: BL2 carries the product's `[EDGE]` line, U-Boot its autoboot prompt):

```
NOTICE:  BL2: v2.10.5(release):2.10.5/rz_1.1.0-dirty
NOTICE:  BL2: SYS_LSI_MODE: 0x10200
NOTICE:  BL2: SYS_LSI_DEVID: 0x18447447
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.10.5(release):2.10.5/rz_1.1.0-dirty
I/TC: OP-TEE version: 82a5cd3b-dev (gcc version 15.3.0 (GCC)) #1 Fri Nov 21 09:32:50 UTC 2025 aarch64
I/TC: Primary CPU initializing
I/TC: Primary CPU switching to normal world boot
U-Boot 2024.07 (Sep 22 2025 - 10:51:32 +0000)
CPU:   Renesas Electronics CPU rev 1.0
Model: smarc-rzv2l
DRAM:  1.9 GiB
I/TC: Reserved shared memory is enabled
I/TC: Dynamic shared memory is enabled
SF: Detected mt25qu512a with page size 256 Bytes, erase size 4 KiB, total 64 MiB
WDT:   Started watchdog@12800800 with servicing every 1000ms (60s timeout)
MMC:   sd@11c00000: 0, sd@11c10000: 1
Loading Environment from MMC... Reading from MMC(0)... OK
```

Lines left out: BL2 build line and PRR, OP-TEE's two configuration warnings, the second `WDT:` lines, the console lines. OP-TEE's `I/TC` lines after `DRAM:` are its answers to U-Boot's OP-TEE probe (I: U-Boot's `CONFIG_OPTEE` driver probes it by SMC).
