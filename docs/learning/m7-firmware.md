# M7: the board's own firmware

> **Context.** Milestone M7 (spec [§17](../spec/project.md#17-milestones)): the board's Trusted Firmware-A, OP-TEE and U-Boot in place of QEMU's shortcuts. Unit M7-el3-platform: [spec](../units/M7-el3-platform/spec.md), [tasks](../units/M7-el3-platform/tasks.md), register evidence [`../research/el3-platform.md`](../research/el3-platform.md). The boot chain is in [`../research/boot-chain-firmware.md`](../research/boot-chain-firmware.md). TF-A paths are under `plat/renesas/rz/common/` at commit `f59ed5a31`.

Until M7, QEMU itself answered the kernel's power calls. This page shows what changes when the board's own BL31 does it: what BL31 needs to start, how it starts a second core through the SoC's registers, and how the model was found to be missing pieces one at a time. It is written for two readers. If you know the RZ/V2L boot chain, it shows which parts of it QEMU replaces and which run for real. If you are new to QEMU, it shows how a machine runs firmware at EL3 and how a CPU is powered on by a device model.

## 1. Who answers PSCI

Linux does not start the second core itself. It asks the firmware with an SMC instruction: PSCI `CPU_ON`, with the core's ID and an entry address. On the board, TF-A's BL31 answers at EL3.

QEMU can stand in for BL31. When a machine starts a kernel directly, QEMU catches each SMC and answers the PSCI call in C (`qemu/target/arm/tcg/psci.c`). That is direct mode, used from M1 to M5. It is fast, and it hides everything BL31 does with the SoC.

| | Direct mode (`-kernel`) | Firmware mode (`-bios bl31.bin -kernel`) |
|---|---|---|
| who answers PSCI | QEMU's C code | the board's BL31, at EL3 |
| CPU1 starts by | QEMU powering the CPU object on | BL31 writing the SYSC and CPG registers |
| SMC Calling Convention seen by Linux | v1.0 | v1.4, as on the board |
| `reboot` | QEMU resets the machine | BL31 forces a WDT0 parity error, which resets the board |
| `poweroff` | QEMU exits | BL31 waits forever: it does not implement `SYSTEM_OFF` |

In firmware mode QEMU's PSCI must be off. Otherwise QEMU catches the SMCs before they reach EL3, and the test would check QEMU, not BL31. The machine never sets the CPUs' `psci-conduit` property in firmware mode, so the SMCs go to EL3 as on the board.

## 2. What BL2 gives BL31

On the board, BL31 is not the first code. The boot ROM loads BL2, and BL2 sets up DDR, loads BL31, OP-TEE and U-Boot, and then enters BL31. QEMU does not run the boot ROM or BL2 yet (M8). So the machine must hand BL31 exactly what BL2 would.

1. **BL31 at `0x44000000`**, from `-bios`.
2. **A parameter block in SRAM at `0x2F000`.** BL2 writes the entry point of each image it loaded. BL31 copies the block once and later starts the next image from it.
3. **BL31 entered at EL3 with `x0` = `0x2F000`.** A six-instruction stub at BL2's address `0x12000` does this. CPU0 starts in it after every machine reset.

The parameter block caught the model out once. TF-A has two structures with the same name, `bl2_to_bl31_params_mem_t`: one for R-Car (`plat/renesas/common/include/rcar_private.h`) and one for RZ (`include/rz_private.h`). The first model used the R-Car layout. BL31 read its BL33 entry point at the wrong offset, found 0, and took a data abort at EL3. A release build prints nothing for this: BL31 waits in `plat_panic_handler`. The QEMU monitor showed the PC, and `-d int` showed the abort:

```
Taking exception 4 [Data Abort] on CPU 0
...from EL3 to EL3
...with ESR 0x25/0x96000007
...with FAR 0x4
```

`FAR` 0x4 is the `attr` field of a NULL entry point. The layout now comes from the RZ header, and BL31's own code confirms it: its lookup reads the non-secure entry point at offset 96.

## 3. Starting a core through the SoC

BL31 does not have QEMU's shortcut. It starts CPU1 the way the manual describes (§2.2), with three blocks of registers:

1. **The reset vector**, in SYSC `SYS_CA55_CFG_RVAL1/RVAH1`: where the core starts.
2. **The core's resets**, in CPG `RST_CA55`: apply `CA55_RST1_1`, wait for `RSTMON_CA55`, then release `CA55_RST1_1` and `CA55_RST3_1`.
3. **The P-Channel handshake**, in CPG `CORE1_PCHCTL/PCHMON`: request power mode ON with `PREQ`, wait for `PACCEPT`, drop `PREQ`, wait for `PACCEPT` to drop.

The model joins these to a real QEMU CPU:

- The CPG keeps each core's last accepted power mode. A core runs while that mode is ON and both its resets are released. The CPG signals each change on a GPIO line, `ca55-run`.
- The SoC takes the line. When a core starts, the SoC copies the SYSC reset vector into the CPU's `rvbar` and calls `arm_set_cpu_on_and_reset()`. The reset samples `rvbar` into the PC at EL3, which is what the hardware does with RVBAR when a core leaves reset.
- When a core stops, the SoC calls `arm_set_cpu_off()`. That call completes later, on the core's own thread. So a start that follows at once is queued on the same thread, behind the stop.

`CPU_OFF` goes the other way. The dying core asks the SYSC for sleep (`LP_CTL1`) and waits until its request flag is set in `LP_CTL5`; then the next `CPU_ON` first takes its P-Channel to OFF.

## 4. Finding the missing pieces

The method was the project's failure loop (AGENTS.md rule 5): boot, find the first access the model refuses, read the code that made it, model what the manual says, boot again. Each stop showed up as one line in the `-d unimp,guest_errors,invalid_mem` log, or as a silent wait found with the monitor:

| Stop | What BL31 was doing | What was added |
|---|---|---|
| write `0x11000020` refused | `syc_init`: the counter frequency into the system counter | the SYC, a CoreSight timestamp generator (manual §15) |
| read `0x11050000` refused | the TZC-400 for the SRAM: its build configuration | a TZC-400 register file that stores, does not filter |
| `gicv3_redist_read` at `0x24` | powering up the GIC-600 Redistributors | `GICR_PWRR` (GIC-600 TRM §4.4.5) |
| SYSC read `0xd08` | `CPU_ON`: was the core put to sleep before? | the reset vectors and sleep registers |
| CPG write `0xb44` | `CPU_ON`: the P-Channel handshake | the P-Channels and the core run lines |
| `CPU_OFF` never ends | the Cortex-A55 power-down sets `CPUPWRCTLR_EL1` | the register on QEMU's Cortex-A55 (EXP-001 had found it missing) |

## 5. How we know it works

1. **Register tests (qtest).** They assert the manual's reset values and rules: the reset vectors' reserved bits, the `LP_CTL5` flag rule, the P-Channel reset value and `PACCEPT`, the TZC filter and region counts. A qtest also watches the CPG's `ca55-run` lines while it applies resets and handshakes.
2. **The firmware boot.** `tests/acceptance/m7/firmware.py` boots BL31 and the vendor kernel from the SD card. It checks the BL31 banner, SMC Calling Convention v1.4, both CPUs, CPU1 offline and online twice, and a `reboot` into BL31 again.
3. **Mutations.** Twelve plausible mistakes, each seen to turn a check red ([tasks](../units/M7-el3-platform/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)). Two stayed green at first and each got a test: an ignored P-Channel OFF, and a core that ignores one of its two resets.

## 6. Pitfalls

- **Two structures, one name.** A firmware tree can hold a platform family's copy of a structure next to another family's. Take the layout from the header the platform builds with, and confirm it in the binary (TF-A `include/rz_private.h:42`).
- **A release firmware panics in silence.** BL31 built with `DEBUG=0` prints nothing when it panics. Read the PC from the QEMU monitor and the exception from `-d int` before you guess.
- **An identification register has consequences.** The model reports a GIC-600 in its IIDR, as the board does (M1). TF-A then powers the Redistributors up through `GICR_PWRR`, a register QEMU's generic GICv3 did not have. An honest ID value makes firmware use the real part's extra registers.
- **The sequence can hide a rule.** BL31's `CPU_ON` applies the core's reset before the ON handshake, so a model that ignores an OFF handshake still boots and hotplugs. Only a test that drives the handshake alone shows the difference (proof 8).
- **QEMU's own PSCI must step aside.** If the CPUs' PSCI conduit is set, QEMU answers the kernel's SMCs, and a firmware boot "works" without BL31 doing anything. Check the SMC Calling Convention version the kernel prints: v1.4 is BL31, v1.0 is QEMU.
- **`poweroff` does not end the run.** This BL31 has no `SYSTEM_OFF` (`plat_pm.c:109`): it waits, as the board does. A test that waits for QEMU to exit will hang in firmware mode.
