# M2-first-character: first blocker after earlycon (M2-T11, L03)

**Model:** fork `unit/M2-first-character` (SCIFA T01-T04). **Guest:** G0 = mainline v6.12.59 (`d5dc97879a97`) arm64 `defconfig` `Image`, unmodified, built by `tests/guests/g0/build-kernel.sh` (SHA-256 `fbe05a8d578683e28f0441191bc3c62bc80688f48e0aa717961bf680dbb551f4`); DTB-U unmodified (`tests/guests/g0/build-dtb.sh`, SHA-256 `4c339906…e85620`).

**Effective configuration (L01, `.config` of that build):** `CONFIG_SERIAL_SH_SCI=y`, `CONFIG_SERIAL_SH_SCI_CONSOLE=y`, `CONFIG_SERIAL_SH_SCI_EARLYCON=y`, `CONFIG_ACPI=y`, `CONFIG_ACPI_SPCR_TABLE=y`. This settles `scif.md` claim 6 for G0. With ACPI built in, a bare `earlycon` takes the SPCR path that falls back to the DT `stdout-path` (`scif.md` §5).

## Acceptance run (L02)

```
qemu-system-aarch64 -M rzv2l-smarc -kernel Image -dtb r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon" \
    -display none -nodefaults -chardev file,id=scif0,path=serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D qemu.log
```

The `-append` string is the DTB-U `/chosen/bootargs` plus a bare `earlycon`: decision (b), a REQ-GUEST-004 gap (device map §4 row 6).

On the serial line (hardware observation of the model):

```
[    0.000000] Linux version 6.12.59 (…) #1 SMP PREEMPT …
[    0.000000] earlycon: scif0 at MMIO 0x000000001004b800 (options '115200n8')
```

The second line is the same line the EVK prints (`../../evidence/EVK-2026-10-08-boot-log.md`).

The serial output then stops at `printk: legacy bootconsole [scif0] disabled` (t = 0.034 s). **Layer: Linux console selection, not the model.** The defconfig kernel has `CONFIG_VT`, and its dummy console (`tty0`) is the first real console to register. Without a `console=` argument, registering it unregisters the boot console. The real serial console (`sh-sci`) cannot register yet, because its probe needs CPG and pinctrl (M3b). Nothing is wrong with SCIF0 at this point: earlycon wrote 33 lines through it.

## Diagnostic run (not acceptance)

To see past the console handover, one run added `keep_bootcon` (and a monitor socket). **This argument is for diagnosis only.** It is not part of any acceptance run and is not a fidelity gap to carry.

The first unmet guest expectation:

```
[    1.007217] Internal error: synchronous external abort: 0000000096000010 [#1] PREEMPT SMP
[    1.057644] pc : rzg2l_cpg_pll_clk_recalc_rate+0x2c/0xa8
 …  rzg2l_cpg_pll_clk_register+0xcc/0x11c
 …  rzg2l_cpg_probe+0x8f4/0xeac
 …  rzg2l_cpg_init+0x24/0x30
[    1.288418] Kernel panic - not syncing: Attempted to kill init! exitcode=0x0000000b
```

- **Guest code:** linux v6.12.59 `drivers/clk/renesas/rzg2l-cpg.c:968`, `readl(priv->base + GET_REG_SAMPLL_CLK1(pll_clk->conf))`, reading PLL1's SAMPLL1_CLK1 at CPG `+0x004` during clock registration.
- **Model:** the CPG window (`0x11010000`, device map CPG row) is unmapped, a recorded gap under DR-0005. The read takes a synchronous external abort. That is an honest fault, and the panic is the guest's honest reaction to it.
- **Layer verified:** the abort address matches the only line of the `-d` log, the ESR (`0x96000010`, DFSC 0x10 = synchronous external abort) and the faulting PC. The cause is the missing CPG model. It is not SCIF, the GIC or the loader.
- **Fix:** M3b, the CPG model (`../../research/cpg-reset.md`). Not done here, as the unit scope says.

Also seen before the panic, at no cost: `smp: Brought up 1 node, 2 CPUs`. CPU1 started through PSCI `CPU_ON` at MPIDR `0x100` with redistributor 1 at `0x11960000`: an early view of the M3 "both CPUs" criterion. `pinctrl core: initialized pinctrl subsystem` printed too; the RZ/G2L pinctrl driver itself has not probed (its window is unmapped too, M3b).

## Coverage list (`-d unimp,guest_errors,invalid_mem`)

| Log line | Window (device map) | Status |
|---|---|---|
| `Invalid read at addr 0x11010004, size 4, region '(null)', reason: rejected` | CPG `0x11010000` | the first blocker; M3b (CPG model) |

That is the whole log of both runs. SCIF0 produced no `guest_errors` or `unimp` line: earlycon used only documented registers at their documented widths.
