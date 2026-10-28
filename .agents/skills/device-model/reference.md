# Device model patterns

Code shapes for the classes in SKILL.md. Names are examples; adapt to the block. QEMU v11.1.2 APIs (the fork's `rzv2l-base`).

## 1. Field classes

| Class | Read returns | Write does | Wrong stub and why |
|---|---|---|---|
| config | last written value (masked to writable bits) | stores | — RAM is right |
| command | 0 once done | starts an action; hardware self-clears | RAM: a "wait for done" poll spins forever |
| status, level | computed from state now (e.g. FIFO count ≤ trigger) | usually nothing; may re-assert after a clear | stored constant: lies when state changes |
| status, event | latched when the event happens | cleared by the documented rule | set on every read: invented behaviour |
| side-effect read | value, and the read changes state (FIFO pop, read-to-clear, arms a clear) | — | plain read: guest sees the same byte twice |

Writable masks: apply the manual's R/W bits on every write (`s->reg = (s->reg & ~WMASK) | (val & WMASK)`). Renesas CPG-style registers with a write-enable upper half: only bits whose enable bit is set change (`docs/research/cpg-reset.md` §2.1).

## 2. "Clear by writing 0 after reading 1" (read-armed clear)

Several Renesas status registers (SCIFA FSR, `docs/research/scif.md` §3.1) clear a flag only if the guest read it as 1 since it was last set. Track the armed bits:

```c
/* on read */
s->fsr_armed |= s->fsr & FSR_CLEARABLE;
/* on write: a 0 clears only an armed flag; 1s do nothing */
uint16_t clr = ~val & s->fsr_armed & FSR_CLEARABLE;
s->fsr &= ~clr;
s->fsr_armed &= ~clr;
/* when hardware sets a flag again, disarm it */
s->fsr |= FSR_TEND;
s->fsr_armed &= ~FSR_TEND;
```

Then recompute level-like flags (they may re-assert at once), then `update_irq()`.

## 3. IRQ lines from equations

```c
static void blk_update_irq(BlkState *s)
{
    /* manual Table x.y: each line is a boolean of enable & flag bits */
    qemu_set_irq(s->irq[BLK_TXI], (s->scr & SCR_TIE) && (s->fsr & FSR_TDFE));
    qemu_set_irq(s->irq[BLK_RXI], (s->scr & SCR_RIE) && (s->fsr & FSR_RDF));
}
```

- `sysbus_init_irq()` once per line in `instance_init`, in the order the SoC wires them.
- Call `update_irq()` at the end of every read with side effects, every write, every timer callback, and after reset.
- Level lines are levels: never pulse them.

## 4. Completion on a virtual-time timer

Use when firmware reads status between "start" and "done" (SCIFA TEND: TF-A and U-Boot read FSR right after the FTDR write and clear TEND; a synchronous completion makes the next flush spin forever, `docs/research/scif.md` §7).

```c
s->tx_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, blk_tx_done, s);   /* realize */
/* on the triggering write: the write itself has effects, then the timer */
s->fsr &= ~FSR_TEND;          /* manual: FSR TEND clears on an FTDR write (p.1281) */
/* push the byte into the TX FIFO, recompute TDFE from the FIFO count, update_irq() */
timer_mod(s->tx_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + char_time_ns(s));
/* blk_tx_done(): send the byte, update FIFO, set the event flag, update_irq() */
```

- Derive the duration from the programmed registers (bit rate, frame length). If the inputs are not modelled yet, use a documented fixed value and list it as a gap.
- Between the trigger and the timer, status must read "in progress" (TEND = 0 here): take each flag's clearing conditions from the manual, not only the guest's own clear.
- Cancel it (`timer_del`) in the reset phase; free it (`timer_free`) in `unrealize`/`finalize`. `timer_del` only stops it.

## 5. Chardev (UARTs)

```c
DEFINE_PROP_CHR("chardev", BlkState, chr),               /* property */
qemu_chr_fe_set_handlers(&s->chr, blk_can_receive, blk_receive,
                         NULL, NULL, s, NULL, true);      /* realize */
```

- `can_receive` returns free RX FIFO space; never block the vCPU on host output (`qemu_chr_fe_write_all` per byte stalls the guest).
- The SoC wires `serial_hd(n)` to the instance that is console on the board (SCIF0 on the EVK).

## 6. Reset and start states

```c
static void blk_reset_hold(Object *obj, ResetType type)
{
    BlkState *s = BLK(obj);
    /* every guest-visible and internal field, not only the registers */
    s->fsr = FSR_RESET;          /* manual Table x.y */
    s->fsr_armed = 0;
    s->scr = SCR_RESET;
    fifo8_reset(&s->tx_fifo);
    timer_del(s->tx_timer);      /* no completion from before the reset */
    if (s->direct_boot) {
        s->scr = SCR_POST_FW;    /* overlay: measured or (I); see header comment */
    }
    blk_update_irq(s);           /* lines follow the reset state (§3) */
}
/* class_init */
ResettableClass *rc = RESETTABLE_CLASS(klass);
rc->phases.hold = blk_reset_hold;
```

## 7. Honest faults

| Situation | Do |
|---|---|
| offset not modelled | `LOG_UNIMP` + `return MEMTX_DECODE_ERROR` (guest takes an external abort). Needs the `.read_with_attrs`/`.write_with_attrs` callbacks; plain `.read` cannot return a bus error (as in `renesas_rzg2l_sysc.c`) |
| guest breaks a manual rule (write to read-only, bad width) | `LOG_GUEST_ERROR`; behave as silicon does (ignore, or the documented error) |
| mode or feature not supported | the block's own error status/IRQ if it has one; otherwise decode error on the register that selects it |
| result the model cannot compute | never report success; leave the documented "busy/error" state |

`LOG_UNIMP` and `LOG_GUEST_ERROR` reach the operator only. The guest sees only bus errors, status bits and IRQs. A C comment saying "not modelled" is invisible to the guest.
