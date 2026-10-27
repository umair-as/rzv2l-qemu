---
name: guest-probe
description: Write a bare-metal aarch64 probe that runs on the emulated Cortex-A55s of rzv2l-smarc to check what a qtest cannot see — aborts, exception levels, PSCI, interrupt delivery, firmware-style register sequences, console output. Use for milestone probes (the M2 hello image) and for any behaviour that needs a real CPU.
---

# Guest probe

Template: `tests/probes/m1-skeleton/` (Image header, vectors, PSCI, semihosting exit status, abort catching). Copy it to `tests/probes/<name>/`; don't grow the M1 probe. Background: `docs/learning/testing.md` §2.

## When a probe, not a qtest

- a read must **abort** (unmodelled offset, unmapped hole): qtest sees 0
- CPU state: `CurrentEL`, ID registers, `CNTFRQ_EL0`, MPIDR, PSCI `CPU_ON`
- an IRQ must reach the CPU through the GIC (enable, priority, ack, EOI)
- the **access order** of real firmware matters (e.g. SCIFA: store FTDR, read FSR, write FSR with TEND cleared, then poll TEND; `docs/research/scif.md` §7)
- milestone deliverables that are themselves guest programs (M2: print `Hello from RZ/V2L` through SCIF0)

## Steps

1. Copy the template; rename in `Makefile`, `run.sh` and the header comments. Keep: the Image header (QEMU loads it at `0x48200000` and enters at EL1), `vectors`, `read32`, `smc_call`, `semihost`.
2. Write each check as `check(name, got, want)` with `want` from the manual or device map, cited in a comment. Print `RESULT: PASS|FAIL (<n> failures)` last, then exit with the status through semihosting `SYS_EXIT`.
3. **Firmware sequences:** replay the guest's register sequence instruction for instruction, from the cited `file:line` (same widths, same order, no extra reads). Add a timeout to every poll so a model bug fails the probe instead of hanging it.
4. **Interrupts:** enable the line at the GIC distributor and redistributor, set `PMR`, unmask `DAIF.I`, and have the IRQ vector record the INTID it acknowledged. Assert the INTID equals 32 + the SPI number from the device map.
5. **Console output (M2 on):** output through the UART model goes to QEMU's serial; run with `-serial file:out/serial.log` or `-serial stdio` and grep the exact string. Keep semihosting for the result line so a broken UART still reports.
6. `run.sh`: keep the exit protocol (0 pass, 1 check failed, 2 no result) and `-d unimp,guest_errors,invalid_mem -D out/qemu.log`. Pass extra arguments through to QEMU.
7. Add the probe's expected log lines (deliberate aborts) to the milestone's log allow-list; anything else in `qemu.log` is a finding.
8. Run `mutation-check` on each check.

## Pitfalls

- A handler that prints from inside an unexpected exception nests forever (M1 lesson): park the CPU on a second exception, then let `run.sh` report "no result".
- Without `-semihosting-config enable=on,target=native` the `HLT` is undefined: the probe gives no output (exit 2).
- `-icount` changes timing: use it to debug a race, never in the probe's normal run.
- The probe is a test of the model, not of QEMU's loader: don't assert QEMU-internal values (the PSCI 0.1 function IDs, boot stub contents) as if they were hardware facts.
