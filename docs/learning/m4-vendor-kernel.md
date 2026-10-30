# M4: the vendor kernel

> **Context.** Milestone M4 (spec [§17](../spec/project.md#17-milestones)): Renesas's own kernel and device tree (G1) boot to the same BusyBox shell as M3, and the watchdog works. Unit M4-vendor-kernel: [spec](../units/M4-vendor-kernel/spec.md), [tasks](../units/M4-vendor-kernel/tasks.md). The manual chapter is §21 (watchdog timer) and §7.2.4.182-183 (its CPG registers).

## 1. The vendor kernel and the watchdog (unit M4-vendor-kernel)

### 1.1 What the kernel needs

The vendor kernel is `rz_linux-cip`: the same Linux version as G0 (6.12.59) plus CIP and Renesas patches. `tests/guests/g1/build-kernel.sh` builds it from the public repository with its own `defconfig`, which is what Renesas's Yocto recipe does. The main difference from mainline is the configuration, not the code. The vendor `defconfig` builds in many drivers that mainline builds as modules: the display (MIPI DSI), CAN-FD, the QSPI controller, the USB function controller and others. Each of these probes at boot. So the first vendor boot aborted twice before the console, first in the DSI driver and then in CAN-FD, on windows that were not mapped. The device map already gave each of them a class (a logged stub), so mapping them was the fix.

The watchdog driver, `rzg2l_wdt.c`, is the same file in both kernels. Its probe touches no register: the watchdog runs only after user space opens `/dev/watchdog`.

### 1.2 How the watchdog is shaped

`qemu/hw/watchdog/renesas_rzg2l_wdt.c` models one channel; the SoC has three (A55 core 0, A55 core 1, M33). The counter is computed from virtual time at 24 MHz, as the OS timer's is. One QEMU timer fires at each overflow:

| Overflow | INTDISP before | Result |
|---|---|---|
| first | 0 | INTDISP = 1, WDTINT interrupt |
| second | still 1 (no ping) | WDTRSTB: a reset request |

A ping is a write of 1 to INTDISP. It clears the interrupt and restarts the count (§21.3.4).

A reset request does not reset the chip by itself. It goes to the CPG, and the CPG resets the system only if `CPG_WDTRST_SEL` allows it for that channel. The reset value masks all three channels, and firmware unmasks them. The CPG then records the channel in `CPG_WDTOVF_RST`, a flag that survives the reset it reports. In the model, the CPG calls QEMU's watchdog action, so `-action watchdog=...` decides what a reset means (the default resets the machine).

Linux cannot stop a running watchdog through its registers: once WDTEN is set, only a reset stops it (§21.3.1). So Linux stops it by applying the channel's reset line in the CPG (`CPG_RST_WDT`). The model wires that line from the CPG to each channel.

**Worked example: U-Boot's 60 s.** The EVK reads WDTSET as `0x2AE00000` at the U-Boot prompt (EVK-R40). WDTTIME is bits 31:20, so `0x2AE` = 686. One cycle is (686 + 1) × 1024 × 1024 clocks at 24 MHz = 30.0 s, and the reset comes at the second overflow: 60 s, the timeout U-Boot prints.

### 1.3 The proof

`rzv2l-wdt-test.c` checks the reset values, the 24 MHz count, the first and second overflow, the CPG mask and flag, the forced parity error and the reset line. Fifteen mutations each turn one check red ([tasks](../units/M4-vendor-kernel/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)). The acceptance run starts BusyBox's `watchdog` on the vendor kernel three ways: pinged (no reset), stopped (no reset), and started with no ping, which resets the board and leaves `CPG_WDTOVF_RST` = 1.

## 2. Pitfalls

- **A defconfig is part of the guest.** Mainline and the vendor kernel share almost all code here, but the vendor `defconfig` builds in drivers that mainline leaves as modules, so the vendor kernel probes a dozen more blocks at boot. Compare the effective `.config` files before predicting a boot (`tests/guests/out/g1/linux/.config`).
- **In QEMU, a watchdog reset should go through `watchdog_perform_action()`,** not a direct reset request. Then the user chooses the action with `-action watchdog=`, as for every other QEMU watchdog (`qemu/include/system/watchdog.h`).
- **The RZ/V2L watchdog cannot reset the chip until firmware allows it.** `CPG_WDTRST_SEL` resets to `0x88`: every channel's system reset masked (§7.2.4.183 p.460). A model that resets on every second overflow resets in firmware mode where the silicon would not.
- **A watchdog that cannot be stopped needs its reset line.** Linux stops it by applying the CPG reset, and changes a running timeout by a stop and a start. Without the reset line, a stopped watchdog keeps counting and resets the board later (`rzg2l_wdt.c:126-140`).
- **"Reset" has two directions here.** The CPG's `RST_WDT` resets the watchdog; the watchdog's WDTRSTB resets the system through the CPG. They are separate lines in the model.
- **A flag that reports a reset must survive it.** The manual says `CPG_WDTOVF_RST` identifies the channel after the release from the reset it caused (§7.2.4.182 p.459), so the model keeps it outside the reset values. `CPG_WDTRST_SEL`, by contrast, goes back to its initial value on a system reset. That is an inference: the note to §7.2.4.183 (p.461) says only that a system reset returns its bit 7 to the initial value.
- **A reset request is a level, not an event.** If WDTRSTB is asserted while the CPG masks it, the request is still held when firmware unmasks it later, and the reset then happens. An edge-only model would lose it.
- **The real board starts with the watchdog running.** U-Boot autostarts WDT0 with 60 s (EVK-R40). Direct mode starts it stopped on purpose (device map gap 16): a guest without a watchdog daemon would reset after a minute.
