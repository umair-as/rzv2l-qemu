# SPI Multi I/O Bus Controller (RPC / SPIBSC) and its SPI-NOR flash: what the guests need

The register contract of the SPI multi I/O bus controller (Renesas calls it RPC or SPIBSC) and of the board's serial NOR flash, as the vendor U-Boot, the vendor kernel and TF-A use them. The model and its qtest are written from this page; the unit is [M7-rpc-spinor](../units/M7-rpc-spinor/spec.md).

**Labels:** **F** = stated by the manual or visible in the cited code; **I** = code-derived inference; **A** = assumption; **O** = EVK observation.

**Citation key:** manual = RZ/V2L HW manual Rev 1.50, §25 (p.1474-1530). U-Boot = renesas-u-boot-cip `4eebfbaa4e`; Linux = rz_linux-cip `212f6e88b7` (G1); TF-A = rzg_tf-a `f59ed5a31` (`docs/sources.md`).

## 1. The block

| Item | Value | Label, cite |
|---|---|---|
| MMIO | registers `0x10060000` (64 KiB; 27 registers `0x00`-`0x88`), external address space (read window) `0x20000000` 256 MiB, write buffer `0x10070000` (64 KiB, DT `wbuf`) | F: Table 25.2 p.1477, Table 25.3 p.1517; DT `reg`, `reg-names = "regs", "dirmap", "wbuf"` |
| Access | 32-bit only, except SMRDR0/1 and SMWDR0/1: 8, 16, 32 | F: Table 25.2 |
| Interrupt | SPI 41 (SPIHF: the HyperFlash INT# input), level-high; no driver requests it | F: DT `interrupts`; Linux `renesas-rpc-if.c` has no `request_irq` |
| Clocks, reset | `CLK_ON 0x550` bits 0-1 (SPI_CLK2, SPI_CLK), `RST 0x850` bit 0 (the CPG model has them); Linux resets the block at probe (`renesas-rpc-if.c:237`) | F: DT `clocks`, `resets`; device map row |
| DMA | the read window can be a DMA source (PHYCNT.HS); no guest uses it (`renesas-rpc-if.c:247`: "DMA Transfer is not supported") | F |
| Flash on the board | Micron MT25QU512A, 64 MiB, 1.8 V, chip select 0, one device (`CMNCR.BSZ = 00`) | F: DT `flash@0 compatible = "micron,mt25qu512a"`; O: the board's U-Boot prints `SF: Detected mt25qu512a ... total 64 MiB` |
| Consumers | U-Boot `rpc_spi` (`CONFIG_RENESAS_RPC_SPI=y`, compatible `renesas,r9a07g054l-spibsc`), board code in `s_init` and `board_init`; Linux `rpc-if` + `spi-rpc-if` (`CONFIG_RENESAS_RPCIF=y`, `CONFIG_SPI_RPCIF=y` in G1; `=m` in G0, so not a G0 consumer), then `spi-nor` and the DT's fixed partitions; TF-A BL2 `spi_multi.c` (SPI boot only: M8) | F: effective `.config`s (`tests/guests/out/fw/u-boot.config`, `out/g1/linux/.config`, `out/g0/linux/.config`) |
| Today (UNIMP) | U-Boot: `jedec_spi_nor spi-flash@0: unrecognized JEDEC id bytes: 00, 00, 00`, `Failed to set up SPI slave`, then about 470 000 reads of CMNSR (`0x48`) during its 1 s timeouts; G1 Linux: `spi-nor spi1.0: unrecognized JEDEC id bytes: 00 00 00 00 00 00` | O: M7 acceptance serial and `-d` logs |

## 2. What each guest does

**U-Boot.**
1. `s_init` writes `CMNCR = 0x01FFF300` (`board/renesas/rzv2l-dev/rzv2l-dev.c:120`).
2. Probe: `DRDRENR = 0`; PHYOFFSET1 read, bit 28 set, written back (`drivers/spi/renesas_rpc_spi.c:455-457`).
3. `board_init` → `board_spinor_op_nvcr_setup` (`rzv2l-dev.c:171-227`): `spi_setup_slave` (spi-nor probe: RDID and friends), read NVCR (`0xB5`, 2 bytes), clear bit 4, WREN (`0x06`), write NVCR (`0xB1`, 2 bytes). Every boot.
4. Claim (`renesas_rpc_spi.c:216-235`): PHYCNT = CAL | STRTIM(7) | `0x260`; CMNCR = MD (manual) or 0 | SFDE | MOIIO = 11 | IOFV = 11 | BSZ 0; SSLDR = 7/7/7; DRCR = SSLN | RBURST(31) | RCF | RBE | SSLE, then a DRCR read. Release: PHYCNT without CAL, the same DRCR flush.
5. **Reads (data in), every one:** external address space read mode (`renesas_rpc_spi.c:283-314`): DRCMR = command, DRENR = CDE | ADE (0, 7 or F) | DME, DREAR (4-byte address: EAV = offset >> 25, EAC 1), DRDMCR, then `memcpy_fromio` from the read window at the flash offset. With no address phase (RDID, RDSR, RDNVCR) the data comes from offset 0 of the window, so the controller's burst and read cache (RBE = 1) must return the command's byte stream in order.
6. **Writes and commands without data:** manual mode (`renesas_rpc_spi.c:315-394`): SMCR = 0, SMCMR, SMADR, SMDMCR, SMOPR, SMDRENR = 0, then per 4 bytes SMENR (SPIDE F/E/C/8), SMWDR0, SMCR = SPIWE | SPIE (| SSLKP until the last word), wait TEND = 1 (1 s, `:198-204`), finally wait SSLF = 0 (1 s). **1- and 2-byte data are written as a 32-bit word with the data in the top bytes** (`data << 24`, `<< 16`, `:358-370`).
7. The `sf` command and the environment are not on the boot path (`CONFIG_ENV_IS_IN_MMC`).

**Linux (G1).**
1. `rpcif_hw_init_impl` (`renesas-rpc-if.c:231-286`): reset; PHYADJ2/1 (driver names PHYWR `0x74`, PHYADD `0x70`, `renesas-rpc-if-regs.h:120-121`) = `0xA5390000`/`0x80000000`, `0x8080`/`0x80000022`, `0x8080`/`0x80000024`, PHYCNT CKSEL = 3, `0x30`/`0x80000032` (`:217-229`); read-modify-write of PHYCNT (PHYMEM 0, HS 0, STRTIM 7), PHYOFFSET1 (DDRTMG 3), PHYOFFSET2 (OCTTMG 4), CMNCR (MOIIO 1, IOFV 3, BSZ 0); DRCR = RCF, a DRCR read; SSLDR = 7/7/7.
2. Manual transfers (`:522-623`): PHYCNT CAL, CMNCR MD = 1, SMCMR, SMOPR, SMDMCR, SMDRENR, SMADR; writes in chunks of 4 (SMENR SPIDE, SMWDR0, SMCR SPIWE | SPIE | SSLKP); reads with an address in chunks of 4 (SMADR advanced, SMCR SPIRE | SPIE, then SMRDR0). Wait for TEND = 1, 1 s (`:333-338`). **SMWDR0/SMRDR0 are accessed at the transfer size**: `writeb`/`writew` for 1/2 bytes (`:93-160`, the hardware manual's "same size as the transfer size").
3. Reads without an address (RDID, RDSR, ...): the driver comment says manual mode "spoils the data" for these, so it uses the read window with DRCR = RBE | RBURST(32) (`:551-578`).
4. Flash reads (`rpcif_dirmap_read_impl`, `:822-848`): DRCR = 0 (normal read, no cache), DREAR = EAV(offs >> 25) | EAC 1, DRENR as prepared, then `memcpy_fromio` from the window: every bus access is one flash read at that address.
5. spi-nor identifies `mt25qu512a` by the 6-byte ID `20 BB 20 10 44 00`; the entry has no size, so the size and opcodes come from the flash's SFDP tables (`drivers/mtd/spi-nor/micron-st.c:466-471`). With only a 3-byte ID it falls back to `n25q512a` (64 MiB, no SFDP, `:473-479`).

**TF-A BL2 (M8, SPI boot):** `spi_multi_setup` sets the external read mode (`plat/renesas/rz/common/drivers/spi_multi/spi_multi.c:110-158`); the same timing sequence as Linux; 1-byte manual writes also as `data << 24` (`SMWDR0_1BYTE_DATA_BIT_SHIFT`, `include/drivers/spi_multi/MT25QU512ABB/spi_multi_reg_values.h:101`). For the MT25QU512A, `spi_multi_setup_device` does nothing.

## 3. Registers

Start state: the manual reset value in both start states. On the EVK the boot source is the SD card, and BL2 touches the controller only for SPI boot (TF-A `plat/renesas/rz/common/plat_storage.c:204-206`, `:236-237`), so U-Boot finds reset values unless its own `s_init` wrote them (I). The write buffer is not used by any guest.

| Offset | Register | Reset (manual) | Fields used | Class | Guest | Cite |
|---|---|---|---|---|---|---|
| `0x00` | CMNCR | `0x01557301` | MD 31; bit 24 reads 1; MOIIO3-0 23:16; IO3FV, IO2FV, IO0FV; BSZ 1:0 (00 one flash) | config | U-Boot `s_init`, claim; Linux hw_init, manual | §25.4.1 p.1478-1480 |
| `0x04` | SSLDR | 0 | SPNDL 18:16, SLNDL 10:8, SCKDL 2:0 (timing only) | config, no effect | both | §25.4.2 p.1481 |
| `0x0C` | DRCR | `0x001F0100` | SSLN 24 (W, reads 0), RBURST 20:16 (+1 units of 8 bytes), RCF 9 (W, reads 0: flush the read cache), RBE 8, SSLE 0 | config + command | both | §25.4.3 p.1482-1483 |
| `0x10` | DRCMR | `0x00A00000` | CMD 23:16, OCMD 7:0 | config | both | §25.4.4 p.1484 |
| `0x14` | DREAR | 0 | EAV 23:16 (flash address bits 32:25), EAC 2:0 (window bits 24:0 + EAC valid) | config | both | §25.4.5 p.1485, §25.5.3 p.1518 |
| `0x18` | DROPR | 0 | OPD3-0 | config | both | §25.4.6 |
| `0x1C` | DRENR | `0xA222D400` | CDB, OCDB, ADB, OPDB, DRDB (00 1-bit, 10 4-bit); DME 15, CDE 14, OCDE 12, ADE 11:8 (0000, 0111 24-bit, 1111 32-bit), OPDE 7:4 | config | both | §25.4.7 p.1487-1488 |
| `0x20` | SMCR | 0 | SSLKP 8, SPIRE 2, SPIWE 1, SPIE 0 (W, reads 0: start a transfer; valid only with TEND = 1) | command | both | §25.4.8 p.1489 |
| `0x24` | SMCMR | 0 | CMD 23:16, OCMD 7:0 | config | both | §25.4.9 |
| `0x28` | SMADR | 0 | ADR 31:0 | config | both | §25.4.10 |
| `0x2C` | SMOPR | 0 | OPD3-0 | config | both | §25.4.11 |
| `0x30` | SMENR | `0x00004000` | as DRENR plus SPIDB 17:16, SPIDE 3:0 (1000 8 bits, 1100 16, 1111 32 with BSZ 00); ADE also 0100 (ADR 23:16), 0110 (23:8) | config | both | §25.4.12 p.1490-1491 |
| `0x38`, `0x3C` | SMRDR0, SMRDR1 | undefined | read data; SMRDR1 unused with BSZ 00 | status (data) | Linux | §25.4.13-14 p.1492-1493 |
| `0x40`, `0x44` | SMWDR0, SMWDR1 | 0 | write data; SMWDR1 unused with BSZ 00 | config (data) | both | §25.4.15-16 p.1494-1495 |
| `0x48` | CMNSR | `0x00000001` | SSLF 1 (SSL asserted), TEND 0 (transfer ended); read-only | status (level) | both poll TEND (1 s); U-Boot polls SSLF = 0 (1 s) | §25.4.17 p.1496 |
| `0x58` | DRDMCR | `0x0000000B` | DMCYC 4:0 (n + 1 cycles) | config | both | §25.4.18 |
| `0x5C` | DRDRENR | `0x00005101` | HYPE 14:12, ADDRE 8, OPDRE 4, DRDRE 0 (SDR when 0) | config | both write 0 | §25.4.19 |
| `0x60` | SMDMCR | 0 | DMCYC | config | both | §25.4.20 |
| `0x64` | SMDRENR | 0 | HYPE, ADDRE, OPDRE, SPIDRE | config | both write 0 | §25.4.21 |
| `0x70`, `0x74` | PHYADJ1, PHYADJ2 | 0, 0 | timing adjustment values (`0x80000000`, `0xA5390000`, ...) | config, no effect | Linux, TF-A | §25.4.26-27 p.1512 |
| `0x7C` | PHYCNT | `0x00000263` | CAL 31 (W, reads 0), CKSEL 17:16, HS 18, WBUF 2, WBUF2 4, PHYMEM 1:0 (00 serial flash SDR); bits 9, 6, 5 read 1 | config | both | §25.4.22 p.1505-1507 |
| `0x80` | PHYOFFSET1 | `0x21511144` | DDRTMG 29:28; the other set bits read 1 | config | both | §25.4.23 p.1508-1509 |
| `0x84` | PHYOFFSET2 | `0x00000431` | OCTTMG 10:8; bits 5, 4, 0 read 1 | config | Linux | §25.4.24 p.1510 |
| `0x88` | PHYINT | `0x07070002` | RSTEN 26, WPEN 25, INTEN 24, RSTVAL 2, WPVAL 1, INT 0 (R) | config | Linux (HyperFlash only) | §25.4.25 p.1511 |

Any other offset: "reading returns an undefined value; do not write" (Table 25.2 note): logged as a guest error, reads 0.

## 4. Behaviour

**Manual mode** (§25.5.7 p.1519-1520, §25.5.8 Figure 25.18 p.1521). Writing SPIE = 1 starts one transfer: command (CDE), optional command (OCDE), address (ADE: ADR[23:16], [23:8], [23:0] or [31:0]), option data (OPDE, OPD3 first), dummy cycles (DME), then data (SPIDE bytes, written from SMWDR0 when SPIWE, read into SMRDR0 when SPIRE). TEND reads 0 while the transfer runs and 1 when it ends; SSLF is 1 while SSL is asserted. SSLKP = 1 keeps SSL asserted to the next transfer, which then continues the same flash command without re-sending the enabled phases (§25.5.10 (2)); SSLKP = 0 negates SSL at the end. Bit sizes (1-bit or 4-bit) and SDR/DDR change only the wire timing.

**Data byte order (conflict, recorded).** The manual sends the data as DATA[3], [2], [1], [0], enabled by SPIDE[3..0], and calls SPIDE = 1000 "data at address 0" (F: Figure 25.18; SMENR p.1491). It does not say which bits of a 32-bit access hold address 0. The guests disagree on the face of it: TF-A and U-Boot write 1 and 2 bytes as a 32-bit word with the data in the top bytes (`<< 24`, `<< 16`), and U-Boot's NVCR write is right only if the two bytes go out lower byte first: written the other way it would change the flash's power-on configuration on every boot, and a board that boots from this flash (the Renesas QSPI boot flow) would stop booting after its first U-Boot run (I; our board boots from the SD card, so this is not observed here); Linux writes and reads them with `writeb`/`writew`/`readb`/`readw` at offset 0. One rule satisfies all three: **for an N-byte transfer the bytes sent (or received) are the top N bytes of the 32-bit data register, lowest first, and an N-byte access at offset 0 reaches exactly those bytes; a 32-bit access is a plain little-endian word** (I). The model follows this rule (operator decision, 2026-11-02: accept the inference); an EVK measurement could settle it (§6).

**External address space read mode** (§25.5.5 p.1517-1518, §25.5.6 p.1519). A read of the window becomes a flash read: command, optional command, address (window address [23:0] for ADE 0111; [31:0] for ADE 1111, with bits 32:25 from DREAR.EAV over the bits EAC leaves), option data, dummy, data. With RBE = 0 one access reads its own size (8, 16, 32 bits). With RBE = 1 a miss reads 8 × (RBURST + 1) bytes from the 8-byte boundary into the read cache (32 lines of 8 bytes, filled in order by a write pointer, tags = flash address bits 32:3); a hit is served from the cache without a flash access. RCF = 1 invalidates every line. SSLE = 1 keeps SSL asserted after a burst; a continuing address continues the same flash command, a non-continuous one ends it (§25.5.5 (3)). **A command without an address phase** returns its byte stream from offset 0 of the window through one burst (I: how U-Boot and Linux read RDID, `renesas_rpc_spi.c:283-314`, `renesas-rpc-if.c:551-578`).

**Write buffer** (§25.5.13, PHYCNT.WBUF/WBUF2): no guest uses it. Not modelled: a write to the `wbuf` window or WBUF = 1 is logged as unimplemented.

## 5. The flash (MT25QU512A)

QEMU's `m25p80` models the Micron N25Q/MT25Q command set, including the non-volatile configuration register (RDNVCR `0xB5`, WRNVCR `0xB1`) and its effect after reset (4-byte address default, dummy cycles, XIP; `hw/block/m25p80.c:906-937`). It has no `mt25qu512a`: `n25q512a11` has the ID `20 BB 20` without the extended bytes. The guests need:

| Item | Need | Source |
|---|---|---|
| JEDEC ID | `20 BB 20 10 44 00` (6 bytes) | F: Linux `micron-st.c:466`, U-Boot `spi-nor-ids.c:316`; the board's name `mt25qu512a` (O) is consistent; O: the board returns these bytes (EVK-L16, `../evidence/EVK-2026-11-04-spi-flash.md`) |
| Size, sectors | 64 MiB, 64 KiB sectors, 4 KiB subsectors | F: U-Boot `INFO6(..., 64 * 1024, 1024, ...)`; O: `total 64 MiB`, `erase size 4 KiB` |
| SFDP | Linux sizes the `mt25qu512a` from SFDP; without it Linux names the part `n25q512a` | F: `micron-st.c:466-479`; O: the board's 136 bytes (SFDP 1.6, BFPT and 4-byte address table), EVK-L16 |
| Contents | `bl2` 0-`0x1D000`, `fip` `0x1D000`-`0x2000000`, `user` `0x2000000`-`0x4000000` (G1 DT); G0 DT: `boot` 32 MiB, `user` 32 MiB | F: DTs |

## 6. Open items

- **Data byte order** (§4): an EVK read of NVCR before and after U-Boot's rewrite would confirm the rule; it needs a way to read NVCR on the board (no tool in the product image is known).
- Not modelled: HyperFlash, Octal-SPI, two flashes (BSZ = 01), DDR, the write buffer, DMA high-speed mode (HS), the SPIHF interrupt, wire timing (SSLDR, PHY offsets, timing adjustment, CAL).
