# M5: storage

> **Context.** Milestone M5 (spec [§17](../spec/project.md#17-milestones)): an SD card with an ext4 file system, used by the unchanged Linux driver. Unit M5-sdhi: [spec](../units/M5-sdhi/spec.md), [tasks](../units/M5-sdhi/tasks.md), register evidence [`../research/sdhi.md`](../research/sdhi.md). The manual chapter is §40 (SD/MMC host interface). Code lines are at fork commit `6eaee48d4e`.

## 1. The SD/MMC host interface (unit M5-sdhi)

### 1.1 What the kernel needs

Both kernels drive SDHI0 and SDHI1 with `renesas_sdhi_internal_dmac`. The driver uses the controller's own DMA engine for every data request. It falls back to the data port `SD_BUF0` only when a buffer is not 128-byte aligned (`renesas_sdhi_internal_dmac.c:389-399`). So a model without the DMA engine would time out on almost every read. The DMA engine is part of the controller, not the separate DMAC block at `0x11820000`.

The board's own Linux shows what to model first. The EVK runs an SD card in SDHI0 at "high speed": 4 bits, 50 MHz, 3.3 V ([EVK evidence §8](../evidence/EVK-2026-10-30-linux.md)). QEMU's SD card model offers the same mode. The faster modes need the sampling clock controller (SCC) for bus tuning; neither the EVK nor QEMU's card uses them.

### 1.2 How the model is shaped

The model is one QEMU device per channel, `renesas-rzg2l-sdhi` (`qemu/hw/sd/renesas_sdhi.c`). It owns an SD bus, the same bus type QEMU's other SD hosts use. The board puts a card on it for each `-drive if=sd`: index 0 is the slot on the module (SDHI0), index 1 the slot on the carrier board (SDHI1).

- **Registers 8 bytes apart.** Table 40.2 places each register at an 8-byte step, and allows 16-, 32- and 64-bit accesses. The driver uses 16-bit accesses for most registers and two 16-bit halves for 32-bit values. The model therefore reads and writes part of an 8-byte slot (`sdhi_read`, `sdhi_write`).
- **One command sequence.** A write to `SD_CMD` sends the command to the card through `sdbus_do_command()` and puts the response in `SD_RSP10`/`SD_RSP54` (Table 40.3). `SD_INFO2.CBSY` is 1 until the sequence ends. A command that the card does not answer ends with `ERR6`, the response timeout.
- **Data waits for the DMA start.** The driver writes `DM_START` only after the command response (manual Figures 40.22-40.23). So the model holds the transfer until then. It then moves every block between the card and guest RAM, sends the automatic CMD12, and sets `DTRANEND1` (card to memory) or `DTRANEND0` (memory to card).
- **Write 0 to clear.** The flags in `SD_INFO1`, `SD_INFO2` and `DM_CM_INFO1/2` clear on a 0 write; a 1 leaves them. The interrupt handler depends on that: it writes back the flags it keeps and acks each one with a 0 (`tmio_mmc_core.c:711-715`).
- **The reset line.** `CPG_RST_SDHI` drives each channel's reset, as `CPG_RST_WDT` does for the watchdog. While the reset is applied, the channel reads its reset values and ignores writes.
- **No timing.** A sequence ends within the register access that starts it. Linux does not notice. The data timeout counter never fires, which is recorded in the spec.

### 1.3 The proof

`tests/qtest/rzv2l-sdhi-test.c` checks the reset values of §40.2, the CPG reset, a command with no card, one block each way through `SD_BUF0`, and DMA transfers with the automatic CMD12. The data comes from a card image that the test writes, and the written blocks are read back from the image file. Ten mutations each turn one check red ([tasks](../units/M5-sdhi/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)). The acceptance run (`tests/acceptance/m5/run.sh`) boots both kernels with a fresh SD image and does three steps:

1. In the guest, it writes files of 1, 513, 4097 and 1 MiB + 7 bytes, then syncs and unmounts.
2. On the host, `e2fsck` and `debugfs` check the image.
3. A new QEMU reads the files back.

## 2. Pitfalls

- **A driver's "fallback" can be its rare path.** The SDHI driver has a PIO fallback, but uses it only for unaligned buffers. A model with PIO only would look plausible and still time out on almost every request. Read the condition before you trust the fallback (`renesas_sdhi_internal_dmac.c:389-399`).
- **The DMA start comes after the response.** The DMA engine and the card are two parties, and the driver starts the DMA engine in a work item after the command response interrupt. A model that moves the data when the command is written sets the "access end" flag before the driver is ready for it (manual Figures 40.22-40.23).
- **Register stride is a property of the SoC, not of the IP.** The same TMIO-family controller has its registers 2 or 4 bytes apart on other Renesas parts and 8 bytes apart here (`bus_shift = 2`, `tmio_mmc.h:211-264`). The driver reads 16-bit halves at `+0` and `+8`, so a model with 32-bit registers at a 4-byte step would answer the wrong offsets (Table 40.2).
- **"Write 0 to clear" is not "write 1 to clear".** Most QEMU devices clear flags with a 1. Here a 1 keeps the flag. The interrupt handler writes 1s to the flags it still needs, so a write-1-to-clear model would lose them (§40.2.6 p.3271).
- **The device tree does not say what is in the slot.** The DTB describes SDHI0 as an 8-bit eMMC with HS200. The EVK boots from an SD card in that slot (eSD), and U-Boot only changes the I/O voltage supply. Linux finds whatever card answers, so the model presents an SD card (EVK evidence §8).
- **Without `mmc` aliases, numbering is a race.** The two hosts probe in parallel, so the card is `mmcblk0` in one boot and `mmcblk1` in the next. The acceptance run looks for `/dev/mmcblk*p1`.
