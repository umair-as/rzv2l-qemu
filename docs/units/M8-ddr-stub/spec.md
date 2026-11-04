# M8-ddr-stub — spec

**Milestone:** M8 (the full boot chain, stage C; second unit). **Requirements:** REQ-MAP-001 (every window classified; the DDR controller and PHY become a recorded STUB), REQ-GUEST-003 (unmodified firmware). **Status:** written; implementation follows.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The contract is [`research/bl2.md`](../../research/bl2.md) §6, checked line by line against TF-A `f59ed5a31` and its effective build.

## Scope

**The DDR memory controller (`0x11410000`) and PHY (`0x11400000`), 64 KiB each**, as one new fork device, `renesas-rzv2l-ddr` (two MMIO regions), class **STUB / honest** (spec §11: "DDR controller + PHY: BL2 training; register-file stub"). The manual documents neither block's registers (§9 p.578-581), so the stub follows the contract BL2's code needs, labelled per item (`research/bl2.md` §6.1):

- **Supported offsets:** the controller's `0x000`-`0x7F8` except `0x070`, `0x11C`, `0x120`, `0x124` (no table entry, no code access), and the PHY's 51 offsets BL2 reads or writes (`research/bl2.md` §6); 32-bit accesses only. Any other offset or width: logged and refused with a bus error.
- **Stored registers:** every supported register stores what is written, reset 0 (A), except the computed ones.
- **Computed, each with its trigger, completion, acknowledgement and reset:** controller START → init-done status (`0x260` bit 25), cleared by its acknowledgement (`0x280` bit 25) or START = 0; a mode-register request (`0x114` bit 25) → `0x264` bit 3, cleared by `0x284` bit 3; `LP_CMD` 0x11/0x02 → `LP_STATE` 0x48/0x40; `0x24C` bits 31:16 read 0; `0x18C` bits 11:0 read 1 (EVK-R80, the one observation). PHY: BL2's seven training commands complete at once (`0x100` bit 28 reads 0, bits 1:0 read 3); write leveling clears `0x14C` bits 1:0; `0x148` and `0x160` bits 1:0 read 3; `0x170` bits 3:2 mirror bits 1:0; `0x1D4` reads 0. Every computed value is the stub's answer to BL2's poll or check, not a claim about silicon (A, except `0x18C`'s value, O).
- **Fails visibly:** an unknown training command (bit 28 set, not one of the seven) and an `LP_CMD` other than 0, 0x11 or 0x02 are logged and refused with a bus error. A write to one of the PHY's three read-only status registers is a different case: logged as a guest error and ignored, with no bus error.
- **SoC:** the device replaces the `ddr-memc` UNIMP stub and the unmapped PHY window (`hw/arm/r9a07g054.c`); U-Boot's ECC read keeps its answer (`0x00000FFF`, bits 25:24 = 0: no ECC).
- **Two start states:** one. The registers start as above in every mode; with `-kernel` or `bl33=` nothing but U-Boot's `0x18C` read touches them. That start state is also the post-firmware state for `0x18C`: its low bits are computed, not stored, so U-Boot reads `0x00000FFF` as after BL2 on the board (O, EVK-R80) (I).
- **Not modelled:** the training (results are BL2's constants), the PHY's lane banking through `0x12C`, ECC and BIST, DDR timing and refresh, the controller's interrupts, the CPG's DDR reset lines (BL2 rewrites the table after its controller reset; I).

## What the guest needs

BL2 `ddr_setup()` (`P/drivers/ddr/ddr.c:73-186`), in order: `cpg_active_ddr(disable_phy_clk)` (PHY `0x200`, `0x204`); `program_mc1()` (507 table writes); reads of `0x22C` and `0x7A4`; `program_phy1()` (about 40 PHY writes, the IO calibration polls on `0x170`); the DLL poll (`0x160`); START and the init-done poll (`0x260`); the controller reset and the table again; START, poll, acknowledgement (`0x280`); write leveling, VREF, bit leveling, `opt_delay` (the low-power polls), SL training (`0x100`, `0x148`, `0x14C`, `0x1AC`, `0x1C0`, `0x1D4`, 40 mode-register writes through `0x114`/`0x264`/`0x284`); `program_phy2()`, `program_mc2()`. Then `bl2_init_fdt()` and the FIP load.

## Exit criterion

- `-M rzv2l-smarc,boot-mode=3 -drive if=mtd,...` (as M8-bl2-staging): after its banner BL2 prints `NOTICE:  BL2: RZ/V2L`, `NOTICE:  BL2: SYS_LSI_MODE: 0x10003` (the machine's default straps, `DEBUGEN` low; the board's QSPI boot printed `0x10203`, with `DEBUGEN` set, device map), `NOTICE:  BL2: SYS_LSI_DEVID: 0x18447447`, `NOTICE:  BL2: SYS_LSI_PRR: 0x0` and `NOTICE:  BL2: Booting BL31`: DDR set up, the FIP read from the flash, BL31, BL32 and BL33 loaded. What BL31 and the rest of the chain do after that is the next unit's (M8-full-chain); the run stops at `Booting BL31` for this check. The `-d` log up to that line lists no DDR access outside the contract.
- A guest probe takes the abort of an unsupported controller offset (a hole and one past the range), an unsupported PHY offset and a non-32-bit access: a qtest read cannot prove a refusal, it reads a value.
- qtests (stub-contract tests, labelled as such): each completion, acknowledgement, computed read, stored read-back and ignored read-only write of §6.1, including a read-modify-write of `0x170` that leaves its mirror, and write leveling clearing `0x14C`; each seen red under a mutation, among them a missing completion, a broken acknowledgement, lost storage, and a write-leveling command that leaves `0x14C` alone.
- Before the boot check: `rzv2l-rpc-test` reads through the QSPI read window as BL2 does (`0xEB`, 1-4-4, 24-bit address, `DRDMCR` 9, `DRCR` `0x001F0300`: 32-line bursts), several kilobytes of non-repeating data across many burst boundaries, every byte compared with the flash image the test prepares; BL2's FIP (about 870 KB) is that path's first use at volume.
- M7 acceptance (U-Boot's ECC read included) and the M8 BL2 run unchanged in what they check.

## Evidence

TF-A `f59ed5a31`: `P/drivers/ddr/ddr.c`, `soc/v2l/drivers/ddr/ddr_v2l.c`, `param_mc_C-010_D4-01-2.c`, `param_swizzle_T1c.c`, `soc/v2l/include/ddr_*.h`; the build's objects (`build/v2l/release/bl2/`). Manual §9 p.578-581, Table 5.1 p.144. EVK-R80 (`../../evidence/EVK-2026-11-02-ddr-ecc.md`). [`research/bl2.md`](../../research/bl2.md) §6.
