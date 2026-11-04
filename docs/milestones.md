# 🗺️ Milestones and progress

Where the project stands, what each milestone delivers, and what comes next. Exit criteria are in the [specification, §17](spec/project.md#17-milestones). The words used here (G0, UNIMP, …) are explained in [`README.md`](README.md).

✅ done · 🔄 in progress · ⏭️ next · ⏳ planned

## Where we are

**M3 is done: the plain upstream Linux kernel boots to a shell on the board's serial console, on both CPUs.** That completes the v1.0 target (M2 + M3). Traceability and requirement statuses are updated: 20 of 27 requirements verified, the rest planned for M4-M7 or noted ([traceability](spec/traceability.md)). **Tagged `rzv2l-v1.0`** (QEMU fork `rzv2l-dev` `aa1764973d`); the tag message lists the scope and the open requirements.

**M4 is done: Renesas's own kernel boots to the same shell, the watchdog resets the board, and QEMU's loader makes the vendor U-Boot's device-tree edit for an SD-card boot** (the edits it does not make are listed). **M5 is done: both kernels read and write ext4 on an SD card, and boot user space from a root file system on it, without an initramfs** ([walkthrough](walkthrough.md#m5-an-sd-card-with-ext4)). An eMMC for boot mode 1 is deferred. **M6 is done: both kernels reach the network through the board's Gigabit Ethernet and PHY, get a DHCP lease, and move data both ways with matching hashes, through link and reset changes** ([walkthrough](walkthrough.md#m6-ethernet)). **M7 is done: the board's own firmware after BL2 (TF-A BL31, OP-TEE without the closed crypto engine, the vendor U-Boot) boots Renesas's kernel from the SD card, Linux calls a trusted application in OP-TEE, and U-Boot and Linux read and write the module's QSPI flash** ([walkthrough](walkthrough.md#m7-the-boards-own-firmware)). That completes the v1.1 target (M4-M7). Requirement statuses and traceability are updated: 36 of 38 requirements verified; the boot-source register waits for the real BL2 (M8), and the TSIP negative test needs a production OP-TEE that cannot be built from public sources ([traceability](spec/traceability.md)). **Tagged `rzv2l-v1.1`**.

| | Release | Milestones | State |
|---|---|---|---|
| 🎯 | **v1.0** | M0-M3: upstream Linux to a shell | ✅ tagged `rzv2l-v1.0` |
| 🎯 | **v1.1** | M4-M7: Renesas's kernel, storage, networking, the board's firmware after BL2, the QSPI flash | ✅ tagged `rzv2l-v1.1` |
| 🎯 | v2 | M8-M9: the full boot chain, platform behaviour | 🔄 (M8 started) |

## Milestones

| | M | Milestone | What it delivers | Guest |
|---|---|---|---|---|
| ✅ | M0 | Research baseline | sources pinned, device map, boot dependency graph, EVK evidence | — |
| ✅ | M1 | Machine skeleton | `-M rzv2l-smarc`: 2× Cortex-A55, GIC-600, DDR, timer, SYSC ID registers | bare-metal probe |
| ✅ | M2 | First character | the serial port (SCIFA) model; `Hello from RZ/V2L` on SCIF0 | bare-metal probe |
| ✅ | M3 | Linux to a shell | clock controller, OS timer, pin and interrupt controllers; mainline Linux to a BusyBox shell, both CPUs | G0 |
| ✅ | M4 | Vendor kernel | Renesas's own kernel and device tree to the same shell; the watchdog; U-Boot's device-tree edits | G1 |
| ✅ | M5 | Storage | the SD controller with the real driver; ext4 root file system (real user space); eMMC deferred | G0, G1 |
| ✅ | M6 | Networking | Ethernet (ravb) and its PHY; DHCP, data checked both ways, link and reset recovery ([walkthrough](walkthrough.md#m6-ethernet)) | G0, G1 |
| ✅ | M7 | Real firmware | TF-A BL31 + OP-TEE (rebuilt without TSIP) + U-Boot, loading Linux from storage; the QSPI flash | G1 |
| 🔄 | M8 | Full boot chain | TF-A BL2 from an SPI flash image, with a DDR stub | G1 |
| ⏳ | M9 | Platform behaviour | A/B selection, bootcount, rollback, FIT signatures | G1 |

## Work units

Each milestone is built in units; each unit has a one-page spec and its proofs in [`units/`](units/).

| | Unit | Milestone | What it did |
|---|---|---|---|
| ✅ | [M1-machine-skeleton](units/M1-machine-skeleton/spec.md) | M1 | board, SoC, CPUs, GIC identity, SYSC ID registers |
| ✅ | [M2-first-character](units/M2-first-character/spec.md) | M2, M3a | serial port model; the mainline kernel's early console prints |
| ✅ | [M3b-cpg](units/M3b-cpg/spec.md) | M3 | clock and reset controller (CPG) |
| ✅ | [M3b-ostm](units/M3b-ostm/spec.md) | M3 | OS timer: kernel time and timer interrupts |
| ✅ | [M3b-pfc-irqc](units/M3b-pfc-irqc/spec.md) | M3 | pin controller and interrupt control unit; the real serial driver takes over the console |
| ✅ | [M3b-shell](units/M3b-shell/spec.md) | M3 | BusyBox initramfs; the M3 acceptance run |
| ✅ | [M4-vendor-kernel](units/M4-vendor-kernel/spec.md) | M4 | the vendor kernel to a shell; watchdog timers WDT0-2, reset through the CPG |
| ✅ | [M4-loader-fixups](units/M4-loader-fixups/spec.md) | M4 | U-Boot's device-tree edits: the SD0 supplies in eSD mode applied by QEMU, the others listed as gaps |
| ✅ | [M5-sdhi](units/M5-sdhi/spec.md) | M5 | the SD/MMC host interface and its DMA engine; an SD card on SDHI0 with ext4 |
| ✅ | [M5-sd-rootfs](units/M5-sd-rootfs/spec.md) | M5 | user space from an ext4 root file system on the SD card, both kernels; clean power-off and reset |
| ✅ | [M6-ravb](units/M6-ravb/spec.md) | M6 | Gigabit Ethernet (DMA rings, MDIO, checksum offload), the board's KSZ9131 PHYs, IRQ0-7 of the interrupt control unit |
| ✅ | [M7-el3-platform](units/M7-el3-platform/spec.md) | M7 | the board's TF-A BL31 as the PSCI firmware (firmware mode): CPU1 on and off, reset through WDT0 |
| ✅ | [M7-optee-uboot](units/M7-optee-uboot/spec.md) | M7 | OP-TEE (without the closed crypto engine) and the vendor U-Boot after BL31; U-Boot loads Linux from the SD card, the root chosen by PARTUUID ([walkthrough](walkthrough.md#op-tee-and-u-boot-after-bl31)) |
| ✅ | [M7-optee-linux](units/M7-optee-linux/spec.md) | M7 | Linux reaches OP-TEE: the project's TEE kernel (vendor source, `CONFIG_OPTEE`, a `/firmware/optee` overlay), `/dev/tee0`, a trusted-application call ([walkthrough](walkthrough.md#linux-and-op-tee)) |
| ✅ | [M7-rpc-spinor](units/M7-rpc-spinor/spec.md) | M7 | the SPI multi I/O bus controller and the module's MT25QU512A flash: U-Boot detects and reads it, Linux registers its partitions and reads and writes them, with the board's ID and SFDP ([walkthrough](walkthrough.md#the-qspi-flash)) |
| 🔄 | [M8-bl2-staging](units/M8-bl2-staging/spec.md) | M8 | the board's TF-A BL2 starts from the QSPI flash: the flash image, a stand-in for the boot ROM's copy, the CPG PLLs and SYSC access control BL2 programs; it runs to its first DDR access |

## The SoC blocks

What the model does with each block the guest touches. Classes: [`device-map.md`](device-map.md).

| | Block | State | Milestone |
|---|---|---|---|
| ✅ | Cortex-A55 ×2, GIC-600, generic timer | modelled; PSCI from QEMU, or from the board's TF-A BL31 in firmware mode | M1, M7 |
| ✅ | SYSC | ID and boot-mode registers; the cores' reset vectors and sleep flags; other offsets fail visibly | M1, M7 |
| ✅ | SYC (system counter), TZC0-3, on-chip SRAM | what the boot firmware programs; the TZCs store it, they do not filter | M7 |
| ✅ | SCIF0-4 (serial) | modelled | M2 |
| ✅ | CPG (clocks and resets) | modelled | M3 |
| ✅ | OSTM0-2 (OS timer) | modelled | M3 |
| ✅ | PFC (pins) | register file; pin electrical settings stored only | M3 |
| ✅ | IRQC (interrupt control) | register file; IRQ0-7 pin interrupts to the GIC; GPIO interrupts (TINT) and NMI not routed | M3, M6 |
| 🟡 | DMAC, USB PHY control | stubs that keep written values | later |
| ✅ | ETH0/1 (Gigabit Ethernet) + KSZ9131 PHYs | modelled: descriptor DMA, MDIO, checksum offload, link interrupts; the first `-nic` is ETH0 | M6 |
| 🟡 | I2C, USB host, thermal sensor | stubs: the drivers fail within a bound | later |
| 🟡 | display, CAN-FD, USB function, SSI, RSPI, ADC | stubs for the drivers the vendor kernel builds in | later |
| ✅ | QSPI (SPI multi I/O bus controller) + MT25QU512A flash | modelled: manual mode, the read window with its read cache; `-drive if=mtd`; HyperFlash, Octal-SPI and the write buffer not supported | M7 |
| ✅ | WDT0-2 (watchdog) | modelled; a watchdog reset resets the board through the CPG | M4 |
| ✅ | SDHI0/1 (SD/MMC host) | modelled with the built-in DMA engine, for SD cards; bus tuning (SCC) not modelled | M5 |
| ⏳ | TSIP (closed crypto) | fails visibly; OP-TEE is rebuilt without it | M7 |

🟡 a stub: logged, so every access is visible.

## Known differences from the board

The full list is [`device-map.md` §4](device-map.md#4-known-fidelity-gaps-req-guest-004-list-and-model-limits). The ones a user notices:

- Guest time runs about 1.6 % fast: QEMU ticks the 24 MHz counter every 41 ns (gap 18).
- In direct mode QEMU's built-in PSCI replaces TF-A; firmware mode (`-bios`, M7) runs the board's BL31 instead, with QEMU in BL2's place, and can continue with OP-TEE (rebuilt without the closed crypto engine) and the vendor U-Boot. The boot ROM, BL2 and DDR training do not run.
- With U-Boot, the project's cards name Linux's root by PARTUUID, not by the vendor's `root=/dev/mmcblk0p2`: without `mmc` aliases in the vendor device tree, Linux names the card `mmcblk0` or `mmcblk1` from boot to boot (gap 22, DR-0007). The vendor's own boot command still runs when a card's saved environment is cleared, and then loses its root about half the time.
- Ethernet links come up at 1 Gb/s full duplex at once and transfers take no wire time; flow control, the receive filters, wake-up and energy-efficient Ethernet are not modelled. A channel without `-nic` has no cable.
- The SD hosts run SD cards at high speed and 3.3 V, as the EVK does; eMMC cards and the faster tuned modes are not modelled. Without `--sd` the slots are empty.

## Side track: the bench

[`bench/`](../bench/) is a web front end for one emulated board: the serial console, start/pause/reset/stop, the `-d` log, the coverage list, the memory map against [`device-map.md`](device-map.md), QEMU's device tree, and a history of runs with a PASS/FAIL verdict. It uses stock QEMU interfaces only, so the fork does not know it exists. It is not an acceptance gate.

**Who it is for:** an embedded developer who has the real board and wants to see what the model does differently, and a team that has no board yet but must run and inspect the board's software.

| | What | State |
|---|---|---|
| ✅ | Runs: profiles, live console, controls, coverage and CSV, Map, Devices, Runs history, gdbstub | merged |
| ✅ | Look and use: instrument look in dark and light (contrast-tested), resizable panels, an address strip over the Map, search in logs, failed-run filter, a [guide with screenshots](../bench/GUIDE.md) | merged |
| ⏸️ | Further bench work | on hold: no milestone needs it |

**On hold, and why:** checked against the specification, the next bench ideas (importing runs made outside the bench, comparing runs, attaching to an external QEMU, an agent interface) serve no milestone or verification gate yet. The bench sees only the QEMU it starts. The tooling that does serve the gates (a coverage check shared by the acceptance runs, the boot loop and the bench, as DR-0004 planned, and diffs of the model against the EVK) belongs to the milestone work.

**What would reopen it:** a milestone that needs it, or a concrete use. The first one in view: following a QEMU's state in the browser away from the terminal.

## What comes next

1. ✅ **M5:** storage. [M5-sdhi](units/M5-sdhi/spec.md): both kernels read and write ext4 on an SD card. [M5-sd-rootfs](units/M5-sd-rootfs/spec.md): both boot user space from an ext4 root on the card, without an initramfs, and keep their files across power-off and reset. With this unit M5 is complete. An eMMC behind SDHI0 for boot mode 1 is deferred (operator's decision): nothing planned needs it yet.
2. ✅ **M6:** networking. [M6-ravb](units/M6-ravb/spec.md): both kernels get a DHCP lease through QEMU user networking and move data both ways with matching hashes.
3. ✅ **M7:** real firmware. [M7-el3-platform](units/M7-el3-platform/spec.md): the board's TF-A BL31 is the PSCI firmware for the vendor kernel, which boots from the SD card with both CPUs, takes CPU1 down and up, and resets the board. [M7-optee-uboot](units/M7-optee-uboot/spec.md): OP-TEE and the vendor U-Boot follow BL31, and U-Boot loads Linux from the card; the root is chosen by PARTUUID (DR-0007), and the vendor's default boot is a separate compatibility check. [M7-optee-linux](units/M7-optee-linux/spec.md): with the project's TEE kernel, Linux calls a trusted application in OP-TEE. [M7-rpc-spinor](units/M7-rpc-spinor/spec.md): the SPI multi I/O bus controller and the module's QSPI flash, which U-Boot and Linux read and write. With this unit M7 is complete (release `rzv2l-v1.1`).
4. 🔄 **M8:** the full boot chain. [M8-bl2-staging](units/M8-bl2-staging/spec.md): the board's BL2 starts from the QSPI flash and runs to its DDR set-up. ⏭️ Next in M8: a DDR controller and PHY stub that BL2's training completes against, then the full chain from BL2 to the Linux shell.
