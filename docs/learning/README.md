# Learning notes

These are plain-language companions to the research notes in `../research/`. They are written for an engineer fluent in Linux, Yocto and embedded systems who is newer to register-level work: reading a hardware manual, then corroborating it against driver code and the physical board.

| Note | Covers |
|---|---|
| [reading-a-hardware-manual.md](reading-a-hardware-manual.md) | the general method: how a register page is laid out, how to verify a claim, and how the three sources of truth relate |
| [cpg-and-sysc.md](cpg-and-sysc.md) | clocks, resets and monitor registers; the SoC ID and boot mode; PDF spot checks |
| [scif-and-pinctrl.md](scif-and-pinctrl.md) | the UART registers, FIFOs and the TEND timing trap; pin function selection; PDF spot checks |
| [cpu-gic-and-boot-graph.md](cpu-gic-and-boot-graph.md) | CPU cluster and PSCI, the GIC, timers (CNTFRQ, OSTM), and the driver chain to the first console character |

Each topic note ends with **spot checks**: a short list of manual pages that verify the research note's load-bearing claims in about 15 minutes.
