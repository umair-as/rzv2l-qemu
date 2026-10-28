---
name: guest-probe
description: Write a bare-metal aarch64 probe that runs on the emulated Cortex-A55s of rzv2l-smarc to check what a qtest cannot see — aborts, exception levels, PSCI, interrupt delivery, firmware-style register sequences, console output. Use for milestone probes (the M2 hello image) and for any behaviour that needs a real CPU.
---

# Guest probe

Template: `tests/probes/m1-skeleton/` (Image header, vectors, PSCI, semihosting exit status, abort catching). Copy it to `tests/probes/<name>/`; don't grow the M1 probe. Background: `docs/learning/testing.md` §2.

## When a probe, not a qtest

- a read must **abort** (unmodelled offset, unmapped hole): qtest sees 0
- CPU state: `CurrentEL`, ID registers, `CNTFRQ_EL0`, MPIDR, PSCI `CPU_ON`
- an IRQ must reach the CPU through the GIC, including SPIs ≥ 256 that qtest cannot intercept
- the **access order** of real firmware matters (e.g. SCIFA: store FTDR, read FSR, write FSR with TEND cleared, then poll TEND; `docs/research/scif.md` §7)
- milestone deliverables that are guest programs (M2: print `Hello from RZ/V2L` through SCIF0)

## Steps

1. Copy the template and rename it. Keep the Image header (QEMU loads it at `0x48200000` and enters at NS-EL1), the vectors, the PSCI and semihosting helpers, and the template's `check()` (name, got, want, print format), with `want` from the manual or device map, cited in a comment.
2. End with `RESULT: PASS|FAIL (<n> failures)` and exit with that status through semihosting; keep `run.sh`'s exit protocol (0 pass, 1 check failed, 2 no result) and its `-d unimp,guest_errors,invalid_mem` log.
3. **Firmware sequences:** replay the guest's register sequence from the cited `file:line` instruction for instruction (same widths, same order, no extra reads). Give every poll a timeout so a model bug fails the probe instead of hanging it.
4. **Interrupts:** the probe runs at NS-EL1 with QEMU's direct-boot GIC state (every interrupt Group 1 NS, `docs/research/cpu-gic.md` §5). Do the full bring-up a kernel does: the Group 1 NS enable in `GICD_CTLR`; wake this CPU's redistributor (`GICR_WAKER.ProcessorSleep` → 0, wait for `ChildrenAsleep` = 0); for the SPI, enable, priority and `GICD_IROUTER` to this CPU; check `ICC_SRE_EL1.SRE` = 1, set `ICC_PMR_EL1` and `ICC_IGRPEN1_EL1`, then unmask `DAIF.I`. The vector acknowledges with `ICC_IAR1_EL1`, records the INTID and writes `ICC_EOIR1_EL1`. Assert INTID = 32 + the SPI number from the device map.
5. **Console output (M2 on):** grep the exact string from QEMU's serial output; keep semihosting for the result line so a broken UART still reports.
6. Add deliberate aborts to the milestone's log allow-list; any other line in the QEMU log is a finding.
7. Run `mutation-check` on each check.

## Traps

- A handler that prints from inside an unexpected exception nests forever (M1): park the CPU on a second exception and let `run.sh` report "no result".
- Without semihosting enabled, the exit `HLT` is undefined: no output at all (exit 2).
- `-icount` changes timing: only to debug a race, never in the probe's normal run.
- The probe tests the model, not QEMU's loader: don't assert QEMU-internal values (PSCI 0.1 function IDs, boot stub contents) as hardware facts.
