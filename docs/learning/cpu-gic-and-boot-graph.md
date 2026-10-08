# CPUs, GIC, timers and the boot dependency chain in plain terms

Companion to `../research/cpu-gic.md` and `../research/boot-dependency-graph.md`.

## The CPU cluster

Two Cortex-A55 cores (r2p0) share a 256 KB L3 cache; there is no L2. Each core has an identity number, its **MPIDR**:

| Core | MPIDR | Who starts it |
|---|---|---|
| CPU0 | `0x000` | the boot ROM starts it at power-on |
| CPU1 | `0x100` | sleeps until software asks firmware to start it |

"Asking firmware" is **PSCI**, a standard Arm firmware API. Linux executes an `SMC` instruction meaning "CPU_ON(0x100, entry address)", and TF-A on the board, or QEMU's built-in PSCI in our first stage, wakes the core. QEMU numbers cores 0, 1 by default, so the machine must set 0x0 and 0x100, or Linux's CPU_ON request names a core that doesn't exist.

**Exception level.** On the board, Linux starts at EL1, the normal OS level. It is not handed EL2, the hypervisor level. QEMU must do the same (`has_el2=false`).

## The GIC: the interrupt switchboard

Every interrupt in the chip goes through the GIC-600 (a GICv3 design). Three kinds:

| Kind | Range | Example |
|---|---|---|
| SGI (software-generated) | 0–15 | one CPU poking another |
| PPI (private per CPU) | 16–31 | each core's own timer: virtual timer = PPI 11 = interrupt ID 27 |
| SPI (shared peripherals) | 32+ | UART, SD, Ethernet…; 480 implemented on this chip |

The GIC has two parts:
- **Distributor** (`0x11900000`): one per chip; routes SPIs to cores.
- **Redistributors** (`0x11940000` for CPU0, `0x11960000` for CPU1, `0x20000` apart): one per core; handle that core's SGIs and PPIs.

The board log confirms all of these numbers. QEMU already has a good GICv3 model; we only place it at the right addresses with the right sizes. One gap: QEMU reports a fixed GIC identity value that differs from the real GIC-600.

## Timers

1. **The Arm generic timer**, inside each core, ticks at the **counter frequency**: 24 MHz on this board. Linux reads the frequency from the `CNTFRQ` register, because the device tree doesn't say. QEMU defaults to 62.5 MHz, so the machine must set 24 MHz or all kernel timing is off by a factor of 2.6.
2. **OSTM**, the SoC's own timers (`0x12801400`, `0x12801800`), ticks at 100 MHz. Linux prefers the faster clock, so OSTM1 becomes the kernel's `sched_clock` (the board log shows `sched_clock: 32 bits at 100MHz`). Two traps for the model:
   - if OSTM is missing, early accesses fault, or the clock freezes silently;
   - stopping the timer means writing "stop" (TT) and waiting until "running" (TE) reads 0, with **no timeout**. A stub that never clears TE hangs the boot.

## The boot dependency chain: who needs whom before the first character

**(a) Earlycon, the very first output.** Before almost anything is set up, Linux pokes the UART registers directly. It needs only the CPU, RAM, and SCIF0's transmit path. It also needs `earlycon` on the kernel command line: a recorded "fidelity gap", because the upstream DT doesn't include it.

**(b) The real console (`ttySC0`).** This one is a chain of drivers, each waiting for the previous:

```
GIC + generic timer (24 MHz) + PSCI           core infrastructure
        │
SYSC device-ID read                           "is this an RZ/V2L?"
        │
CPG probes (once, no retry)                   clocks + resets for everyone
        │
IRQC probes ── needs CPG clock/reset
        │
OSTM probes ── needs CPG; becomes sched_clock
        │
Pin control probes ── needs IRQC (GPIO interrupts)
        │
SCIF0 probes ── needs CPG clock+reset, pins applied
        │
ttySC0 console: first character via the real driver
```

If any link is missing, everything below it waits. For the CPG there is no second chance (a failed probe is permanent), and without pin control the UART waits forever. That is why M3b ("real console") needs faithful CPG, pin-control, IRQC and OSTM models, not just a UART.

**Everything else** enabled in the device tree (watchdog, DMA, I²C, SD, USB…) must at least be *mapped* by M3b, so its driver fails softly instead of crashing the boot with an access fault.

## Known gaps in QEMU's first stage (direct kernel boot)

| Board | QEMU stage A | Why |
|---|---|---|
| SMCCC v1.4 | v1.0 | QEMU's built-in PSCI doesn't implement the version call |
| `SCR_EL3.FIQ=1` | 0 | set by TF-A on the board; absent without firmware |
| GIC-600 identity | QEMU's generic value | hard-coded in QEMU |

These are listed, not hidden: the project's fidelity rule.

## Spot checks (HW manual Rev 1.50, printed page numbers)

| # | Page | Topic | Confirm |
|---|---|---|---|
| 1 | p.83, §2.1, Tables 2.1–2.2 | CPU | Cortex-A55 **r2p0**, L2 = none, L3 = 256 KB |
| 2 | p.143, §5.2.1, Table 5.1 (1/3) | memory map | DDR at `0x0_4000_0000`; GIC window `0x1190_0000`–`0x119F_FFFF`; OSTM/GTM ch0–2 at `0x1280_1000`/`1400`/`1800` |
| 3 | p.530, §8.1 | GIC | GIC-600; 32 priority levels; 16 PPIs; 480 SPIs; LPIs not supported |
| 4 | p.534, §8.2, Table 8.2 | PPIs | virtual timer `nCNTVIRQ` = PPI 11 (ID 27); physical timer PPI 14; PMU PPI 7; maintenance PPI 9 |
| 5 | p.1224, §20.1.1, Table 20.2 | OSTM | the base addresses |
| 6 | pp.1229–1230, §20.2.2.3 / §20.2.2.5 | OSTM | TE reflects "counter running"; writing TT stops it and clears TE (the driver waits for that with no timeout) |
