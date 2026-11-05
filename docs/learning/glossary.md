# Glossary

This file explains the terms that the learning docs use, in four groups. Conventions and reading order: [`README.md`](README.md).

**Hardware: the chip and board**

| Term | Meaning |
|---|---|
| SoC | System on Chip: CPUs, interrupt controller, memory controller and peripherals on one die. Here the Renesas RZ/V2L, part number R9A07G054. |
| EVK | Evaluation Kit: the RZ/V2L SMARC board this project models; also the physical reference ("oracle") for measurements. |
| SYSC | System Controller, a Renesas block at `0x11020000`: product ID, captured boot pins, bus security and low-power control (manual §6.1.1). M1 models only its three ID/mode registers. |
| Register | A fixed-width value at an address inside a device; software reads or writes it to query or control the hardware. |
| Reset value | The value of a register directly after power-on or reset, before software writes it. |
| MMIO | Memory-mapped I/O: device registers reached with ordinary loads and stores at fixed addresses. |
| GIC | Generic Interrupt Controller (Arm). Collects interrupts from devices and delivers them to CPUs. The RZ/V2L has a GIC-600, which implements the GICv3 architecture. |
| GICD / distributor | The GIC part shared by all CPUs: enables, prioritises and routes shared interrupts. |
| GICR / redistributor | The per-CPU GIC part: that CPU's private interrupts and its connection to the distributor. |
| ITS | Interrupt Translation Service: GIC block for message-signalled interrupts (PCIe). The RZ/V2L has none. |
| SGI / PPI / SPI | Interrupt kinds by ID (INTID): software-generated (0-15), private per-CPU (16-31, for example the timers), shared peripheral (32 and up, for example a UART). |
| IIDR | Implementer Identification Register: the identification register of the GIC: implementer, product, revision. |
| TRM | Technical Reference Manual: Arm's document for one IP block, for example the GIC-600 TRM. |
| Cortex-A55 | The Arm CPU core in the RZ/V2L (two of them). |
| MPIDR / affinity | The CPU's own ID register; its affinity fields name the CPU (`0x0` and `0x100` here) and must match the DT `cpu@0`, `cpu@100`. |
| EL0-EL3 | Arm exception levels: EL0 applications, EL1 kernel, EL2 hypervisor, EL3 secure monitor (TF-A). |
| CNTFRQ | The generic timer's frequency register; 24 MHz on this board. |
| CPG | Clock Pulse Generator at `0x11010000` (manual §7): the PLLs, clock dividers, and every peripheral's clock gate, reset line and module stop. |
| CLK_ON | CPG clock-gate registers (`0x500`-`0x5E8`), one per peripheral group; bit n = 1 supplies clock n. Written with a write-enable mask. |
| CLK_MON | Clock monitors, CLK_ON + `0x180`, read-only: bit n = 1 once clock n is supplied. Linux polls it 10 µs after each CLK_ON write. |
| RST | CPG reset registers (`0x800`-`0x8E8`); bit n = 1 **releases** reset n. Written with a write-enable mask. |
| RSTMON | Reset monitors, RST + `0x180`, read-only, **inverted**: bit n = 1 while reset n is applied. Linux polls it 200 µs after each RST write. |
| MSTOP | CPG module-stop registers (`0xB60`-`0xB88`); 1 = the module is in its stop state. The pinned kernels never write them on RZ/V2L. |
| Write-enable mask | Renesas CPG convention: bit n + 16 of a write enables the write to the field starting at bit n; fields without it keep their value; the upper 16 bits read 0. |
| CLKSTATUS | CPG register whose bits are 1 while a divider or selector switch is in progress; Linux polls it only for the SD clock selector. |
| PLL1, SAMPLL1_CLK1/2 | The CPU PLL and its two setting registers; the reset values give 24 MHz × 100 / 2 = 1200 MHz. |
| PLn_DDIV, PLn_SSEL, PL2SDHI_DSEL | CPG divider and source-selector registers behind the bus and peripheral clocks (P0 = 100 MHz feeds SCIF and OSTM). |
| OSTM | OS Timer, three channels at `0x12801000` + n × `0x400`; the manual calls it GTM. Linux uses OSTM1 as a clock source and `sched_clock`. |
| GTM | The manual's name for OSTM, also the name of its CPG clock and reset registers (CLK_ON_GTM, RST_GTM). |
| SCIF / SCIFA | Serial ports, SCIF0-4 at `0x1004B800` + n × `0x400`; SCIF0 is the board console. |
| TSU | Thermal Sensor Unit at `0x10059400`; read-as-zero stub here, so Linux's probe fails with "Failed to start TSU". |
| EVK row ID (R10, X01 …) | A numbered register read in [`EVK-2026-10-29-post-firmware.md`](../evidence/EVK-2026-10-29-post-firmware.md); R = planned read, X = experimental read. |
| DIP switch / boot mode | Physical switches on the board that select the boot source; latched into `SYS_LSI_MODE` at power-on. |

**Software: firmware and guests**

| Term | Meaning |
|---|---|
| Guest | Software running inside the emulated machine (as opposed to the host, the PC running QEMU). |
| TF-A, BL2, BL31 | Trusted Firmware-A, the first firmware after the boot ROM. BL2 loads the next stages; BL31 stays resident at EL3 and serves PSCI. |
| FIP | Firmware Image Package: TF-A's container for the images BL2 loads (BL31, OP-TEE as BL32, U-Boot as BL33). Here at flash offset `0x20000`. |
| Boot ROM stand-in | QEMU's replacement for the boot ROM's serial-flash load in boot modes 3 and 4: it copies BL2 from the flash to on-chip RAM and starts it at EL3. The ROM code itself is not modelled. |
| U-Boot | The bootloader that loads Linux. |
| OP-TEE | The secure-world OS running beside Linux. |
| PSCI | Power State Coordination Interface: the firmware call Linux uses to power CPUs on and off (here via the `SMC` instruction). |
| DT / DTB | Device tree / device tree blob: the hardware description the kernel reads at boot. |
| DTB-U | The upstream device tree for the board (`r9a07g054l2-smarc.dtb`), built unmodified from the pinned kernel by `tests/guests/g0/build-dtb.sh`. |
| G0 / G1 / G2 | This project's guest tiers, that is, which software runs inside QEMU. **G0**: the plain upstream Linux kernel from kernel.org (v6.12.59, arm64 `defconfig`), the upstream device tree and a BusyBox shell; nothing in it is made for QEMU, and the same files would boot on the EVK. **G1**: Renesas's own software stack for the board (their kernel, TF-A, U-Boot, OP-TEE). **G2**: products built on G1; studied as samples, never a target. |

**QEMU**

| Term | Meaning |
|---|---|
| TCG | Tiny Code Generator: QEMU's CPU emulator, which translates guest ARM instructions into host x86 code ([`qemu-basics.md` §1](qemu-basics.md#1-what-qemu-is)). |
| KVM | Running the guest directly on the host CPU via the Linux kernel; needs a host of the same architecture, so not used here. |
| Memory region | QEMU's unit of the memory map: RAM, MMIO (callbacks) or a container ([`qemu-basics.md` §2](qemu-basics.md#2-the-memory-map)). |
| Memory map / `info mtree` | Which region owns which address; the monitor command prints it. |
| QOM | QEMU Object Model: types, objects and the composition tree a machine is built from ([`qemu-basics.md` §4](qemu-basics.md#4-objects-properties-realize)). |
| Property | A setting on a device, chosen by its creator before realize; the guest sees only its effect on registers ([`qemu-basics.md` §4](qemu-basics.md#4-objects-properties-realize)). |
| Realize | The step that switches a configured device on; it can refuse bad settings ([`qemu-basics.md` §4](qemu-basics.md#4-objects-properties-realize)). |
| Machine / board | The top-level QEMU object, selected with `-M` (here `rzv2l-smarc`). |
| Monitor | QEMU's command console (`info mtree`, `info qtree`, `xp`). |
| qtest | Test mode where a test program reads and writes addresses directly, with no guest CPU ([`testing.md` §1](testing.md#1-qtest-and-guest-probes)). |
| UNIMP / `unimplemented-device` | QEMU's stub device: logs every access under `-d unimp`, reads 0, ignores writes. "UNIMP" in the device map means a window mapped this way. |
| `retain-writes` | This project's option on `unimplemented-device`: reads return the last value written (the DMA controller and USB PHY control stubs). |
| Semihosting | A channel letting a guest program talk to QEMU, for example to report an exit status; used by the M1 probe. |

**This project's process**

| Term | Meaning |
|---|---|
| Milestone (M0, M1 …) | A stage of the project with exit criteria; M1 is the machine skeleton. |
| Unit | One reviewed piece of work in a milestone, with its own spec, design and tasks ([`docs/units/`](../units/)). |
| REQ-… | A project requirement ([`docs/spec/requirements.md`](../spec/requirements.md)). |
| AC | Acceptance criterion: a testable statement in a unit spec, for example M1-AC12. |
| Task (T01 …) | One implementation step of a unit, usually one commit (`tasks.md`). |
| DR | Decision record ([`docs/decisions/`](../decisions/)), for example DR-0003 on the GIC identity. |
| Fidelity class | How much of a device is modelled (FULL / FUNCTIONAL / STUB / UNSUPPORTED), and whether it fails honestly (honest-fault) or lies (silent-wrong, never allowed). |
| Mutation check | Breaking the model on purpose to prove a test can fail ([`testing.md` §1](testing.md#1-qtest-and-guest-probes)). |
| Device map / device-map row | [`docs/device-map.md`](../device-map.md): one row per hardware block with its address, IRQs, clocks, milestone and the class it is mapped with. |
| `direct-boot` | The device property that selects the direct-kernel start state; the board sets it when `-kernel` is given. |
| Direct-kernel / firmware mode | Two start states: QEMU boots Linux directly (devices start as firmware would leave them) or runs the real firmware (devices start at reset values). |
