# 🗺️ Milestones and progress

Where the project stands, what each milestone delivers, and what comes next. Exit criteria are in the [specification, §17](spec/project.md#17-milestones). The words used here (G0, UNIMP, …) are explained in [`README.md`](README.md).

✅ done · 🔄 in progress · ⏭️ next · ⏳ planned

## Where we are

**M3 is done: the plain upstream Linux kernel boots to a shell on the board's serial console, on both CPUs.** That completes the v1.0 target (M2 + M3). Traceability and requirement statuses are updated: 20 of 27 requirements verified, the rest planned for M4-M7 or noted ([traceability](spec/traceability.md)). **Tagged `rzv2l-v1.0`** (QEMU fork `rzv2l-dev` `aa1764973d`); the tag message lists the scope and the open requirements.

**M4 is done: Renesas's own kernel boots to the same shell, the watchdog resets the board, and QEMU's loader makes the vendor U-Boot's device-tree edit for an SD-card boot** (the edits it does not make are listed). **M5 (storage) has started:** its first unit spec is written.

| | Release | Milestones | State |
|---|---|---|---|
| 🎯 | **v1.0** | M0-M3: upstream Linux to a shell | ✅ tagged `rzv2l-v1.0` |
| 🎯 | v2 | M4-M9: vendor software, storage, networking, real firmware | 🔄 M5 (M4 done) |

## Milestones

| | M | Milestone | What it delivers | Guest |
|---|---|---|---|---|
| ✅ | M0 | Research baseline | sources pinned, device map, boot dependency graph, EVK evidence | — |
| ✅ | M1 | Machine skeleton | `-M rzv2l-smarc`: 2× Cortex-A55, GIC-600, DDR, timer, SYSC ID registers | bare-metal probe |
| ✅ | M2 | First character | the serial port (SCIFA) model; `Hello from RZ/V2L` on SCIF0 | bare-metal probe |
| ✅ | M3 | Linux to a shell | clock controller, OS timer, pin and interrupt controllers; mainline Linux to a BusyBox shell, both CPUs | G0 |
| ✅ | M4 | Vendor kernel | Renesas's own kernel and device tree to the same shell; the watchdog; U-Boot's device-tree edits | G1 |
| 🔄 | M5 | Storage | the SD/eMMC controller with the real driver; ext4 root file system (real user space) | G0, G1 |
| ⏳ | M6 | Networking | Ethernet (ravb) and its PHY; DHCP | G0, G1 |
| ⏳ | M7 | Real firmware | TF-A BL31 + OP-TEE (rebuilt without TSIP) + U-Boot, loading Linux from storage | G1 |
| ⏳ | M8 | Full boot chain | TF-A BL2 from an SPI flash image, with a DDR stub | G1 |
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
| 🔄 | [M5-sdhi](units/M5-sdhi/spec.md) | M5 | the SD/MMC host interface and its DMA engine; an SD card on SDHI0 with ext4 (in review) |

## The SoC blocks

What the model does with each block the guest touches. Classes: [`device-map.md`](device-map.md).

| | Block | State | Milestone |
|---|---|---|---|
| ✅ | Cortex-A55 ×2, GIC-600, generic timer | modelled; PSCI from QEMU | M1 |
| ✅ | SYSC | ID and boot-mode registers; other offsets fail visibly | M1 (rest M7) |
| ✅ | SCIF0-4 (serial) | modelled | M2 |
| ✅ | CPG (clocks and resets) | modelled | M3 |
| ✅ | OSTM0-2 (OS timer) | modelled | M3 |
| ✅ | PFC (pins) | register file; pin electrical settings stored only | M3 |
| 🟡 | IRQC (interrupt control) | register file; no external interrupts | M3 (routing M6) |
| 🟡 | DMAC, USB PHY control | stubs that keep written values | later |
| 🟡 | Ethernet, I2C, USB host, thermal sensor | stubs: the drivers fail within a bound | M6, later |
| 🟡 | display, CAN-FD, QSPI, USB function, SSI, RSPI, ADC | stubs for the drivers the vendor kernel builds in | later (QSPI: M7) |
| ✅ | WDT0-2 (watchdog) | modelled; a watchdog reset resets the board through the CPG | M4 |
| 🔄 | SDHI0/1 (SD/MMC host) | modelled with the built-in DMA engine, for SD cards; bus tuning (SCC) not modelled | M5 |
| ⏳ | TSIP (closed crypto) | fails visibly; OP-TEE is rebuilt without it | M7 |

🟡 a stub: logged, so every access is visible.

## Known differences from the board

The full list is [`device-map.md` §4](device-map.md#4-known-fidelity-gaps-req-guest-004-list-and-model-limits). The ones a user notices:

- Guest time runs about 1.6 % fast: QEMU ticks the 24 MHz counter every 41 ns (gap 18).
- QEMU's built-in PSCI replaces TF-A until M7; no OP-TEE until then.
- The stubbed eMMC makes the kernel retry for about 4.5 minutes after boot (until M5).

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

1. 🔄 **M5:** storage: the first unit, [M5-sdhi](units/M5-sdhi/spec.md), models the SD/MMC host interface and its DMA engine; both kernels read and write ext4 on an SD card (in review). Next in M5: a root file system on the card.
2. ⏳ After M5: M7 (firmware, needs M4 and M5); M6 when a boot path needs the network.
