---
name: guest-bringup
description: Boot a real guest (G0 Linux, G1 BSP, firmware) on rzv2l-smarc and drive the failure loop — find the first unmet guest expectation, trace it to driver and manual, fix the smallest model, retest. Covers QEMU debug flags, faults, hangs, gdb, and the coverage list. Use when a guest stops, hangs, loops or prints a probe failure.
---

# Guest bring-up and debug

The policy is AGENTS.md rule 5: observe → first unmet guest expectation → guest code → hardware contract → smallest model change → retest. This skill is the how.

## Run

- Always with `-d unimp,guest_errors,invalid_mem` and a `-D` log; `invalid_mem` is the only mask that logs accesses to unmapped addresses.
- The DTB is DTB-U (`tests/guests/g0/build-dtb.sh`). Never edit the DT or add a boot argument to make it boot (rule 4); a needed argument is a fidelity gap.
- Linux silent from the start: check SCIF0 TX (earlycon) before anything else.
- Keep each run's exact command line with its log; a result without its command is not evidence.

## Classify first

Before blaming the device, rule out: the environment (stale binary, an old QEMU still running and holding the gdb port), the image (stale or wrong build), the command line, the machine topology, and only then device semantics or the guest.

## Triage by symptom

| Symptom | First move |
|---|---|
| guest prints an error and goes on | read the driver at that message: which register read gave the wrong answer? |
| `Invalid read/write at addr X` | map X to a `docs/device-map.md` row; is the window planned at this milestone? |
| `unimplemented …` (`LOG_UNIMP`) | the guest needs a register the model lacks → `register-evidence` for it |
| kernel oops / external abort | PC via `addr2line` on `vmlinux`; the faulting address → device-map row |
| driver probe timeout (`-110`) | the driver polls a bit the model never sets: find the poll loop, model that bit's rule |
| hang, no output | see "Hangs" |

A symptom can sit several layers above its cause (a loader placement, a clock bit, a reset monitor). Name the layer you verified (rule 8).

## Hangs

- Find where each CPU is (gdb stub, or the monitor's `info registers`), then `addr2line` PC and LR.
- In gdb use hardware breakpoints, and `-d nochain` if breakpoints fire inconsistently (TB chaining skips them).
- A spin on MMIO: the register and bit it waits for are in the loop; read the manual rule for that bit.
- An interrupt that never arrives: the device's `update_irq()` equation, the SPI number in the SoC wiring, then the GIC. `info pic` shows nothing for the GICv3 model (no `InterruptStatsProvider`): use the `gicv3_*` trace points and the CPU's `ICC_*` registers.
- Timing-dependent: `-icount shift=auto` to make it deterministic while debugging, removed afterwards.

## Choosing the fix

1. extend an existing model with the field the guest reads
2. turn a stub into a real model when the guest reads back or polls
3. a new model for a block the milestone needs (`device-model`)
4. an UNIMP window only where the device map allows it, a read of 0 is honest, and it is listed with its fidelity class (spec §7)
5. accept a **bounded** probe failure (`-ENODEV`, timeout) as an honest outcome, listed as a gap in `docs/device-map.md` §4

Not allowed: DT trimming, kernel config changes, invented status bits, a register returning "ready" because the driver wants it.

## Coverage: every log line is accounted for

Every line of the `-d` log, not just the `Invalid`/`unimplemented` forms (`guest_errors` lines such as "write to read-only offset" count too), is either fixed or listed with its fidelity class. Group addresses by device-map window. An acceptance run passes only with every line fixed or listed (REQ-TEST-003); the acceptance log gate and the bench's coverage list apply the same rule.

## Record

- A real model bug: `docs/units/templates/fidelity-bug.md` → `FB-NNN`, with the layer verified.
- A try without evidence: an experiment under `docs/experiments/`.
- The fix gets a qtest or probe and a `mutation-check`.

## Traps

- `-daemonize` sends stderr to `/dev/null`: debug prints vanish.
- A fix that makes the next failure appear is progress at layer N, not proof of the root cause.
