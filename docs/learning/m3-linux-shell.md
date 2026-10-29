# M3: a Linux shell

> **Context.** Milestone M3 (spec [§17](../spec/project.md#17-milestones)): the G0 Linux kernel boots to a shell through the real `sh-sci` driver, on both CPUs, with time advancing. The units are cut by what the kernel blocks on. Unit M3b-cpg: [spec](../units/M3b-cpg/spec.md), [tasks](../units/M3b-cpg/tasks.md). The CPG facts are in [`cpg-reset.md`](../research/cpg-reset.md). The EVK values are in [`EVK-2026-10-29-post-firmware.md`](../evidence/EVK-2026-10-29-post-firmware.md).

Code references are at fork commit `4ae1d307eb`.

## 1. The clock pulse generator (unit M3b-cpg)

### 1.1 What the kernel needs

The CPG supplies the clocks and the resets of every other block. The kernel's driver (`rzg2l-cpg.c`) does three things with it:

1. At probe it reads the PLL1 setting and the dividers, and computes the clock rates. PLL1 = 24 MHz × 100 / 2 = 1200 MHz.
2. To start a clock, it writes CLK_ON. Then it polls CLK_MON for 10 µs until the clock shows as supplied.
3. To release a reset, it writes RST. Then it polls RSTMON for 200 µs until the reset shows as released.

M2 stopped at the first of these: the PLL1 read at `0x11010004` took an external abort, because nothing was mapped there.

### 1.2 How the model is shaped

The model is one table of 189 registers (`qemu/hw/misc/renesas_rzv2l_cpg.c`). Each row has an offset, a kind, a reset value, the writable bits and the write-enable bits. A script read these values from the bit table of each register in manual §7.2.4, and checked them against Table 7.5 and the EVK dumps.

There are five kinds of register:

| Kind | Read | Write |
|---|---|---|
| plain (PLL1 settings) | the stored value | the writable bits |
| write-enable (CLK_ON, RST, MSTOP, dividers, selectors) | the stored value | only fields whose enable bit is set in the same write |
| CLKSTATUS | 0 | ignored, logged |
| CLK_MON | CLK_ON's implemented bits, plus the monitor's own reserved 1s | ignored, logged |
| RSTMON | the inverse of RST's implemented bits | ignored, logged |

The monitors are computed when they are read. A stored copy could go out of date. The model has no settle time, so the kernel's first poll read succeeds.

**Worked example: SCIF clocks and resets.** CLK_ON_SCIF is at `0x584` and RST_SCIF at `0x884`. Bit n is SCIFn, and the monitors are `0x180` higher. The sequence starts from reset. `rzv2l-cpg-test.c` asserts the same writes (`/cpg/write-enable` the first row, `/cpg/monitors` the monitor values of the others):

| Write | Register reads after it | Why |
|---|---|---|
| CLK_ON_SCIF ← `0x0000001F` | CLK_ON `0x00`, CLK_MON `0x00` | no bit in 31:16 is set, so no field is enabled and nothing changes |
| CLK_ON_SCIF ← `0x00010001` | CLK_ON `0x01`, CLK_MON `0x01` | bit 16 enables bit 0; this is the kernel's "SCIF0 clock on" |
| CLK_ON_SCIF ← `0x00120010` | CLK_ON `0x11`, CLK_MON `0x11` | bits 17 and 20 enable bits 1 and 4: bit 4 is set, bit 1 is written 0 |
| CLK_ON_SCIF ← `0x00010000` | CLK_ON `0x10`, CLK_MON `0x10` | bit 16 enables bit 0, written 0: SCIF0 clock off, SCIF4 untouched |
| RST_SCIF ← `0x00010001` | RST `0x01`, RSTMON `0x1E` | releases SCIF0; RSTMON is inverted, so SCIF1-4 still show 1 (in reset) |

The kernel never does a read-modify-write on these registers. It writes the enable bits for the clocks or resets it changes, and leaves the others alone. A model that ignored the upper half would switch off SCIF4 on the fourth write.

Two start states (AGENTS.md rule 9) come from the `direct-boot` property. Without it, the registers start at the manual reset values. With `-kernel`, the board sets it, and 23 registers start at the values the EVK firmware left. For example, the OSTM clocks are off (CLK_ON_GTM = 0) and SCIF0 is clocked and out of reset.

### 1.3 The boot, step by step

The trace points show the probe in order (`-trace "renesas_rzv2l_cpg_*"`):

```
renesas_rzv2l_cpg_read SAMPLL1_CLK1 (0x4) -> 0x1901
renesas_rzv2l_cpg_read SAMPLL1_CLK2 (0x8) -> 0x180601
...
renesas_rzv2l_cpg_write CLKON_GIC600 (0x514) <- 0x10001
renesas_rzv2l_cpg_read CLKMON_GIC600 (0x694) -> 0x1
...
renesas_rzv2l_cpg_write RST_GTM (0x834) <- 0x20002
renesas_rzv2l_cpg_read RSTMON_GTM (0x9b4) -> 0x4
```

The value `0x20002` sets bit 1 and its enable bit 17. That releases the OSTM1 reset. RSTMON_GTM then reads `0x4`: only OSTM2 is still held in reset.

After the CPG, three more blocks were probed before the next blocker: the DMA controller, the USB PHY control and the thermal sensor. Each one is mapped with the class the device map gives it, as a logged stub. The kernel then stops in the OS timer (OSTM), which needs a model of its own ([spec, Next blocker](../units/M3b-cpg/spec.md#next-blocker-2026-10-29-fork-4ae1d307eb)).

### 1.4 The proof

`qemu/tests/qtest/rzv2l-cpg-test.c` checks reset values, direct-boot values, the write-enable rule and the monitors. Every expected value comes from Table 7.5, a §7.2.4 bit table or the EVK. Seven mutations each turn one assertion red ([tasks](../units/M3b-cpg/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)). For example, a reset monitor with the same polarity as RST fails at offset `0x980`.

## 2. Pitfalls

- **A Renesas write-enable bit covers a field, not one bit.** In PL2_DDIV, bit 16 enables the 3-bit field at bits 2:0. Linux writes a mask of all field bits into the upper half, so it also sets bits 17 and 18. They have no function. A model that applies each upper bit to the bit 16 below gets the divider wrong (manual §7.2.4.17 p.275; tasks proof 3).
- **RSTMON is the inverse of RST.** In RST, 1 means released; in RSTMON, 1 means in reset. A model that copies RST makes every Linux reset release time out after 200 µs (manual §7.2.4.135 p.409, §7.2.4.173 p.450; `rzg2l-cpg.c:1480`).
- **The manual and silicon disagree on two reserved bits.** Table 7.5 gives CLK_MON_WDT a reset value of `0xC3`, but the EVK reads bits 7:6 of the monitor as 0. CLK_MON_MBUS keeps its reserved 1s on silicon, as the manual says. A model needs a per-register answer, not one rule (EVK X01; spec question 1).
- **"Holes read 0" was not true.** Table 7.5 skips offsets such as `0x510` and `0x824`, but the EVK reads live values there. Do not infer that an offset is unused from a register list. The model gives a bus error for them, so a guest that uses one fails visibly (spec question 4).
- **A register named "DSI only" was read at probe.** The research note listed OTHERFUNC1 (`0xBE8`) as used only for the display. The driver reads it when it registers the PLL5_4 mux, so the first boot stopped there. Registration reads every mux, used or not (`rzg2l-cpg.c:734-740`).
- **A QEMU stub that reads as zero can stop time.** In a diagnostic build with every window read-as-zero, OSTM1 became `sched_clock` and its counter read 0. The kernel clock stayed at 2.133 s while the boot went on. A zero is only honest where the guest does not depend on the value (spec, Next blocker).
- **In QEMU, the unimplemented device logs every access but keeps nothing.** The device map asks for a DMA stub that keeps written values. The new `retain-writes` property of `unimplemented-device` does this, and the log still shows every access (`qemu/hw/misc/unimp.c`).
