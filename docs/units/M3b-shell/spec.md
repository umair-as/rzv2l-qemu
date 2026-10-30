# M3b-shell — spec

**Milestone:** M3 (last unit; it closes M3). **Requirements:** REQ-GUEST-001, REQ-GUEST-002, REQ-GUEST-004, REQ-MACH-003, REQ-MACH-004. **Status:** written 2026-10-30; implementation follows.

## Scope

- **No new device model.** After the pin and interrupt controller unit, the stock kernel boots to `No working init found` only because it has no root file system. This unit gives it one and proves the M3 criterion.
- **Guest artifact:** `tests/guests/g0/build-initramfs.sh` builds a static BusyBox 1.36.1 (aarch64, tarball checked against its pinned SHA-256) and a cpio with an `/init` that mounts `proc`, `sysfs` and `devtmpfs`, prints `G0-INIT: ready, cpus online <list>` and runs a shell on the console. `tc` is left out: it does not build against the v6.12 uapi headers. Nothing in the initramfs knows about QEMU.
- **Acceptance run:** `tests/acceptance/m3/`: M2 acceptance (which runs M1), then two cold boots of G0 with the initramfs, a shell session on SCIF0 over a socket, and a log gate.
- **Boot arguments:** none. The run passes no `-append`, so the kernel uses the DTB's own `bootargs` (`ignore_loglevel rw root=/dev/nfs ip=on`, `rzg2l-smarc-som.dtsi:29`). `earlycon` is not needed after the `sh-sci` takeover, so gap 6 of the device map stays M3a-only. The gaps of this run are QEMU's loader fixups: `/psci` (gap 7) and `/memory`, `linux,initrd-*` (gap 8). (Fact: the kernel command line in the serial log.)

## What the guest needs

- `-initrd`: the kernel unpacks the cpio (`CONFIG_BLK_DEV_INITRD=y`, `CONFIG_RD_GZIP=y`, effective `.config`) and runs `/init` (`init/main.c:162`). `root=/dev/nfs` is not used when `/init` exists.
- The console: `stdout-path = "serial0:115200n8"` (`rz-smarc-common.dtsi:32`) puts the console on `ttySC0`; the shell reads it through the SCIFA receive path (M2 model).
- Both CPUs: PSCI `CPU_ON` over SMC (`arch/arm64/kernel/psci.c:39-47`), from M1.
- Time: the generic timer and the OS timer (M1, OS timer unit).

## Exit criterion (the M3 acceptance list)

1. `sh-sci` takes over the console (`legacy console [ttySC0] enabled`).
2. A per-run command gets its response on `ttySC0`: the shell prints `<marker>-42` for `echo <marker>-$((6*7))`, a value the command line does not contain.
3. `/sys/devices/system/cpu/online` = `0-1`.
4. Time advances: `sleep 3` moves `/proc/uptime` by 3 s or more, and guest time runs at the host's rate within 5 %.
5. Every access in the `-d unimp,guest_errors,invalid_mem` log is to a window the device map classes UNIMP; no other line.
6. M1 and M2 acceptance still pass.
7. A second cold boot gives the same result.

## Evidence

Trial runs, 2026-10-30, fork `01168f7f3e`: `/init` runs at 18 s; checks 1-4 pass with the stock bootargs; the `-d` log names only the twelve UNIMP windows of the device map (ETH0/1, RIIC0/1/3, USB0/1 host, SDHI0/1, DMAC, TSU, USB PHY control). Pinned sources: `../../sources.md`.

## For the operator

- **Guest time runs about 1.6 % fast** (device map gap 18). QEMU ticks the generic counter every 41 ns, the truncated period of 24 MHz (`qemu/target/arm/cpu.c` `gt_cntfrq_period_ns`), so it counts at 24.39 MHz while `CNTFRQ` says 24 MHz. Fact from the QEMU source; seen as `sleep 3` taking 2.99 s of host time. It is generic QEMU code, deliberate upstream, not this project's model, so this unit records it and does not change it.

- **SDHI0 (eMMC, `non-removable`, `rzg2l-smarc-som.dtsi:369-378`) retries for about 4.5 minutes.** Every command to the read-as-zero stub waits out a 5 s timeout, and the MMC core keeps retrying: a message every 5 s until 268 s, 186 in all (a 600 s boot, 2026-10-30). Before `/init` the SD probes cost about 17 s. The class stays UNIMP, as the device map records; whether a read-as-zero SDHI is honest enough until M5 is your call.
