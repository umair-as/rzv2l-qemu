# M4: the vendor kernel

> **Context.** Milestone M4 (spec [§17](../spec/project.md#17-milestones)): Renesas's own kernel and device tree (G1) boot to the same BusyBox shell as M3, and the watchdog works. Unit M4-vendor-kernel: [spec](../units/M4-vendor-kernel/spec.md), [tasks](../units/M4-vendor-kernel/tasks.md). Unit M4-loader-fixups: [spec](../units/M4-loader-fixups/spec.md), [tasks](../units/M4-loader-fixups/tasks.md). The manual chapter is §21 (watchdog timer) and §7.2.4.182-183 (its CPG registers).

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

## 2. U-Boot's device-tree edits (unit M4-loader-fixups)

This section shows how QEMU's loader stands in for U-Boot's edits to the kernel's device tree. On the EVK, U-Boot edits the DTB after it loads it and before it starts Linux. With `-kernel`, no U-Boot runs, so each edit must be made by QEMU or listed as a gap (REQ-GUEST-005).

### 2.1 What U-Boot edits

The EVK log shows the edits (EVK evidence §4):

```
Changing the current FDT in beaf4000.
   Config Node /soc/mmc@11c00000
	Set property vmmc-supply : <&/regulator-vcc-sdhi0>
   Config Node /soc/mmc@11c00000
	Set property vqmmc-supply : <&/regulator-vccq-sdhi0>
```

The EVK runs a G2 image, so its U-Boot is the vendor U-Boot plus the image's own patches. The first step was to sort each edit by its source. Only the vendor's edits are the contract:

- The SD0 supply edit is vendor code. It applies only if the boot mode pins select eSD (`rzv2l-dev.c:269-292`, U-Boot `4eebfbaa4e`).
- `kaslr-seed` comes from `ft_board_setup()`. Only the G2 patches enable it. The vendor `defconfig` does not set `OF_BOARD_SETUP`.
- `u-boot,version` and the bootargs from the U-Boot environment are vendor edits. QEMU does not write them (spec "For the operator").

The full list, with each condition and what QEMU does, is in the [unit spec](../units/M4-loader-fixups/spec.md#scope).

### 2.2 How the edit is made

`struct arm_boot_info` has a hook, `modify_dtb`, that QEMU's loader calls after its own edits (`/memory`, `/chosen`, `/psci`) and before it copies the DTB into guest RAM (`qemu/hw/arm/boot.c:632-633`). The board sets the hook (`qemu/hw/arm/rzv2l-smarc.c:118`). If the machine property `boot-mode` is 0 (eSD), the hook sets the two supply properties (`qemu/hw/arm/rzv2l-smarc.c:90-100`). `boot-mode` is the same value the SoC shows in `SYS_LSI_MODE[2:0]`, which U-Boot reads.

The hook copies three details of U-Boot's `update_fdt()`:

1. A supply points at the regulator by its phandle.
2. If the regulator has no phandle, it gets the highest phandle in the tree plus 1. QEMU calls the same libfdt function as U-Boot, `fdt_generate_phandle()` (`qemu/hw/arm/rzv2l-smarc.c:68`).
3. If the regulator node does not exist, the property keeps its value. The Linux DTBs have no `/regulator-vcc-sdhi0`, so only `vqmmc-supply` changes: from `0x18` (`regulator-1p8v`) to `0x74` (`regulator-vccq-sdhi0`).

### 2.3 The proof

`-machine dumpdtb=<file>` writes the DTB that the loader built, after the hook, and stops QEMU before the guest runs. `tests/acceptance/m4/loader-fixups.sh` uses it for the G0 and G1 DTBs in eSD and eMMC mode. It compares the result with the DTB file. A third case removes the regulator's phandle and expects the next free one. Three mutations turn the check red ([tasks](../units/M4-loader-fixups/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)).

## 3. Pitfalls

- **A defconfig is part of the guest.** Mainline and the vendor kernel share almost all code here, but the vendor `defconfig` builds in drivers that mainline leaves as modules, so the vendor kernel probes a dozen more blocks at boot. Compare the effective `.config` files before predicting a boot (`tests/guests/out/g1/linux/.config`).
- **In QEMU, a watchdog reset should go through `watchdog_perform_action()`,** not a direct reset request. Then the user chooses the action with `-action watchdog=`, as for every other QEMU watchdog (`qemu/include/system/watchdog.h`).
- **The RZ/V2L watchdog cannot reset the chip until firmware allows it.** `CPG_WDTRST_SEL` resets to `0x88`: every channel's system reset masked (§7.2.4.183 p.460). A model that resets on every second overflow resets in firmware mode where the silicon would not.
- **A watchdog that cannot be stopped needs its reset line.** Linux stops it by applying the CPG reset, and changes a running timeout by a stop and a start. Without the reset line, a stopped watchdog keeps counting and resets the board later (`rzg2l_wdt.c:126-140`).
- **"Reset" has two directions here.** The CPG's `RST_WDT` resets the watchdog; the watchdog's WDTRSTB resets the system through the CPG. They are separate lines in the model.
- **A flag that reports a reset must survive it.** The manual says `CPG_WDTOVF_RST` identifies the channel after the release from the reset it caused (§7.2.4.182 p.459), so the model keeps it outside the reset values. `CPG_WDTRST_SEL`, by contrast, goes back to its initial value on a system reset. That is an inference: the note to §7.2.4.183 (p.461) says only that a system reset returns its bit 7 to the initial value.
- **A reset request is a level, not an event.** If WDTRSTB is asserted while the CPG masks it, the request is still held when firmware unmasks it later, and the reset then happens. An edge-only model would lose it.
- **The real board starts with the watchdog running.** U-Boot autostarts WDT0 with 60 s (EVK-R40). Direct mode starts it stopped on purpose (device map gap 16): a guest without a watchdog daemon would reset after a minute.
- **A board's firmware edits the device tree, so a DTB file is not what the kernel sees.** In QEMU, the `modify_dtb` hook of `struct arm_boot_info` is the place for such edits, and `-machine dumpdtb` shows the result. On the EVK, U-Boot changes SD0's `vqmmc-supply` in eSD mode (EVK evidence §4).
- **A log from a product image mixes vendor and product edits.** The EVK's U-Boot prints `kaslr-seed=ok`, but that edit comes from the G2 image's patches, not from the vendor U-Boot. Sort each edit by its source before you model it (`rzv2l-dev.c:269-292` is vendor; `ft_board_setup()` needs `OF_BOARD_SETUP`).
- **U-Boot can name a node that does not exist.** The vendor U-Boot sets `vmmc-supply` to `/regulator-vcc-sdhi0`, which no Linux DTB for the board has, so the property keeps its old value. A loader that writes 0 or fails here would differ from the board (`update_fdt.c:84-85,173-178`).
