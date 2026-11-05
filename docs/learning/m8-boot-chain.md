# M8: the full boot chain from the QSPI flash

> **Context.** Milestone M8 (spec [§17](../spec/project.md#17-milestones)): the board's own BL2 in place of QEMU's last shortcut, so that every firmware stage runs. Unit M8-bl2-staging: [spec](../units/M8-bl2-staging/spec.md), [tasks](../units/M8-bl2-staging/tasks.md). Unit M8-ddr-stub: [spec](../units/M8-ddr-stub/spec.md), [tasks](../units/M8-ddr-stub/tasks.md). Unit M8-full-chain: [spec](../units/M8-full-chain/spec.md), [tasks](../units/M8-full-chain/tasks.md). The evidence for BL2 is [`../research/bl2.md`](../research/bl2.md). TF-A paths are at commit `f59ed5a31`; `P/` is `plat/renesas/rz/common/`. QEMU lines are at fork commit `176d418966`.

In M7, QEMU did BL2's work: it loaded BL31, OP-TEE and U-Boot and wrote BL2's parameter block ([`m7-firmware.md` §2](m7-firmware.md#2-what-bl2-gives-bl31)). In M8 the board's BL2 does that work itself, from the QSPI flash on the module. This page shows the four parts that make that possible:

1. a stand-in for the boot ROM;
2. BL2 and what it needs from the SoC;
3. a stub of the DDR controller and PHY, and what that stub cannot prove;
4. how BL2 finds its firmware package and reads it from the flash.

If you know the RZ/V2L boot chain, the page shows which parts QEMU replaces and which run for real. If you are new to QEMU, it shows how a machine starts from a flash image and what a register stub can and cannot stand in for.

## 1. The boot ROM and its stand-in

This section shows the first step after reset, and why QEMU does only part of it. On the board, the boot ROM reads the boot-mode pins and loads the first loader from the boot device. QEMU has no copy of the ROM code, and the project does not model it (spec §18).

The manual gives the ROM's steps for a serial-flash boot (§4.2.4.2-4.2.4.4 p.128-129). In boot mode 3 (1.8 V serial flash), the ROM:

1. turns on the SPI controller's clock and releases its reset;
2. reads a 512-byte size block at flash offset `0x0`;
3. checks the signature `0xAA55` in the last two bytes of that block;
4. copies the loader from flash `0x200` into on-chip RAM at `0x12000`;
5. branches to `0x12000`.

The size is in bytes 0-3, little-endian. The loader can be at most `0x1D000` bytes: on-chip RAM from `0x12000` to `0x2EFFF`.

The project's flash image has that layout ([`../research/bl2.md` §2](../research/bl2.md#2-the-flash-image)):

```
$ xxd -l 4 tests/guests/out/spi/spi.img
00000000: 24e9 0000                                $...
$ xxd -s 0x1fc -l 4 tests/guests/out/spi/spi.img
000001fc: ffff 55aa                                ..U.
```

The loader size is `0xE924` bytes. The signature bytes are `55 aa`: the value `0xAA55`, little-endian.

QEMU's stand-in does steps 2-5 (`qemu/hw/arm/rzv2l-smarc.c:453-503`). It reads the flash image through the block layer, not through the SPI controller. Then it starts CPU0 at `0x12000` at EL3, with CPU1 off. Stop QEMU before the first instruction (`-S`) and look:

```
$ qemu-system-aarch64 -S -M rzv2l-smarc,boot-mode=3 -monitor stdio \
      -drive if=mtd,format=raw,file=spi.img ...
(qemu) info registers
 PC=0000000000012000 X00=0000000000000000 X01=0000000000000000
PSTATE=00000000400003cd -Z-- EL3h     FPCR=00000000 FPSR=00000000
(qemu) xp /4wx 0x12000
00012000: 0xaa0003f4 0xaa0103f5 0xaa0203f6 0xaa0303f7
```

The four words at `0x12000` are BL2's first instructions. They are the bytes at flash `0x200` (`f403 00aa ...` in `xxd`). The stand-in skips step 1: it leaves the SPI controller's clock off and its reset applied. BL2 turns both on before it uses the controller (`P/drivers/cpg.c:926-936`), so BL2 cannot see the difference.

If the ROM could not boot from the flash, the board would try the next boot source. The stand-in stops QEMU instead and names the cause. The M8 acceptance run checks each case (`tests/acceptance/m8/bl2.py`):

```
qemu-system-aarch64: boot mode 3 boots from the QSPI flash: give it with -drive if=mtd
qemu-system-aarch64: boot ROM: no loader on the QSPI flash (signature ff ff at 0x1fe, not 55 aa)
qemu-system-aarch64: boot ROM: loader size 0x0 is not 1 to 0x1d000 bytes
qemu-system-aarch64: boot ROM: loader size 0x1d004 is not 1 to 0x1d000 bytes
```

The ROM loads the loader again after each reset, so the stand-in does too (`rzv2l_smarc_rom_cpu_reset`, `qemu/hw/arm/rzv2l-smarc.c:506`). A `reboot` in Linux therefore goes back through BL2, as on the board.

## 2. What BL2 does

This section lists what BL2 needs from the SoC, in order. BL2 runs from on-chip RAM, sets up the clocks, pins, console, bus security and DDR, then loads the next images. The full table, with the code and register for each step, is [`../research/bl2.md` §3](../research/bl2.md#3-what-bl2-does-in-order). This is what a run prints on SCIF0:

```
NOTICE:  BL2: v2.10.5(release):2.10.5/rz_1.1.0
NOTICE:  BL2: Built : f59ed5a31
NOTICE:  BL2: RZ/V2L
NOTICE:  BL2: SYS_LSI_MODE: 0x10003
NOTICE:  BL2: SYS_LSI_DEVID: 0x18447447
NOTICE:  BL2: SYS_LSI_PRR: 0x0
NOTICE:  BL2: Booting BL31
NOTICE:  BL31: v2.10.5(release):2.10.5/rz_1.1.0
```

Seven lines cover clock set-up, DDR training, the FIP read and three image loads. A release build (`DEBUG=0`) prints only `NOTICE` and `ERROR` lines. A panic prints nothing, because the crash console is empty (`P/aarch64/plat_helpers.S:35-38`). No poll in BL2 has a timeout. If the model lacks a register, BL2 therefore stops in silence or loops. The only witnesses are the `-d unimp,guest_errors,invalid_mem` log and the PC in the monitor.

M8's first unit found the missing pieces that way. BL2 needs these from the model:

- **two more PLLs in the CPG** (PLL4 and PLL6): BL2 starts them and polls their lock bits;
- **the SPI clock's on and reset registers** (`SRC`): the manual's revision history lists them as deleted, but BL2 writes and polls them (`P/drivers/cpg.c:254-255`);
- **the SYSC access-control registers**: BL2 reads and writes back 22 of them.

Each one is in [`../research/bl2.md` §4-5](../research/bl2.md#4-the-cpg-registers-bl2-needs). After those, BL2 stopped at its first write to the DDR PHY. That is the subject of §3.

## 3. The DDR stub and its limits

This section shows a different kind of model: a stub whose behaviour comes from the guest's code, not from the manual. BL2 sets up and trains a DDR4-1600 memory system through two register blocks, the controller at `0x11410000` and the PHY at `0x11400000`. The manual documents neither block's registers (§9 p.578-581 give the features and pins only).

Without a manual there is no hardware truth to model. The project therefore wrote the stub's contract from BL2's own code ([`../research/bl2.md` §6.1](../research/bl2.md#61-the-stub-contract)), and labels each item. The stub, `renesas-rzv2l-ddr`, does three things:

1. **It stores what BL2 writes.** It accepts only the offsets BL2 reads or writes: the controller's `0x000`-`0x7F8` without four holes, and 51 PHY offsets.
2. **It computes the answers to BL2's polls.** For example, START sets the init-done flag at once, and each of BL2's seven training commands completes at once.
3. **It fails visibly.** Any other offset, any access that is not 32 bits wide, an unknown training command and an unknown low-power command are logged and refused with a bus error (`qemu/hw/misc/renesas_rzv2l_ddr.c:112-122`, `:281-289`).

Trace the stub to see BL2's set-up from the device's side. Count the events of one boot:

```
$ qemu-system-aarch64 -M rzv2l-smarc,boot-mode=3 ... \
      -trace 'renesas_rzv2l_ddr_*' -D trace.log
$ grep -o 'renesas_rzv2l_ddr_[a-z_]*' trace.log | sort | uniq -c
    164 renesas_rzv2l_ddr_event
      4 renesas_rzv2l_ddr_lp
    269 renesas_rzv2l_ddr_mc_read
   1195 renesas_rzv2l_ddr_mc_write
    541 renesas_rzv2l_ddr_phy_read
    514 renesas_rzv2l_ddr_phy_write
$ grep -o 'ddr_event .*' trace.log | sort | uniq -c
      2 ddr_event init done
      1 ddr_event init done acknowledged
     40 ddr_event mode register write
     40 ddr_event mode register write acknowledged
     81 ddr_event training command done
```

The 1195 controller writes are BL2's 507-entry parameter table, written twice, and the other set-up writes. The two "init done" events are the two STARTs: BL2 resets the controller between them and writes the table again ([`../research/bl2.md` §6](../research/bl2.md#6-the-ddr-controller-and-phy)).

**What the stub does not prove.** The DDR itself is ordinary QEMU RAM, and QEMU RAM works before BL2 writes a single register. A BL2 that skipped its DDR set-up, or trained the PHY with wrong values, would still boot in QEMU. The stub proves that BL2's code runs to completion against the contract it was written for. It does not prove that the trained values are right, that the timing is right, or that the memory would work on silicon. The stub's class in the device map is **STUB**, and the spec names the limit (§11).

## 4. How BL2 finds the firmware package

This section shows how one register decides where the rest of the chain comes from. The FIP (Firmware Image Package) is TF-A's container for the next images. The project's FIP holds three:

```
$ fiptool info tests/guests/out/spi/fip.bin
EL3 Runtime Firmware BL31: offset=0xB0, size=0x70C9, cmdline="--soc-fw"
Secure Payload BL32 (Trusted OS): offset=0x7180, size=0x6CC78, cmdline="--tos-fw"
Non-Trusted Firmware BL33: offset=0x73E00, size=0xD25B0, cmdline="--nt-fw"
```

BL2 reads the boot mode from `SYS_LSI_MODE` bits 3:0 (`P/drivers/sys.c:25-50`). The value selects the FIP's device (`P/plat_storage.c:228-265`):

| Bits 3:0 | Boot mode | BL2 reads the FIP from |
|---|---|---|
| 0 | eSD | the SD card |
| 1, 2 | eMMC, 1.8 V or 3.3 V | the eMMC |
| 3, 4 | serial flash, 1.8 V or 3.3 V | the QSPI flash, at `0x20000` |
| other | — | nowhere: `panic()` |

The QEMU machine sets the register from its `boot-mode` property, as the board latches it from the pins. With `boot-mode=4`, BL2 prints `SYS_LSI_MODE: 0x10004` and reads the same FIP from the flash. The board's own QSPI boot printed `0x10203`: bit 9 is the debug-enable pin, which is set on the EVK and clear in the machine's default.

BL2 needs every image it is set to load. If the FIP has no BL33, BL2 loads BL31 and OP-TEE, then stops:

```
NOTICE:  BL2: SYS_LSI_PRR: 0x0
ERROR:   BL2: Failed to load image id 5 (-2)
```

Image id 5 is BL33. The acceptance run builds such a FIP with `fiptool remove --nt-fw` and checks that nothing runs after this line (`tests/acceptance/m8/chain.py`). The same check without BL31 stops at image id 3. These two cases show that the images come from the flash. QEMU loads no image on this path: the command line has no `-bios`, `-kernel`, `bl32=` or `bl33=`.

## 5. Reading the flash through the window

This section shows how BL2 reads 1.3 MB from the flash with ordinary memory copies. BL2 sets up the SPI controller's external address space read mode ([`m7-firmware.md` §7](m7-firmware.md#two-ways-to-reach-the-flash)): Quad I/O Fast Read (`0xEB`, one line for the command, four for address and data), 24-bit addresses, 10 dummy cycles, and the read cache on (`P/drivers/spi_multi/spi_multi.c:111-158`). Then BL2 reads the FIP from the window at `0x20020000` with `memcpy`.

Trace the controller to see each flash command that a read of the window sends:

```
$ qemu-system-aarch64 ... -trace renesas_rzv2l_rpc_read -D trace.log
$ grep -m3 rpc_read trace.log
renesas_rzv2l_rpc_read command 0xeb address 0x00020000 length 256 burst 1
renesas_rzv2l_rpc_read command 0xeb address 0x00020100 length 256 burst 1
renesas_rzv2l_rpc_read command 0xeb address 0x00020200 length 256 burst 1
$ grep -c 'command 0xeb' trace.log
5223
```

Each command fills one 256-byte line of the read cache (`burst 1`). The reads run from `0x20000` to `0x166300`. The FIP is `0x1463B0` bytes long, so it ends at `0x1663B0`, inside the last line. That is 5221 different lines. The first line, the FIP's table of contents, is read three times: once for each image that BL2 opens (I). BL2's FIP read is this path's first use at volume. The M8-ddr-stub unit's qtest therefore reads several kilobytes across many burst boundaries first, and compares every byte with the image.

## 6. How we know it works

The checks are in the acceptance runs and the unit pages; this list only points to them:

- `tests/acceptance/m8/bl2.py`: BL2's lines up to `Booting BL31`, a `-d` log with no DDR line, and the stand-in's errors.
- `tests/acceptance/m8/chain.py`: the chain, in order, up to the Linux shell, a reboot back through BL2, boot mode 4, FIPs without BL31 or BL33, and OP-TEE called from Linux.
- the qtests `rzv2l-ddr-test` (the stub contract) and `rzv2l-rpc-test` `bl2-read` (BL2's read settings).

Each check was seen red: the mutations and broken inputs are in the units' `tasks.md` files.

## 7. Pitfalls

- **A release firmware stops without a word.** BL2 built with `DEBUG=0` has an empty crash console and polls without a timeout. A missing register shows as silence. Read the `-d unimp,guest_errors,invalid_mem` log and the monitor's PC first (`P/aarch64/plat_helpers.S:35-38`).
- **The manual can delete a register that the firmware still uses.** The revision history lists `CPG_CLKON_SRC` and `CPG_RST_SRC` as deleted, but BL2 writes and polls them. Guest code rules what is required. Record the conflict instead of choosing one source silently (manual p.3554; `P/drivers/cpg.c:254-255`).
- **A stub that answers every poll proves the code path, not the hardware.** QEMU RAM works before DDR training, so the DDR stub cannot catch a wrong training value. Label each computed value as the stub's answer to the guest, and keep the class STUB ([`../research/bl2.md` §6.1](../research/bl2.md#61-the-stub-contract)).
- **Refuse what the guest does not do.** The DDR stub accepts only the offsets and the seven training commands that BL2 uses, and refuses the rest with a bus error. If a new TF-A version touches another register, the boot fails visibly and does not continue on a value nobody chose (`qemu/hw/misc/renesas_rzv2l_ddr.c:281-289`).
- **A stand-in must stop where the original would fall back.** The ROM tries the next boot source when the flash has no loader. A stand-in that continued would hide a broken image. Stop QEMU and name the cause.
- **A boot-mode register value has more than the boot mode in it.** `SYS_LSI_MODE` also reports the debug-enable pin (bit 9) and a security bit. BL2 masks bits 3:0 only, so compare those bits, not the whole value, with the EVK (`0x10203` on the EVK, `0x10003` in the machine's default).
- **A firmware package can be in a different place in another flow.** The vendor kernel's device tree labels the FIP partition at `0x1D000`, from an older Renesas flow. This TF-A reads the FIP at `0x20000` only (`P/include/rz_soc_def.h:51`). Build the image for the TF-A you run.
- **Absence of `-bios` is not proof by itself.** That the firmware came from the flash shows best as a failure: a FIP without one image must stop BL2 at that image. A check that only looks for banners passes as well when QEMU loads the images itself.
