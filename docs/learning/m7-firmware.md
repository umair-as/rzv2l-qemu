# M7: the board's own firmware

> **Context.** Milestone M7 (spec [§17](../spec/project.md#17-milestones)): the board's Trusted Firmware-A, OP-TEE and U-Boot in place of QEMU's shortcuts. Unit M7-el3-platform: [spec](../units/M7-el3-platform/spec.md), [tasks](../units/M7-el3-platform/tasks.md), register evidence [`../research/el3-platform.md`](../research/el3-platform.md). The boot chain is in [`../research/boot-chain-firmware.md`](../research/boot-chain-firmware.md). TF-A paths are under `plat/renesas/rz/common/` at commit `f59ed5a31`. Unit M7-rpc-spinor (§7): [spec](../units/M7-rpc-spinor/spec.md), [tasks](../units/M7-rpc-spinor/tasks.md), register evidence [`../research/rpc.md`](../research/rpc.md); QEMU lines in §7 are at fork commit `f66bcc5e26`.

Until M7, QEMU itself answered the kernel's power calls. This page shows what changes when the board's own BL31 does it: what BL31 needs to start, how it starts a second core through the SoC's registers, and how the model was found to be missing pieces one at a time. It is written for two readers. If you know the RZ/V2L boot chain, it shows which parts of it QEMU replaces and which run for real. If you are new to QEMU, it shows how a machine runs firmware at EL3 and how a CPU is powered on by a device model.

## 1. Who answers PSCI

Linux does not start the second core itself. It asks the firmware with an SMC instruction: PSCI `CPU_ON`, with the core's ID and an entry address. On the board, TF-A's BL31 answers at EL3.

Why ask the firmware at all? PSCI is Arm's standard interface, so one Linux driver works on every Arm SoC. The kernel only says "core `0x100` on, start it at this address". The way to do that differs from SoC to SoC: on the RZ/V2L it means programming the SYSC and CPG registers. Those registers belong to the secure world, and BL31 is the one piece of software that knows them. Each call is made by a particular core:

| PSCI call | Made by | What it asks |
|---|---|---|
| `CPU_ON` | a running core (CPU0) | start another core at a given address |
| `CPU_OFF` | the core going down, about itself | power me off; a core can only stop itself |
| `AFFINITY_INFO` | a running core | is that core off yet? (the kernel's `CPU1 killed (polled 0 ms)`) |
| `SYSTEM_RESET`, `SYSTEM_OFF` | any core | `reboot`, `poweroff` |

So `echo 0 > /sys/devices/system/cpu/cpu1/online` goes like this: Linux moves CPU1's tasks and interrupts to CPU0, and CPU1 itself then calls `CPU_OFF` and never returns. Meanwhile CPU0 polls `AFFINITY_INFO` until BL31 reports CPU1 off. `echo 1` is a `CPU_ON` from CPU0, the same call that brought CPU1 up during boot.

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

1. **The reset vector**, in SYSC `SYS_CA55_CFG_RVAL1/RVAH1`: where the core starts. BL31 writes its own warm-boot entry point there, not the kernel's address.
2. **The core's resets**, in CPG `RST_CA55`: apply `CA55_RST1_1`, wait for `RSTMON_CA55`, then release `CA55_RST1_1` and `CA55_RST3_1`.
3. **The P-Channel handshake**, in CPG `CORE1_PCHCTL/PCHMON`: request power mode ON with `PREQ`, wait for `PACCEPT`, drop `PREQ`, wait for `PACCEPT` to drop.

The model joins these to a real QEMU CPU:

- The CPG keeps each core's last accepted power mode. A core runs while that mode is ON and both its resets are released. The CPG signals each change on a GPIO line, `ca55-run`.
- The SoC takes the line. When a core starts, the SoC copies the SYSC reset vector into the CPU's `rvbar` and calls `arm_set_cpu_on_and_reset()`. The reset samples `rvbar` into the PC at EL3, which is what the hardware does with RVBAR when a core leaves reset.
- When a core stops, the SoC calls `arm_set_cpu_off()`. That call completes later, on the core's own thread. So a start that follows at once is queued on the same thread, behind the stop.

A `CPU_ON` therefore enters BL31 twice, once on each core:

1. **On CPU0**, at Linux's SMC: BL31 records the kernel's entry address for CPU1, writes the registers above, and returns to Linux on CPU0.
2. **On CPU1**, when it leaves reset: it starts at EL3 in BL31's warm-boot entry, the address from step 1's reset vector. BL31 turns on CPU1's GIC CPU interface (`rzg2l_pwr_domain_on_finish` in `plat_pm.c`) and drops to non-secure EL1 at the kernel's address. Linux prints `CPU1: Booted secondary processor`.

`CPU_OFF` goes the other way and runs on the dying core. BL31 turns off the core's GIC CPU interface, so no interrupt can wake it, and asks the SYSC for sleep (`LP_CTL6`, `LP_CTL1`). It waits until its request flag is set in `LP_CTL5`. Per the manual, that flag records the request and interrupts the Cortex-M33; BL31's comment calls it the M33's answer. The model sets the flag when the request arrives and has no Cortex-M33. BL31 then sets `LP_CTL2`, powers the core down through `CPUPWRCTLR_EL1` and waits in `wfi`. The next `CPU_ON` sees `LP_CTL2` and first takes the core's P-Channel to OFF. A boot only runs the first `CPU_ON`; the offline-online test also runs `CPU_OFF` and this second path.

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

## 5. Asking the board the same questions

Two reads on the board check what firmware mode should reproduce. Both are in [`../evidence/EVK-2026-11-01-firmware.md`](../evidence/EVK-2026-11-01-firmware.md).

**From Linux: what firmware is the kernel talking to?** At boot the kernel calls the firmware and logs what it finds. One filter shows the lines, on the board and in QEMU alike:

```bash
dmesg | grep -iE 'trusted os|migrat|smccc|psci'
grep . /sys/devices/system/cpu/vulnerabilities/*
```

- `PSCIv1.1 detected in firmware`: the power interface's version.
- `SMC Calling Convention v1.4`: the version of the rules for calling into the firmware. QEMU's own PSCI says v1.0; BL31 says v1.4, on the board and in firmware mode. This line tells you who answered.
- `Trusted OS migration not required`: Linux asked whether the Secure OS (OP-TEE) is tied to one core. BL31 passes this question to OP-TEE's dispatcher, so the answer exists only while OP-TEE runs. Firmware mode has no OP-TEE yet and prints `MIGRATE_INFO_TYPE not supported.` instead; the next unit adds OP-TEE.
- `vulnerabilities/*`: the CPU security bugs the kernel checked for, and its answer to each. Some mitigations need firmware calls, so these could differ; they read the same on the board and in both QEMU modes (only `spectre_v1` is mitigated, in the kernel itself).

**From U-Boot: how is a TrustZone controller built?** The SoC has four TZC-400s, gatekeepers that decide which memory accesses the Secure and Non-secure worlds may make. Each has a read-only `BUILD_CONFIG` register that describes it. `md.l ADDRESS 1` in U-Boot reads one 32-bit word:

```
=> md.l 0x11040000 1
"Synchronous Abort" handler, esr 0x96000010, far 0x11040000
...
Resetting CPU ...
```

The board refused the read. U-Boot runs in the Non-secure world, and the bus answered its access with an error: `ESR` `0x96000010` decodes as a data abort (`EC` `0x25`) from an external abort (`DFSC` `0x10`), not an MMU fault. U-Boot's reaction to an abort is to reset. So the controllers' own registers are Secure-only, which the model did not know: it now refuses Non-secure accesses the same way. BL31 is unaffected, because it runs in the Secure world at EL3.

## 6. How we know it works

1. **Register tests (qtest).** They assert the manual's reset values and rules: the reset vectors' reserved bits, the `LP_CTL5` flag rule, the P-Channel reset value and `PACCEPT`, the TZC filter and region counts. A qtest also watches the CPG's `ca55-run` lines while it applies resets and handshakes.
2. **The firmware boot.** `tests/acceptance/m7/firmware.py` boots BL31 and the vendor kernel from the SD card. It checks the BL31 banner, SMC Calling Convention v1.4, both CPUs, CPU1 offline and online twice, and a `reboot` into BL31 again. The second round checks the `CPU_ON` path from the off state again; it does not check the sleep flag again, because BL31 never clears it (the first `CPU_OFF` leaves it set).
3. **A probe at EL3.** A qtest's accesses carry no security state, and BL31's boot cannot tell some mistakes apart (it reads a `GICR_PWRR` that always reads 0 as "powered up"). `tests/probes/el3-secure/` is a small bare-metal program run as `-bios`. It checks the `GICR_PWRR` rules of the GIC-600 TRM from EL3, then drops to Non-secure EL1, finds `GICR_PWRR` reading 0 and a TZC read aborting, and returns to EL3 with an SMC to confirm the Non-secure writes changed nothing.
4. **Mutations.** Nineteen plausible mistakes, each seen to turn a check red ([tasks](../units/M7-el3-platform/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)). Two stayed green at first and each got a test: an ignored P-Channel OFF, and a core that ignores one of its two resets.

## 7. The QSPI flash

The SMARC module has a 64 MiB serial NOR flash, a Micron MT25QU512A, on the SoC's SPI Multi I/O Bus Controller (Renesas also calls it RPC or SPIBSC). U-Boot rewrites one of the flash's registers on every boot, and the vendor kernel registers three partitions on it. This section shows how a guest reaches a flash through this controller, how QEMU connects a flash to a controller, and the one-byte error that the flash's own description table found.

### Two ways to reach the flash

The controller has two operating modes (manual §25.5.4):

| Mode | The guest writes | The controller sends | Used for |
|---|---|---|---|
| manual mode | the command, address and data registers, then `SMCR.SPIE` | one flash command; the data goes through `SMWDR0` / `SMRDR0` | writes, erases, status and ID reads |
| external address space read mode | nothing per read: it reads the 256 MiB window at `0x20000000` | one flash read command for each CPU read that misses the read cache | reading the flash's contents |

In the second mode an ordinary load instruction becomes a flash command. The registers `DRCMR`, `DRENR` and `DRDMCR` set the command, which phases are sent, and how many dummy cycles come before the data. A Linux session that reads 16 bytes of a partition with `dd` shows both kinds of read. The trace is `--trace renesas_rzv2l_rpc_read`, counted by command with `uniq -c`, the addresses removed:

```
4096 renesas_rzv2l_rpc_read command 0xec address X length 4 burst 0
   2 renesas_rzv2l_rpc_read command 0x9f address X length 256 burst 1
```

`0xec` is the 4-byte-address Quad I/O Fast Read. Linux reads the flash with it through the window, 4 bytes for each CPU access, without the cache (`burst 0`). `0x9f` is Read ID. The ID command has no address phase, so Linux reads its answer through the window from offset 0 with the cache on, as one burst of 32 lines (`renesas-rpc-if.c:551-578`).

### The read cache

With `DRCR.RBE` = 1 the controller reads through a cache of 32 lines of 8 bytes (manual §25.5.6). A miss reads `RBURST` + 1 lines from the flash, from an 8-byte boundary. A hit reads no flash. So the cache can hold old data after the flash changes, and the guest must flush it with `DRCR.RCF`. The qtest shows this with a page program between two reads (`tests/qtest/rzv2l-rpc-test.c:422`):

1. Read address 4 through the cache: `0xffffffff`, the erased flash.
2. Program 16 bytes of `0x00` at address 0 in manual mode.
3. Read address 4 again: still `0xffffffff`, a cache hit.
4. Write `DRCR.RCF` and read again: `0x00000000`.

A model without the cache returns `0x00000000` at step 3 (proof 7 in the unit's tasks). With `DRCR.SSLE` = 1 the chip select stays asserted after a burst, and the next miss at the following address continues the same flash command. While it waits, `CMNSR.TEND` reads 0 (manual §25.5.12; `qemu/hw/ssi/renesas_rzv2l_rpc.c:776`).

### A flash on an SSI bus

QEMU already has a model of SPI NOR flash: `m25p80` (`qemu/hw/block/m25p80.c`). It is a device on QEMU's SSI bus. The controller owns the bus and drives a chip-select line. The board puts the flash on the bus (`info qtree`):

```
dev: renesas-rzv2l-rpc, id ""
  gpio-in "clk" 1
  gpio-in "rst" 1
  gpio-out "sysbus-irq" 2
  mmio 0000000010060000/0000000000010000
  mmio 0000000020000000/0000000010000000
  bus: spi
    type SSI
    dev: mt25qu512a, id ""
      nonvolatile-cfg = 65535 (0xffff)
```

One SSI transfer moves one byte each way. The controller model sends a command as bytes: the command byte, the address bytes, the option bytes, the dummy cycles, then the data (`rpc_build_header`, `qemu/hw/ssi/renesas_rzv2l_rpc.c:314`). The bus has no lines, so the 1-bit or 4-bit width of a phase does not change the bytes. The one place the width counts is the dummy phase: the model sends cycles × lines / 8 bytes, with the width of the address phase (`renesas_rzv2l_rpc.c:400`). `m25p80` counts its dummy bytes in the same way. The `clk` and `rst` inputs come from the CPG (`CPG_CLKON_SPI_MULTI`, `CPG_RST_SPI`). While the reset is applied or the clocks are off, an access to the controller is refused.

### The one-byte shift

The first boot with the flash showed the right ID and partitions, but every read from Linux came one byte early:

```
image:  76 37 81 99 e4 7a 00 1e 27 f5 ae b5 e6 ab ad 95
Linux:  37 81 99 e4 7a 00 1e 27 f5 ae b5 e6 ab ad 95 b9
```

The trace gave the cause: Linux reads with `0xec`, the 1-4-4 command (one line for the command, four lines for the address and the data). Linux takes its dummy cycles from the flash's SFDP table, the parameter table that a flash returns for command `0x5a`. The board's flash says 1 mode clock and 9 wait states for this command, that is 10 cycles (EVK-L16, [`../evidence/EVK-2026-11-04-spi-flash.md`](../evidence/EVK-2026-11-04-spi-flash.md)). On four lines, 10 cycles are 5 bytes. `m25p80` gave Micron parts 10 dummy cycles only in the Quad I/O protocol and 8 in the normal one, which is 4 bytes. So the controller sent 5 dummy bytes, the flash model started its data after 4, and the controller dropped the first data byte. The fix is in the flash model: Quad I/O Fast Read gets 10 cycles in every protocol (`qemu/hw/block/m25p80.c:995`).

The ID read had worked because it has no dummy cycles. A boot that only prints the flash's name proves nothing about its data. The acceptance run reads a random 64 MiB image back through U-Boot and Linux ([`../../tests/acceptance/m7/flash.py`](../../tests/acceptance/m7/flash.py)).

### Where the bytes go in the data registers

Data shorter than 4 bytes in manual mode has two conventions in the guests:

| Guest | 1- or 2-byte write | 1- or 2-byte read |
|---|---|---|
| U-Boot, TF-A | a 32-bit write, data in the top bytes (`<< 24`, `<< 16`) | TF-A: a 32-bit read, data in bits 7:0 |
| Linux | `writeb`/`writew` at offset 0 | `readb`/`readw` at offset 0 |

The manual puts a short transfer in bits 7:0 or 15:0 of `SMRDR0` and `SMWDR0` (Figure 25.32). Reads agree with all guests, so the model fills `SMRDR0` from bit 0 (`renesas_rzv2l_rpc.c:495`). Writes disagree: U-Boot's top-byte writes work on the board. U-Boot writes the flash's non-volatile configuration register with them on every boot, and the flash still answers normal SPI commands afterwards (EVK-L16). If those bytes came from bits 15:0, U-Boot would write `0x0000`, which selects the flash's quad-only protocol. So the model sends the top bytes of `SMWDR0`, and a 1- or 2-byte write at offset 0 lands there (`renesas_rzv2l_rpc.c:492`). This is an inference, recorded in [`../research/rpc.md`](../research/rpc.md) §4. The acceptance run checks the result: U-Boot reads `FFFFh` from the register and writes `FFEFh` back, as its code intends.

## 8. Pitfalls

- **Two structures, one name.** A firmware tree can hold a platform family's copy of a structure next to another family's. Take the layout from the header the platform builds with, and confirm it in the binary (TF-A `include/rz_private.h:42`).
- **A release firmware panics in silence.** BL31 built with `DEBUG=0` prints nothing when it panics. Read the PC from the QEMU monitor and the exception from `-d int` before you guess.
- **An identification register has consequences.** The model reports a GIC-600 in its IIDR, as the board does (M1). TF-A then powers the Redistributors up through `GICR_PWRR`, a register QEMU's generic GICv3 did not have. An honest ID value makes firmware use the real part's extra registers.
- **The sequence can hide a rule.** BL31's `CPU_ON` applies the core's reset before the ON handshake, so a model that ignores an OFF handshake still boots and hotplugs. Only a test that drives the handshake alone shows the difference (proof 8).
- **QEMU's own PSCI must step aside.** If the CPUs' PSCI conduit is set, QEMU answers the kernel's SMCs, and a firmware boot "works" without BL31 doing anything. Check the SMC Calling Convention version the kernel prints: v1.4 is BL31, v1.0 is QEMU.
- **Secure-only registers fail loudly on silicon.** A Non-secure read of a TZC register aborts on the board; a model that answers it hides the mistake from whoever wrote the access. Ask the board from the Non-secure world (U-Boot `md`) before assuming a register is readable there, and expect a reset if it is not.
- **`poweroff` does not end the run.** This BL31 has no `SYSTEM_OFF` (`plat_pm.c:109`): it waits, as the board does. A test that waits for QEMU to exit will hang in firmware mode.
- **A controller's reset values can select another kind of flash.** After reset, `CMNCR.BSZ` says two flash memories, `PHYCNT.PHYMEM` says HyperFlash and `DRDRENR` says DDR (manual Table 25.2). The guest must set all three before a serial flash works. A model that ignores them hides a guest that forgets one.
- **A flash's own table beats a model's defaults.** QEMU's `m25p80` default for Micron dummy cycles did not match the part's SFDP table, and Linux follows the table. Read the part's SFDP on the board (`/sys/bus/spi/devices/*/spi-nor/sfdp`) and give the model those bytes (EVK-L16).
- **Dummy cycles are not bytes on every line count.** On a byte-wide SSI bus a dummy phase is cycles × lines / 8 bytes. A count of cycles that is not a whole number of bytes cannot be sent. The model refuses such a setting and logs it (`renesas_rzv2l_rpc.c:400`).
- **A read cache returns old data until it is flushed.** After a manual-mode write, a read through the window can come from the cache (manual §25.5.6). The guest flushes with `DRCR.RCF` and reads `DRCR` once before the next window read (manual §25.4.3).
- **The flash keeps state that the image file does not.** The non-volatile configuration register lives in the flash, not in its array. On the board U-Boot's write stays; in the model each QEMU start begins at the factory `FFFFh` ([`../device-map.md`](../device-map.md), gap 25).
