# TF-A BL2 from the QSPI flash: what the boot ROM and BL2 need

The contract for running the board's own TF-A BL2 under QEMU, booted from the module's QSPI flash (boot mode 3): what the boot ROM does before BL2, how the flash image is laid out, and every hardware access BL2 makes, in order, with what the model has today. M8's units are written from this page ([M8-bl2-staging](../units/M8-bl2-staging/spec.md) first). The DDR controller and PHY have their own section (§6) because BL2's training is the largest piece.

**Labels:** **F** = stated by the manual or visible in the cited code; **I** = code-derived inference; **A** = assumption; **O** = EVK observation.

**Citation key:** manual = RZ/V2L HW manual Rev 1.50 (printed page numbers). TF-A = rzg_tf-a `f59ed5a31`, built `PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0` (`tests/guests/fw/build-tf-a.sh`); `P/` = `plat/renesas/rz/common/`.

## 1. Boot mode and the boot ROM

| Item | Value | Label, cite |
|---|---|---|
| Boot mode for the module's flash | mode 3, MD_BOOT = `011`: 1.8 V serial flash (single, quad or octal); mode 4 is the 3.3 V one | F: manual Table 4.1 p.105 |
| `SYS_LSI_MODE` | reports MD_BOOT in bits 2:0; latched, not changed by an internal reset | F: §6.3.42 p.207; the board's eSD boot reads `0x10200` (O, EVK-L15) |
| What the ROM does in mode 3 | starts the SPI controller's clock and releases its reset (CPG), sets up the I/O buffers from SYSC, reads the loader size, copies the loader into on-chip RAM `0x12000`-`0x2EFFF`, branches to `0x12000`; on a read failure falls back to SCIF download mode, then loops | F: §4.2.4.2-4.2.4.3 p.128 |
| Loader layout in flash | a 512-byte size block at `0x0`: size in bytes 0-3 (little-endian), signature `0xAA55` in the last two bytes; the loader at `0x200` | F: §4.2.4.4 p.129 (Figure 4.14, 4.15) |
| State the ROM leaves | not documented beyond the steps above: no register values, no EL or SCTLR state | — |

BL2 assumes little of it (F, TF-A): it starts at EL3 in AArch64 on core 0, re-initialises every EL3 control register, zeroes its `.bss`, uses its own stack and ignores `x0`-`x3` (`include/arch/aarch64/el3_common_macros.S:20-121`, `P/bl2_plat_setup.c:135-137`). It does assume PLL4 and PLL6 in standby ("It is assumed that the PLL has stopped", `P/drivers/cpg.c:755`) and the SPI controller idle (`spi_multi.c:116-118` waits for `CMNSR.TEND` = 1). It turns on the SPI clock and releases its reset itself, in `cpg_setup()`'s clock-on and reset tables (`cpg.c:926-936`), before it touches the controller.

**A QEMU stand-in for the ROM** (spec §12 stage C, §18: no boot-ROM model) therefore needs only: check the size block's signature, copy `size` bytes from flash `0x200` to `0x12000`, start core 0 there at EL3 with core 1 off, and fail visibly if the drive is missing, the block or its signature is missing, the size is zero or above `0x1D000`, the image is shorter than the size says, or the drive cannot be read. The stand-in leaves the CPG and the controller at their reset values (A). This differs from the ROM, which turns on the SPI controller's clock and releases its reset (§4.2.4.2 step 1); BL2 sets both up itself before it uses the controller, so BL2 cannot see the difference.

## 2. The flash image

| Flash offset | Content | Source |
|---|---|---|
| `0x0` | boot parameter block, 512 bytes, `0xFF` filled: `size` at `0x00` (BL2's size rounded up to 4), `load` = `0x200` at `0x10`, `dest` = `0x12000` at `0x20`, `0xAA55FFFF` at `0x1FC` | F: `tools/renesas/rz_boot_param/bptool.c`; `soc/v2l/platform.mk:35-36` (`bptool ... 0x00012000 spi`, `cat bp_spi.bin bl2.bin`) |
| `0x200` | `bl2.bin` | F |
| `0x20000` | `fip.bin`: BL31, BL32 (OP-TEE), BL33 (U-Boot) | F: `P/include/rz_soc_def.h:51` (`RZG2L_SPIROM_FIP_BASE` = window + `0x20000`); TF-A's V2L platform guide `rz-v2l.rst:178-180` (flash procedure: FIP at `0x20000`) |
| to `0x4000000` | `0xFF` | — |

**Conflict, recorded:** the vendor kernel DT splits the flash into `bl2` `0x0`-`0x1D000` and `fip` from `0x1D000`, commented "fip is at offset 0x200" (`rzg2l-smarc-som.dtsi`), the layout of an older Renesas flow (FIP at `0x1D200`). This TF-A reads the FIP at `0x20000` only. The project's image follows the TF-A it builds; the partitions are labels and do not move data. EVK-L17 would show which layout the board's own flash carries (a request, not needed for the model).

**BL32 is mandatory in the FIP** (F): `SPD=opteed` leaves a BL32 entry without an optional flag (`P/bl2_plat_mem_params_desc.c:36-50`); a FIP without `tos-fw` ends in `ERROR: BL2: Failed to load image id ...` and a `wfi` loop (`bl2/bl2_image_load_v2.c:70-75`).

## 3. What BL2 does, in order

| Step | Code | Hardware | Model today |
|---|---|---|---|
| 1. Early CPG: SYC clock and reset, PLL4/PLL6 start (poll MON bits 0 and 4 for 0, program, poll for 1), dividers and selectors (poll `CLKSTATUS` = 0), clock-on and reset tables (each entry: write, poll its monitor) | `P/drivers/cpg.c:756-790`, `:888-936`; tables `:240-470` | CPG `0x10`-`0x2C` (`CPG_SAMPLL4/6_*`), `0x2xx`-`0x4xx`, `0x5xx`-`0x9xx` | **PLL4/6 not modelled** (decode error = abort); **`0x574`/`0x6F4`/`0x874`/`0x9F4` (SRC) not modelled**; the rest modelled |
| 2. Pins: PWPR unlock, PMC/PFC per pin, IOLH/PUPD/SR (64-bit stores), QSPI and SD pins | `P/drivers/pfc.c:168-264` | PFC `0x11030000` | modelled (8/16/32/64-bit) |
| 3. Console on SCIF0, then `NOTICE: BL2: v2.10.5(release):...` and the build line | `bl2/bl2_main.c:95-96` | SCIF0 | modelled |
| 4. Security: TZC-400 on DDR and SPI; SYSC master/slave access control, read-modify-write of 22 registers | `P/plat_security.c:19-132` | TZC `0x11060000`, `0x11070000`; SYSC `0x000`-`0x014`, `0x100`-`0x13C` | TZC modelled; **SYSC access control not modelled** (decode error) |
| 5. DDR init and training | `P/drivers/ddr/ddr.c:73-197`, `soc/v2l/drivers/ddr/ddr_v2l.c` | CPG DDR clock/reset; PHY `0x11400000`, controller `0x11410000` | **PHY unmapped, controller a read-as-zero stub**: §6 |
| 6. Device tree for BL31 at `0x58000000`; `SYS_LSI_DEVID` check, `NOTICE: BL2: RZ/V2L` | `P/bl2_plat_setup.c:71-133` | SYSC `0xA04` | modelled |
| 7. Boot mode from `SYS_LSI_MODE` & `0xF` (3, 4: SPI; 0-2 eSD/eMMC; else panic); SPI read path set up: command `0xEB` (1-4-4), 24-bit address, `DRDMCR` = 9 (10 dummy cycles), `DRCR` = `0x001F0300` (read cache on, flushed, SSLE off), SDR | `P/plat_storage.c:195-246`, `P/drivers/spi_multi/spi_multi.c:111-158` | SYSC `0xA00`; SPI controller | modelled (M7); the flash model gives `0xEB` 10 dummy cycles (M7) |
| 8. `NOTICE`s of `SYS_LSI_MODE`, `_DEVID`, `_PRR` | `P/bl2_plat_setup.c:231-233` | SYSC | modelled |
| 9. FIP read through the window at `0x20020000` (memcpy); BL31 to `0x44000000`, BL32 `0x44100000`, BL33 `0x50000000`; parameters at `0x2F000` | `P/plat_storage.c:38-41`, `P/bl2_plat_mem_params_desc.c`, `drivers/io/io_memmap.c` | SPI read window, DDR, SRAM | modelled |
| 10. `NOTICE: BL2: Booting BL31`; `eret` to `0x44000000` at EL3, `x0` = `0x2F000` | `bl2/bl2_main.c:153-167` | — | — |

BL2 does not touch the OTP, the WDT, the GIC, or the SD and eMMC drivers in SPI boot (F). **No poll has a timeout, and a panic prints nothing** (F): `plat_crash_console_putc` is empty (`P/aarch64/plat_helpers.S:35-38`) and `DEBUG=0` prints only `NOTICE` and `ERROR`. A missing model therefore shows as a silent stop; the `-d unimp,guest_errors,invalid_mem` log and the monitor's PC are the only witnesses.

## 4. The CPG registers BL2 needs

| Register | Offset | Reset | Needed behaviour | Label, cite |
|---|---|---|---|---|
| `CPG_SAMPLL4_STBY`, `_CLK1`, `_CLK2` | `0x010`, `0x014`, `0x018` | `0x00000004`, `0x00003203`, `0x00082400` | STBY: bit 0 `RESETB` (1 = normal mode), written only with its write-enable bit (`R0W1` bits in the upper half, §7.2.4.1 p.252-253). CLK1 and CLK2: ordinary writes, no write enables; CLK1 bits 31:16 are data (`DIV_K`, §7.2.4.2 p.254-255), CLK2 bits 31:24, 15:14 and 7:3 reserved, the rest data (§7.2.4.3 p.256-257) | F: Table 7.5 p.246; §7.2.4.1-7.2.4.3; TF-A `include/cpg_regs.h:16-19`, `:352-356` |
| `CPG_SAMPLL6_STBY`, `_CLK1`, `_CLK2` | `0x020`, `0x024`, `0x028` | `0x0`, `0x00003E83`, `0x00082D02` | as PLL4 | F: Table 7.5 p.246 |
| `CPG_SAMPLL4_MON`, `CPG_SAMPLL6_MON` | `0x01C`, `0x02C` | 0 | bit 0 `RESETB` (1 normal, 0 standby) and bit 4 `LOCK` follow STBY.RESETB at once (no lock time) | F: §7.2.4.4 p.259 (reset 0 for n = 4, 6); I for "at once" (BL2 has no timeout and no time check) |
| `CPG_CLKON_SRC`, `CPG_CLKMON_SRC`, `CPG_RST_SRC`, `CPG_RSTMON_SRC` | `0x574`, `0x6F4`, `0x874`, `0x9F4` | inferred, as their siblings: `CLKON` 0 (clock off), `RST` 0 (reset applied), so `CLKMON` 0 and `RSTMON` bit 0 = 1 | as the other clock and reset registers: write-enable halves, `CLKMON` = `CLKON`, `RSTMON` = `~RST` (I: the deleted entries give no reset values or bit layout; bit 0 is the one BL2 uses) | **conflict:** the manual's revision history (p.3554) lists `CPG_CLKON_SRC` and `CPG_RST_SRC` as "deleted" (their old numbers 7.2.4.55 and 7.2.4.134 now hold other registers); BL2 writes and polls them (`cpg.c:254-255`, `:450-451`): guest code rules what is required |

The CPG's BL2 start overlay (`cpg_post_bl2`, used when QEMU stands in for BL2 in M7) is the state BL2 leaves; with the real BL2 the model must reach the same values from BL2's own writes (I: a cross-check, not a separate model).

## 5. The SYSC access-control registers

BL2 reads, masks and writes back `SYS_MSTACCCTL0`-`5` (`0x000`-`0x014`) and `SYS_SLVACCCTL0`-`15` (`0x100`-`0x13C`) (`P/plat_security.c:19-65`). The manual lists them in Table 6.1 (p.167-168) with reset values (for example `SYS_MSTACCCTL0` `0x00AAAA00`, §6.3.1 p.169), except `SLVACCCTL9`, `11` and `15`, which have no row (F). On the board a Non-secure read of `MSTACCCTL0` aborts (O, `research/sysc.md`). Needed: stored registers with the manual's reset values, refusing Non-secure accesses as the TZC model does. The board shows the abort for `MSTACCCTL0` and `SLVACCCTL0` only; that the whole bank is Secure-only is an inference (I). The three unlisted ones are held at the value BL2 writes back (A: reset 0). They are not enforced (spec §12): device map gap 9 stays open for enforcement.

## 6. The DDR controller and PHY

BL2 programs and trains a DDR4-1600 memory system: the `smarc_2` build selects `param_mc_C-010_D4-01-2.c` and `param_swizzle_T1c.c` (F, board makefile), two chip selects of 1 GiB. The manual has no register chapter for either block (§9, p.578-581: features and pins only; Table 5.1 p.144: the windows). The oracle is TF-A's code and the EVK.

| Item | Value | Label, cite |
|---|---|---|
| Windows | PHY `0x11400000`, controller `0x11410000`, 64 KiB each | F: TF-A `P/include/ddr_internal.h:22-77`, manual Table 5.1 p.144 |
| Registers written | 507 controller registers (`0x000`-`0x7F8`, 32-bit; `program_mc1` writes them twice), 48 PHY registers (`0x058`-`0x240`) | F: `ddr.c`, the parameter table |
| Polls | every loop unbounded; seven `panic()` sites (`ddr.c:657`, `:677`, `:880`, `:1001`, `:1187`, `:1203`, `:1349`); 81 PHY training starts, 40 mode-register-write completions | F |
| Must be computed (a store-only register file hangs or panics) | controller `0x260` bit 25 (init done, set by START, cleared by its ack at `0x280`); `0x264` bit 3 (mode-register write done, ack `0x284`); `LP_STATE` `0xF4` from `LP_CMD` `0xE8`; PHY `0x100` bit 28 busy (clears at once) and bits 1:0 = 3; PHY `0x148`, `0x160` bits 1:0 = 3; PHY `0x14C` bits 1:0 = 0 after BL2 writes 3; PHY `0x170` bits 3:2 mirror bits 1:0 | I: from the poll masks and register names; to be checked line by line in the DDR unit |
| `0x1141018C` (`ECC_ENABLE`) | U-Boot reads `0x00000FFF` on the board although BL2 writes 0 there | O: EVK-R80 |
| What would detect a stub | nothing in this build: no memory test, no training result check, ECC off | F |

The stub is a deliberate STUB class (spec §11): each computed bit is labelled as what BL2 waits for, not as the silicon's behaviour.

## 7. Open items

- **The ROM's exit state** (EL, caches, the SPI controller's register values): not documented; the stand-in follows BL2's own assumptions (§1). A board measurement would need a project-built BL2 on the board's flash: an operator decision.
- **The SRC registers' real behaviour** (deleted in the manual, used by BL2): a U-Boot-prompt read of `0x11010574`, `0x6F4`, `0x874`, `0x9F4` would show what BL2 leaves.
- **`SLVACCCTL9`, `11`, `15`**: no manual row; reset values unknown.
- **The FIP offset on the board's own flash** (§2): EVK-L17.
- **The DDR stub's computed bits** (§6): inferred from BL2's polls; an EVK read of the PHY and controller status registers after BL2 would turn them into observations.
