# 🗺️ Milestones and progress

Where the project stands, what each milestone delivers, and what comes next. Exit criteria are in the [specification, §17](spec/project.md#17-milestones). The words used here (G0, UNIMP, …) are explained in [`README.md`](README.md).

✅ done · 🔄 in progress · ⏭️ next · ⏳ planned

## Where we are

**M3 is done: the plain upstream Linux kernel boots to a shell on the board's serial console, on both CPUs.** That completes the v1.0 target (M2 + M3). Before the `rzv2l-v1.0` tag: one pass over traceability and requirement statuses.

| | Release | Milestones | State |
|---|---|---|---|
| 🎯 | **v1.0** | M0-M3: upstream Linux to a shell | ✅ milestones done; ⏭️ closure pass, then the tag |
| 🎯 | v2 | M4-M9: vendor software, storage, networking, real firmware | ⏳ |

## Milestones

| | M | Milestone | What it delivers | Guest |
|---|---|---|---|---|
| ✅ | M0 | Research baseline | sources pinned, device map, boot dependency graph, EVK evidence | — |
| ✅ | M1 | Machine skeleton | `-M rzv2l-smarc`: 2× Cortex-A55, GIC-600, DDR, timer, SYSC ID registers | bare-metal probe |
| ✅ | M2 | First character | the serial port (SCIFA) model; `Hello from RZ/V2L` on SCIF0 | bare-metal probe |
| ✅ | M3 | Linux to a shell | clock controller, OS timer, pin and interrupt controllers; mainline Linux to a BusyBox shell, both CPUs | G0 |
| ⏭️ | M4 | Vendor kernel | Renesas's own kernel and device tree to the same shell; the watchdog | G1 |
| ⏳ | M5 | Storage | the SD/eMMC controller with the real driver; ext4 root file system (real user space) | G0, G1 |
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
| ⏭️ | M4 unit page | M4 | to be written |

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
| 🟡 | SDHI0/1, Ethernet, I2C, USB host, thermal sensor | stubs: the drivers fail within a bound | M5, M6, later |
| ⏳ | WDT0 (watchdog) | not mapped | M4 |
| ⏳ | TSIP (closed crypto) | fails visibly; OP-TEE is rebuilt without it | M7 |

🟡 a stub: logged, so every access is visible.

## Known differences from the board

The full list is [`device-map.md` §4](device-map.md#4-known-fidelity-gaps-req-guest-004-list-and-model-limits). The ones a user notices:

- Guest time runs about 1.6 % fast: QEMU ticks the 24 MHz counter every 41 ns (gap 18).
- QEMU's built-in PSCI replaces TF-A until M7; no OP-TEE until then.
- The stubbed eMMC makes the kernel retry for about 4.5 minutes after boot (until M5).

## What comes next

1. ⏭️ **v1.0 closure:** traceability and requirement statuses, then the `rzv2l-v1.0` tag in both repositories.
2. ⏭️ **M4:** the unit page for the Renesas kernel (its kernel, device tree, the watchdog, loader fixups).
3. ⏳ M5 (storage, needs M4), then M7 (firmware, needs M4 and M5); M6 when a boot path needs the network.
