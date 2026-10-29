# M3b-ostm — spec

**Milestone:** M3 (second unit, after the clock controller). **Requirement:** REQ-OSTM-001. **Status:** written 2026-10-29; implementation follows straight on (operator's standing instruction).

## Scope

A new device `renesas-rz-ostm`, one instance per channel: OSTM0-2 at `0x12801000` + n × `0x400` (manual Table 20.2 p.1224), interrupts on SPI 46, 47 and 48, edge-rising (DT). The manual calls the block GTM ("General Timer"). It is FUNCTIONAL and faithful for what is modelled:

- **Registers** (§20.2.1 p.1226): CMP (R/W, 32-bit), CNT (R, 32-bit), TE (R, 8-bit), TS (W, 8-bit, reads 0), TT (W, 8-bit, reads 0), CTL (R/W, 8-bit; MD1 bit 1, MD0 bit 0). Each register accepts only its own access width; another width, or an offset the manual does not list, is a bus error. That is a design choice (an honest fault, AGENTS.md rule 6): the manual gives only the access units (§20.2.1) and does not say what another width does.
- **Counter on the virtual clock** at the count clock P0 (§20.3.2), a board property set to 100 MHz: CPG PL2_DDIV resets to 0 and the EVK leaves it at 0 (EVK R11), which gives P0 = 100 MHz.
- **Free-running comparison mode** (MD1 = 1, §20.3.6): counts up from 0, wraps at `0xFFFFFFFF`; interrupt when the counter passes CMP, first after (CMP + 1) clocks (Table 20.5 (a)); a CMP rewrite takes effect at once (Table 20.5 (c), (d)); TS while running is ignored.
- **Interval timer mode** (MD1 = 0, §20.3.5): counts down from CMP, interrupt every (CMP + 1) clocks, then reloads CMP; a CMP rewrite takes effect at the next reload; TS while running is a forced restart. With CMP = 0 the interrupt request stays asserted while the counter runs (§20.3.5.2). **Inference:** the model holds it whatever CTL.MD0 is. The section's first bullet reads as unconditional, but its item (4) could also be read as MD0 = 0 suppressing the request; Linux never uses interval mode with CMP = 0.
- **TE / TS / TT** (§20.2.2.3-5): TS sets TE and starts; TT clears TE and stops, the counter keeps its value. A restart begins again from CMP (interval) or from 0 (free-running) (§20.2.2.3 Note 1).
- **CTL** is writable only while TE = 0 (§20.2.2.6; the manual's text says "OSTMnTOE", which is no register of this block and is read as TE); a write while running is ignored and logged. Changing MD1 sets CNT to the mode's initial value (Table 20.4 p.1228: interval `0xFFFFFFFF`, free-running 0). MD0 = 1 adds an interrupt when counting starts (§20.3.3).
- **Interrupt:** a pulse into the GIC per event, matching the edge-triggered SPI; the CMP = 0 interval case holds the line high instead.

**Not modelled:** DMA start by compare match (§20.1); the debug-pause input (§20.2.2.3 Note 2); the count clock following CPG divider writes or CLK_ON gating, and the CPG reset line RST_GTM (no CPG outputs yet, as for SCIF; Linux releases the reset before its first access, so it is not visible today); in free-running mode with CMP = 0, the request lasting two count clocks (§20.3.6.2 item 3): the model sends one pulse, which an edge-triggered interrupt cannot tell apart.

## What the guest needs

G0 = linux v6.12.59 `drivers/clocksource/renesas-ostm.c` (`CONFIG_RENESAS_OSTM=y`); DT: OSTM1 and OSTM2 `okay` (`rzg2l-smarc-som.dtsi:167-173`), OSTM0 disabled.

| Driver step (`file:line`) | Registers | Behaviour needed |
|---|---|---|
| `ostm_timer_stop` :46-59 | TE read (8-bit), TT write, TE poll | TE = 1 only while running; TT clears it at once |
| clock source on OSTM1, `ostm_init_clksrc` :61-72 | CMP ← 0, CTL ← `0x02`, TS ← 1, CNT read (32-bit, counting up) | free-running counter at 100 MHz |
| `sched_clock` on OSTM1 :74-83 | CNT read | must advance: a still counter freezes kernel time (EXP-002) |
| one-shot event on OSTM2 :85-97 | stop, CMP ← delta, CTL ← `0x02`, TS ← 1 | one interrupt after delta + 1 clocks |
| periodic event on OSTM2 :107-119 | stop, CMP ← period − 1, CTL ← `0x00`, TS ← 1 | an interrupt every period clocks |
| IRQ handler :130-142 | TE read, TT write (one-shot) | as above |

**Start states.** Both are the reset values (§20.2.1): CMP 0, CNT `0xFFFFFFFF`, TE/CTL 0. Firmware mode: the manual. Direct mode: the EVK reads RST_GTM = `0x1` after firmware, so OSTM1 and OSTM2 are still held in reset, and CLK_ON_GTM = 0, so no channel runs (EVK R15). OSTM0 is out of reset but unclocked; G0 does not use it (I). No `direct-boot` property is needed.

## Exit criterion

The G0 boot passes the OSTM probe (`timer@12801400: used for clocksource`, `timer@12801800: used for clock events`) with kernel time advancing, and stops at the next block that needs its own model (PFC, IRQC or `sh-sci`). The qtests assert the manual's values and timing, each seen red on a plausible mutation (`tasks.md`).

## Evidence

HW manual Rev 1.50 §20 p.1224-1240; EVK R11, R15 (`../../evidence/EVK-2026-10-29-post-firmware.md`); the driver lines above; [EXP-002](../../experiments/EXP-002-read-as-zero-survey.md); `../M3b-cpg/spec.md` "Next blocker".

## Listed for the operator

- **CMP = 0 in interval mode with MD0 = 0:** the model asserts the request (see Scope). The other reading would assert it only with MD0 = 1. No guest uses it.
- **Bus error on a wrong-size or unlisted access:** kept as the project's honest-fault class; the manual is silent.

## Next blocker (2026-10-29, fork `afe1e5b71b`)

From the diagnostic run (`keep_bootcon`):

```
[    3.479130] Internal error: synchronous external abort: 0000000096000010 [#1] PREEMPT SMP
[    3.540851] pc : rzg2l_rmw_pin_config+0x50/0xa0
 …  rzg2l_pinctrl_pinconf_set+0x1ec/0x4f4
 …  pinctrl_enable+0x6c/0x294
 …  rzg2l_pinctrl_probe+0x478/0x778
```

- **Guest code:** linux v6.12.59 `drivers/pinctrl/renesas/pinctrl-rzg2l.c`. At probe the pin controller applies its default pin state; `rzg2l_rmw_pin_config` read-modify-writes the input-enable register of port 4, `IEN(4)` = `0x1800 + 4 × 8` = `0x1820` (:139). The default state is the pin controller's own `sound_clk` hog (AUDIO_CLK1/2 `input-enable`), as `../../research/pinctrl.md` §3 predicted; the EVK reads IEN04 as 0 after firmware (R35).
- **Model:** the PFC window (`0x11030000`) is unmapped: an honest fault.
- **Layer verified:** the `-d` log's only unmapped access is `Invalid read at addr 0x11031820, size 4`, matching the PC, the call trace and DFSC `0x10`. The OS timer probe completed first. The cause is the missing pin controller model, the next unit (with the external-interrupt controller).

### Coverage list (`-d unimp,guest_errors,invalid_mem`)

| Log lines | Window (device map) | Class | Status |
|---|---|---|---|
| `rz-dmac` × 18 writes | DMAC `0x11820000` | write-retaining STUB | earlier unit |
| `usbphy-ctrl` read and write at `+0x0` | USB PHY control `0x11C40000` | write-retaining STUB | earlier unit |
| `tsu` reads and writes (a bounded poll; count depends on host speed) | TSU `0x10059400` | UNIMP | earlier unit |
| `Invalid read at addr 0x11031820, size 4` | PFC `0x11030000` | FUNCTIONAL, needs a model | next unit |

No OSTM line appears: every access the kernel makes to the OS timers is to a modelled register at its own width.
