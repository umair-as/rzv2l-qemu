# M8-bl2-staging — spec

**Milestone:** M8 (the full boot chain, stage C; first unit). **Requirements:** REQ-SYSC-002 (boot source from `SYS_LSI_MODE`, proven when the real BL2 reads it), REQ-GUEST-003 (unmodified firmware). **Status:** written; implementation follows.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The contract, the image layout and BL2's accesses are in [`research/bl2.md`](../../research/bl2.md).

## Scope

The board's own TF-A BL2, built from the vendor source, starts from the module's QSPI flash and runs until it first needs the DDR memory controller (the next unit, M8-ddr-stub).

- **Guest builds** (project, `tests/guests/fw/`): `build-tf-a.sh` also builds `bl2` and `fiptool` with the same flags as BL31 (`PLAT=v2l BOARD=smarc_2 SPD=opteed DEBUG=0`); a new `build-spi-image.sh` writes a 64 MiB flash image: the 512-byte boot parameter block from TF-A's own `bptool` at `0x0`, `bl2.bin` at `0x200`, a FIP (`bl31.bin`, OP-TEE `tee-raw.bin`, `u-boot.bin`) at `0x20000`, `0xFF` elsewhere (`research/bl2.md` §2). Each records its command and output hashes, as the other firmware builds do.
- **Boot-ROM stand-in** (fork `hw/arm/rzv2l-smarc.c`; spec §12 stage C: no ROM model): with `boot-mode=3` or `4` (serial flash, manual Table 4.1 p.105) and neither `-bios` nor `-kernel`, at every machine reset the board reads the flash drive's size block, checks the `0xAA55` signature, copies `size` bytes from flash `0x200` to on-chip RAM `0x12000`, and starts core 0 there at EL3 in AArch64, core 1 off (manual §4.2.4.3-4.2.4.4 p.128-129). No drive, a missing signature or a size above `0x1D000` stop QEMU with an error that names the cause (the ROM's fallback, SCIF download mode, is not modelled). The CPG and the SPI controller start at their reset values: BL2 sets both up itself (A: the ROM's exit state is not documented; `research/bl2.md` §1). With `-bios` the M7 path (QEMU in BL2's place) is unchanged.
- **CPG** (fork `hw/misc/renesas_rzv2l_cpg.c`, FUNCTIONAL): `CPG_SAMPLL4_STBY`/`_CLK1`/`_CLK2`/`_MON` (`0x010`-`0x01C`) and the same for PLL6 (`0x020`-`0x02C`) with the reset values of Table 7.5 (p.246); each `MON`'s `RESETB` (bit 0) and `LOCK` (bit 4) follow `STBY.RESETB` at once (§7.2.4.4 p.258-259; I: no lock time, BL2 checks none). The SRC clock and reset registers `0x574`, `0x6F4`, `0x874`, `0x9F4` as their siblings (reset 0, write-enable halves, monitors computed).
- **SYSC** (fork `hw/misc/renesas_rzg2l_sysc.c`, register file, not enforced): `SYS_MSTACCCTL0`-`5` and `SYS_SLVACCCTL0`-`15` stored with the reset values of Table 6.1 (p.167-168), Secure accesses only (O: a Non-secure read aborts on the board, `research/sysc.md`); a Non-secure access is refused like the TZC's.
- **Two start states.** Firmware mode: the manual reset values above. Direct-kernel mode and the M7 BL2 stand-in (`cpg_post_firmware`, `cpg_post_bl2`): PLL4 and PLL6 in normal mode with BL2's settings (`cpg_pll4_setdata`, `cpg_pll6_setdata`, `cpg.c`; I: what BL2 writes, not measured), the SRC registers as BL2's tables leave them, the SYSC access-control values BL2 writes (I).
- **Source conflict, recorded:** the manual lists `CPG_CLKON_SRC` (§7.2.4.55) and `CPG_RST_SRC` (§7.2.4.134) as deleted; BL2 writes and polls them (`cpg.c:254-255`, `:450-451`). Guest code rules what is required; the model keeps them as ordinary clock and reset registers.
- **Not modelled:** the boot ROM itself (its SCIF fallback, its SPI and CPG settings, its I/O buffer set-up), PLL lock time, the SSCG modulation, enforcement of the access-control registers, `SLVACCCTL9`/`11`/`15` beyond storing what is written (no manual row; A: reset 0).

## What the guest needs

BL2 (TF-A `f59ed5a31`), in order: EL3 entry at `0x12000` (`bl2/aarch64/bl2_el3_entrypoint.S`); `cpg_early_setup()` and `cpg_setup()`: PLL4/PLL6 standby poll, set-up, lock poll (`P/drivers/cpg.c:756-790`), dividers, clock-on and reset tables with monitor polls including SRC (`:240-470`, `:888-936`); `pfc_setup()` (`P/drivers/pfc.c:168-264`); the SCIF0 console; `NOTICE: BL2: v2.10.5(release):...` and the build line (`bl2/bl2_main.c:95-96`); `bl2_platform_setup()`: TZC-400 set-up for DDR and SPI, then the SYSC access-control read-modify-writes (`P/plat_security.c:19-132`); then `ddr_setup()` (`P/drivers/ddr/ddr.c:73`), the next unit's.

## Exit criterion

- `-M rzv2l-smarc,boot-mode=3 -drive if=mtd,format=raw,file=spi.img` (no `-bios`, no `-kernel`): SCIF0 prints `NOTICE:  BL2: v2.10.5(release):2.10.5/rz_1.1.0` and `NOTICE:  BL2: Built : f59ed5a31` (the project's build, as its BL31); BL2 passes its security set-up and stops at its first DDR controller or PHY access, which the `-d unimp,guest_errors,invalid_mem` log names (the next blocker). No other unlisted line in the log.
- The ROM stand-in's errors: no drive, a bad signature, an oversized loader each stop QEMU with their message (acceptance).
- qtests: the PLL4/PLL6 and SRC reset values and monitor rules, the SYSC access-control reset values and the Non-secure refusal; each seen red under a mutation.
- M7 acceptance (with M1-M6) unchanged.

## Evidence

Manual Table 4.1 p.105, §4.2.4 p.124-130, §6.3.1 p.169 and Table 6.1 p.167-168, Table 7.5 p.246, §7.2.4.4 p.258-259. [`research/bl2.md`](../../research/bl2.md) §1-§5. TF-A's V2L platform guide `rz-v2l.rst:170-180` (flash procedure). EVK: the board boots from the SD card (`SYS_LSI_MODE` `0x10200`, EVK-L15), so no board observation of a QSPI boot exists; EVK-L17 (requested) would show the layout of the board's own flash.
