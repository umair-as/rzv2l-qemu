# M7-rpc-spinor — spec

**Milestone:** M7 (real firmware; fourth unit, which completes M7). **Requirements:** REQ-MACH-005 (SoC blocks the boot touches), spec §11 ("RPC / SPIBSC: functional by M7"). **Status:** written; implementation follows.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The register contract, guest sequences and citations are in [`research/rpc.md`](../../research/rpc.md).

## Scope

**The SPI multi I/O bus controller** (RPC / SPIBSC) at `0x10060000` (registers), `0x20000000` (256 MiB read window), `0x10070000` (write buffer), and **the board's SPI-NOR flash**, a Micron MT25QU512A (64 MiB) on chip select 0. Today the windows are UNIMP stubs: U-Boot and the vendor kernel find no flash and say so (device map row "RPC / SPIBSC").

- **New model `renesas-rzv2l-rpc`** (FUNCTIONAL / faithful), fork `hw/ssi/`: the 27 registers of Table 25.2 (p.1477) with their reset values and read-only bits; **manual mode** (SMCR.SPIE starts a transfer: command, optional command, address, option data, dummy, data; TEND, SSLF; SSLKP keeps SSL asserted); **external address space read mode** (normal read; burst read through the 32-line read cache, RBURST, RCF, SSLE; DREAR's 32-bit address); the flash on an SSI bus with one chip select. Transfers complete at once (TEND reads 1 again on the next read). Both start states: the manual reset values (BL2 sets the controller up only for SPI boot, `research/rpc.md` §3).
- **The flash:** QEMU's `m25p80` with a new part `mt25qu512a`: ID `20 BB 20 10 44 00`, 64 MiB, 64 KiB sectors and 4 KiB subsectors, the Micron command set and non-volatile configuration register `m25p80` already models. Its contents come from `-drive if=mtd,format=raw,file=<64 MiB image>`; without one the flash is erased (all `0xFF`) and holds writes until QEMU exits.
- **SoC and board wiring:** the controller in the SoC with its clocks and reset (CPG `CLK_ON 0x550` b0-1, `RST 0x850` b0: a held reset or stopped clock fails visibly, as for SDHI), SPI 41; the flash on the board (`hw/arm/rzv2l-smarc.c`).
- **Source conflict, recorded (`research/rpc.md` §4):** which bits of SMWDR0/SMRDR0 carry 1- and 2-byte data. TF-A and U-Boot use the top bytes of a 32-bit access; Linux uses byte and halfword accesses at offset 0. The model follows the one rule that serves all three (I): an N-byte transfer uses the top N bytes, lowest first, and an N-byte access at offset 0 reaches them.
- **Not modelled** (each fails visibly or is recorded): HyperFlash and Octal-SPI (PHYCNT.PHYMEM 11, HYPE ≠ 0: logged, transfer not done), two flashes (BSZ = 01: logged), DDR (data as SDR, logged once), the write buffer (window and WBUF: `-d unimp`), DMA high-speed mode (HS), the SPIHF interrupt, wire timing (SSLDR, PHY offsets, timing adjustment, CAL), 1-bit vs 4-bit lanes (data is bytes on the SSI bus).

## What the guest needs

1. **U-Boot** (`research/rpc.md` §2): `s_init` CMNCR; probe PHYOFFSET1; `board_init` NVCR rewrite on every boot: RDID and RDNVCR through the read window with the read cache, WREN and WRNVCR in manual mode with 2-byte data in the top bytes; TEND and SSLF waits of 1 s each.
2. **Linux G1:** `rpcif_hw_init` (reset, timing sequence, PHYCNT/PHYOFFSET/CMNCR updates, DRCR RCF); RDID through the window with RBE; SFDP and status reads in manual mode (SMRDR0); `spi-nor` names `mt25qu512a` (needs SFDP, below) and registers the DT's three partitions; flash reads through the window (normal read, DRCR = 0, 32-bit address with DREAR).
3. **TF-A BL2** (M8, SPI boot): external read mode set-up only; nothing in M7.

## Design choices (operator)

1. **SFDP of the MT25QU512A.** Linux sizes this part from its SFDP tables; with only a 3-byte ID it reports `n25q512a` instead. Options: (a) read the board's SFDP and ID (read-only, under the board's Linux: `/sys/bus/spi/devices/*/spi-nor/{jedec_id,partname,sfdp}`), the recommendation; (b) the table from Micron's public datasheet (A until compared with the board); (c) no SFDP: Linux says `n25q512a`, recorded as a gap. Decided: (a); the board's ID and SFDP are recorded as EVK-L16 (`../../evidence/EVK-2026-11-04-spi-flash.md`).
2. **The data byte-order rule** above: accept the inference, or measure it on the board first.

## Exit criterion

- qtest `rzv2l-rpc-test`: reset values (Table 25.2) and read-only bits; a manual-mode read (RDID) and write sequence with TEND and SSLF; 1-, 2- and 4-byte data through SMWDR0/SMRDR0 at 32-bit and at transfer-size access; the read window in normal and burst mode against known flash contents, cache hit after a flash change, RCF flush; DREAR 32-bit addresses; the clock and reset gates. Each assertion is a manual value or flash content, each seen red under a mutation.
- U-Boot (M7 boot-loader run): no `unrecognized JEDEC id`, no `Failed to set up SPI slave`, no 1 s CMNSR timeouts; `sf probe` reports `mt25qu512a` with 64 MiB; `sf read` of a known image region matches; the NVCR rewrite leaves bit 4 cleared and the other bits as they were.
- Linux G1: `spi-nor spi1.0: mt25qu512a (65536 Kbytes)` (or the recorded `n25q512a` gap), `/proc/mtd` lists `bl2`, `fip`, `user`; reading `mtdblock` matches the image; an erase and write on `user` reads back, and survives a reboot and a QEMU restart with the same image.
- Direct mode, firmware mode and the other acceptance runs unchanged; the `-d` log gate lists no unexpected RPC line.

## Evidence

Manual §25 (p.1474-1530): Table 25.2 p.1477, §25.4 p.1478-1512, §25.5.5-25.5.8 p.1517-1521. [`research/rpc.md`](../../research/rpc.md). Device map row "RPC / SPIBSC". EVK: board U-Boot `SF: Detected mt25qu512a with page size 256 Bytes, erase size 4 KiB, total 64 MiB` (the product U-Boot, [EVK-L15](../../evidence/EVK-2026-11-02-vendor-kernel-on-board.md)).
