# CPG and SYSC in plain terms

Companion to `../research/cpg-reset.md` and `../research/sysc.md`.

## CPG: the chip's power strip and reset buttons

Think of the CPG (Clock Pulse Generator) as **a power strip with a switch and a reset button for every device on the chip**: UARTs, timers, SD controllers and the rest.

1. **Clock switches** (`CLK_ON_*`). A device whose clock is off is frozen; its registers do not respond. At power-on almost everything is off.
2. **Reset buttons** (`RST_*`). A device held in reset sits in a blank state; releasing reset lets it run.
3. **Indicator lights** (`CLK_MON_*`, `RSTMON_*`). After flipping a switch, Linux does not assume it worked. It waits for the indicator to confirm.
   - The clock light is **on when the clock is on**: same meaning as the switch.
   - The reset light is **on when the device is held in reset**: the opposite of the switch (p.409 vs p.450).
4. **Why this matters for QEMU.** To bring up the UART, Linux does: clock on → wait for the light; release reset → wait for the light to go off. If the model's lights do not behave exactly like that, the driver times out and there is no console.
5. **The speedometer** (PLL and divider registers). Linux reads these to compute each device's clock rate, e.g. the UART input clock = 100 MHz (the EVK boot log shows OSTM running at 100 MHz from the same clock). If the model returned zeros, Linux would compute 0 Hz and get timing wrong without any error, so the model returns the manual's reset values.
6. **MSTOP.** A third kind of switch (bus master stop) used by newer kernels. The pinned 6.12 kernels never touch it on RZ/V2L, so the model simply stores what is written.
7. **Vendor extras.** The vendor kernel also manages the DRP-AI accelerator clocks, so those registers must exist in the model even though mainline ignores them.

## SYSC: the chip's ID card and boot dial

1. **ID card** (`SYS_LSI_DEVID`). Early in boot, Linux reads it to confirm "this is an RZ/V2L, revision 1". The EVK boot log line `Detected Renesas RZ/V2L r9a07g054 Rev 1` is that read succeeding, and the model must return the same value. The manual contradicts itself about the value (p.208 vs Table 6.1); the board is the authority.
2. **Boot dial** (`SYS_LSI_MODE`). It records the medium the chip booted from (SD, eMMC, SPI flash). Firmware reads it; plain Linux does not.
3. **Firmware-only levers** (`RVAL`/`RVAH`, `LP_CTL*`). TF-A uses these to start and stop the second CPU. They matter once real firmware runs, not for the first Linux milestones.
4. **A quirk.** The SYSC device-tree node is marked disabled, yet Linux still reads the ID card. Even a minimal machine must map SYSC.

## In one sentence

The CPG note defines how the model's power switches, reset buttons and indicator lights must behave so Linux can start devices. The SYSC note defines the ID card Linux reads to recognise the chip.

## Spot checks (HW manual Rev 1.50, printed page numbers)

| # | Page | Register | Confirm |
|---|---|---|---|
| 1 | p.327, §7.2.4.58 | `CPG_CLKON_SCIF` | bit 0: 1 = clock supplied; initial 0; bits 16–20 are write-enables |
| 2 | p.368, §7.2.4.97 | `CPG_CLKMON_SCIF` | 1 = supplied (same polarity as CLKON) |
| 3 | p.409, §7.2.4.135 | `CPG_RST_SCIF` | bit 0: 0 = reset applied, 1 = released; initial 0 |
| 4 | p.450, §7.2.4.173 | `CPG_RSTMON_SCIF` | 1 = reset applied, the opposite of check 3; initial 1s |
| 5 | p.208, §6.3.43 vs p.167–168, Table 6.1 | `SYS_LSI_DEVID` | the description gives `844_7447`, the table gives `x841_C447` (the RZ/G2L value): a manual conflict. **Resolved on the EVK: `0x18447447`, so the description is right.** |

## SYSC block diagram (HW manual §6.1.2, Figure 6.1)

SYSC is the chip's **miscellaneous system block**: settings that belong to the whole SoC rather than to one peripheral. Reading the figure from left to right:

| Block in the figure | What it is | Registers (Table 6.1) | Who uses it | Matters for QEMU? |
|---|---|---|---|---|
| **APB4 bus → APB I/F** | How the CPU reaches SYSC's registers: an ordinary memory-mapped slave on the peripheral bus | — | — | The MMIO window at `0x11020000` |
| **Security control** → bus modules | A bus firewall. For each bus *master* (CPU, DMA, …) and *slave* (peripheral), it decides whether secure-only or non-secure access is allowed. The small pink boxes in front of register groups are these gates. | `SYS_MSTACCCTL0-5`, `SYS_SLVACCCTL0-14` | TF-A programs them at boot (`plat/renesas/rz/common/plat_security.c`) | Stored, not enforced (same stance as the TZC: spec §12) |
| **Address translation table** | Lets bus masters with a 32-bit address range (e.g. SD controllers doing DMA) reach memory above 4 GB by substituting upper address bits | `SYS_AOF0-8` (reset values = identity mapping) | Nobody on this board changes them | Identity mapping; store only |
| **Internal register access control → Reg → Each IP** | Configuration wires SYSC holds on behalf of other blocks | Ethernet/I²C config, ECC RAM, CM33 config, CA55 reset vectors (`RVAL/RVAH`) | TF-A (reset vectors for CPU_ON) | Stage B (real BL31) |
| **Arbitration ↔ CoreSight, WDT** | Coordinates the debugger (CoreSight) with the watchdogs, e.g. whether a watchdog keeps counting while a debugger halts the CPU | `SYS_WDT0-2_CTRL` | Firmware/debug setups | Low; store only |
| **Low power mode state management** | The sequencer for putting CPUs to sleep and waking them, handshaking with each CPU, the CPG and interrupts. **Release factors** (USB, GPIO/external interrupt) are the wake-up sources. | `SYS_LP_CTL*`, `SYS_LP_CA55CK_CTL*` | TF-A PSCI CPU_OFF (with the Cortex-M33 completing the handshake) | Stage B: the acknowledge bit must complete |
| **Capture** ← `MD_BOOT[2:0]`, `DEBUGEN`, `MD_CLKS`, `MD_OSCDRV[1:0]`, `PRST#` | Latches the board's strap pins (the boot-mode switches) at power-on reset, so software can read how the board was configured | `SYS_LSI_MODE` (+ the fixed IDs `SYS_LSI_DEVID`, `SYS_LSI_PRR`) | BL2 (boot device), U-Boot | Yes: board properties of the machine |

**Strap pins**, in more detail. `MD_BOOT` is wired to the boot-mode DIP switches on the SMARC board. The chip samples them once, as it leaves power-on reset (`PRST#` rising edge), and the boot ROM uses that value to decide where to load BL2 from. On the EVK the values seen were eSD (0), 1.8 V eMMC (1) and 1.8 V QSPI flash (3) (`docs/evidence/EVK-2026-10-08-boot-log.md`). In QEMU these become **machine properties**: the user picks a boot mode, and `SYS_LSI_MODE` reports it.

**Identification registers measured on the EVK:**

| Register | Value | Meaning |
|---|---|---|
| `SYS_LSI_DEVID` | `0x18447447` | revision 1, RZ/V2L |
| `SYS_LSI_PRR` | `0x0` | dual Cortex-A55 |
| `SYS_LSI_MODE` bit 16 | 1 | security function available on this part |
