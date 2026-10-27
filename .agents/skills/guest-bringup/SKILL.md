---
name: guest-bringup
description: Boot a real guest (G0 Linux, G1 BSP, firmware) on rzv2l-smarc and drive the failure loop — find the first unmet guest expectation, trace it to driver and manual, fix the smallest model, retest. Covers QEMU debug flags, faults, hangs, gdb, and the unimp coverage list. Use when a guest stops, hangs, loops or prints a probe failure.
---

# Guest bring-up and debug

The policy is AGENTS.md rule 5: observe → first unmet guest expectation → guest code → hardware contract → smallest model change → retest. This skill is the how.

## Run

```bash
build/qemu/qemu-system-aarch64 -M rzv2l-smarc -kernel Image -dtb <DTB-U> -initrd <initramfs> \
  -serial mon:stdio -display none -nodefaults \
  -d unimp,guest_errors,invalid_mem -D out/qemu.log
```

- DTB-U comes from `tests/guests/g0/build-dtb.sh`. Never edit the DT or add a boot argument to make it boot (rule 4); a needed argument is a fidelity gap.
- Earlycon first (M3a): if Linux prints nothing, check SCIF0 TX before anything else.
- Save each run's command and log; a result without its command is not evidence.

## Triage by symptom

| Symptom | First move |
|---|---|
| guest prints an error and goes on | read the driver at that message; which register read gave the wrong answer? |
| `Invalid read/write at addr X` in the log | map X to a `docs/device-map.md` row; is the window planned at this milestone? |
| `unimplemented read at offset` (`LOG_UNIMP`) | the guest needs a register the model lacks → `register-evidence` for that register |
| kernel oops / external abort | PC from the oops → `aarch64-linux-gnu-addr2line -e vmlinux <pc>`; the faulting address → device-map row |
| hang, no output | see "Hangs" below |
| driver probe timeout (`-110`, `ETIMEDOUT`) | the driver polls a bit the model never sets: find the poll loop, model that bit's rule |

Before blaming the driver that reported it: a symptom can sit several layers above its cause (a loader placement, a clock bit, a reset monitor). Name the layer you verified (rule 8).

## Hangs

1. Attach gdb: add `-s -S`, then `gdb-multiarch vmlinux -ex 'target remote :1234'`. Use `hbreak`, and add `-d nochain` if software breakpoints fire inconsistently (TB chaining skips them).
2. Find where each CPU is: `info registers` in the monitor (`-monitor unix:out/mon.sock,server,nowait`), then `addr2line` on PC and LR.
3. A spin on MMIO: the register and the bit it waits for are in the loop; read the manual rule for that bit.
4. Interrupt never arrives: check the device's `update_irq()` equation, the SPI number in the SoC wiring, and the GIC state (`info pic` in the monitor).
5. Race or timing-dependent: try `-icount shift=auto` to make it deterministic while debugging. Remove it after; it distorts boot timing.

## Choosing the fix (allowed options here)

1. extend an existing model with the field the guest reads
2. turn a stub into a real model when the guest reads back or polls
3. a new model for a block the milestone needs (`device-model`)
4. UNIMP window only where the device map allows it and a read of 0 is honest
5. accept a **bounded** probe failure (`-ENODEV`, timeout) as an honest outcome, listed as a gap in `docs/device-map.md` §4

Not allowed: DT trimming, kernel config changes, invented status bits, a register returning "ready" because the driver wants it without the manual's rule.

## Coverage list (what the guest touches that the model doesn't)

After a run: `grep -E 'Invalid (read|write)|unimplemented' out/qemu.log | sort | uniq -c | sort -rn`. Group the addresses by device-map window. Each group is either fixed, or listed with its fidelity class. An acceptance run passes only with every line fixed or listed (REQ-TEST-003).

## Record

- A real model bug: `docs/units/templates/fidelity-bug.md` → `FB-NNN`, with the layer verified.
- A try without evidence: an experiment under `docs/experiments/`.
- The fix gets a qtest or probe (`qtest-golden`, `guest-probe`) and a `mutation-check`.

## Gotchas

- `-daemonize` sends stderr to `/dev/null`: debug prints vanish. Run in the foreground or `setsid … 2>file &`.
- A QEMU still running from an earlier session holds `:1234` and the old binary. Kill it by PID before rebuilding.
- A fix that makes the next failure appear is progress at layer N, not proof of the root cause.
