# M5-sdhi — spec

**Milestone:** M5 (storage; first unit). **Requirements:** REQ-SDHI-001, REQ-SDHI-002 (proposed with this page).

## Scope

**The SD/MMC host interface** (manual §40, "SDHI"), channels 0 and 1 at `0x11C00000` and `0x11C10000`, as the unchanged Linux driver `renesas_sdhi` uses them, with an SD card behind SDHI0. Today both windows are logged stubs (UNIMP: reads return 0), so the driver's requests time out after 5 s.

- **Register file** (Table 40.2, p.3262-3263): the SD card interface registers at a 4-byte stride (`bus_shift = 2`), 16-, 32- and 64-bit accesses, with manual reset values (§40.2, p.3264-3298). Flags in `SD_INFO1`, `SD_INFO2` and `DM_CM_INFO1/2` clear on a write of 0; a write of 1 keeps them (§40.2.6-40.2.7 p.3271-3277, §40.2.28 p.3295, §40.2.30 p.3297).
- **Command and data engine** on QEMU's SD bus (`hw/sd/sd.c` card model, `-drive if=sd`): command, response registers, multi-block transfers with the automatic CMD12 (`SD_STOP.SEC`), the data port `SD_BUF0`, busy and clock-ready bits (`CBSY`, `SCLKDIVEN`), response timeout when no card answers.
- **Internal DMAC** (§40.2.25-40.2.32 p.3293-3298): `DM_CM_DTRAN_MODE/CTRL`, `DM_CM_RST`, `DM_CM_INFO1/2` and masks, `DM_DTRAN_ADDR`; transfers between the card and guest RAM; `DTRANEND0/1` interrupts.
- **PIO path** through `SD_BUF0`: 16-bit accesses (mainline) and 64-bit accesses (the vendor kernel sets `TMIO_MMC_64BIT_DATA_PORT`, `rz_linux-cip` `212f6e88b7` `renesas_sdhi_internal_dmac.c:110`); each access moves as many bytes as its width (A; not readable on the EVK without a write).
- **Interrupts:** SPI 104 (SDHI0) and SPI 106 (SDHI1), level (Table 8.2 p.537). SPI 105/107 (SDIO) stay low: no SDIO card (the EVK counts 0 on SPI 105, evidence §8).
- **Card topology:** SDHI0 gets the first `-drive if=sd` as an SD card. SDHI1 has no card: card detect reads "no card" and the driver powers the slot off, as on the EVK (evidence §8).
- **Not in this unit:** the Sampling Clock Controller (SCC, `+0x1000`, §40.6-40.7) stays a logged stub: it is used only for HS200/SDR104 tuning, which neither the EVK (high speed, 3.3 V) nor QEMU's card models reach. UHS signalling (CMD11), eMMC on SDHI0 (boot mode 1), and a card on SDHI1 are later units if wanted.

## What the guest needs

Both kernels build `CONFIG_MMC_SDHI=y` and `CONFIG_MMC_SDHI_INTERNAL_DMAC=y` (effective `.config`: G0 `:7479-7482`, G1 `:5080-5083`). Paths below are linux v6.12.59 `drivers/mmc/host/`; the vendor kernel is the same except where named.

- **Match:** `renesas,rzg2l-sdhi` (`renesas_sdhi_internal_dmac.c:289`): `bus_shift = 2`, `scc_offset = 0x1000`, `max_segs = 1` (`:108-122`), quirks `fixed_addr_mode`, `hs400_disabled` (`:214-217`).
- **VERSION** must read `0xCC10` (manual §40.2.21 p.3291): the driver takes its Gen3 paths, `HOST_MODE` width switching and `SD_OPTION.EXTOP` from it (`renesas_sdhi_core.c:56`, `:76`, `:604`).
- **DMA is the normal path, not optional.** Every data request goes to the internal DMAC; the driver falls back to PIO only when `dma_map_sg()` fails or the buffer is not 128-byte aligned (`renesas_sdhi_internal_dmac.c:389-399`). A DMA request completes on both `SD_INFO1` access end and `DM_CM_INFO1.DTRANEND`, and `DM_CM_DTRAN_CTRL.DM_START` is written after the command response, so the card data waits for it.
- **Interrupt mask** at probe: `0x8b7f031d` (`tmio_mmc.h:109`), the manual reset values of `SD_INFO1_MASK`/`SD_INFO2_MASK`. The handler writes the status back with only the bits it keeps set, then acks each source with a 0 write.
- **Writes gated by status:** before 16-bit writes to `SD_CMD`, `SD_STOP`, `SD_SECCNT`, `SD_SIZE`, `SD_OPTION`, `SDIO_MODE`, `CC_EXT_MODE`, `HOST_MODE` the driver waits for `CBSY` = 0, and before `SD_CLK_CTRL` for `SCLKDIVEN` = 1; on a timeout it skips the write.
- **Clocks and reset** (CPG, already modelled): SD mux `0x218`, `CLK_ON 0x554` bits 0-7, `RST 0x854` bits 0-1, `CLKSTATUS` bits 28-29.
- **Start states:** firmware mode: manual reset values. Direct mode: the same (A) until EVK-R74-R78 (the U-Boot reads in `../../evidence/requests.md` §1.8) are measured; U-Boot uses SDHI0 by PIO only, and Linux resets the controller at probe (`SOFT_RST`, `DM_CM_RST`, the CPG reset).

The register-by-register list (reset values, bits the driver reads and writes, line numbers) is built with the `register-evidence` skill as the first task and recorded in `docs/research/sdhi.md`.

## Exit criterion

1. qtests assert the manual reset values, the write-0-to-clear rule, `VERSION`, a command with no card (response timeout), a single-block and a multi-block transfer by PIO and by DMA; each seen red on a mutation.
2. G0 and G1 boot with a project-built SD image (`-drive if=sd`): `mmc0: new … SD… card`, the partitions appear, no `timeout waiting for hardware interrupt`; SDHI1 reports no card.
3. Persistence (REQ-SDHI-002): in the guest, write files across block and transfer boundaries to an ext4 partition, record their hashes, `sync`, unmount; stop QEMU; check the hashes in the image from the host; boot again and check them in the guest. Clean unmount only: no claim about power loss.
4. M4 acceptance and the serial-port regression suite still pass; the `-d` log lists only recorded stub windows.

## Evidence

Manual §40 (p.3259-3347), Table 8.2 (p.537); EVK evidence §8 (O: SD card, 4-bit, high speed, 50 MHz, 3.3 V; SDHI1 empty; interrupts on SPI 104 only); the vendor U-Boot's PIO driver (`drivers/mmc/sh_sdhi.c`, `4eebfbaa4e`) for the direct-mode state; leads from a research packet in the working area.

## For the operator

- **SD card on SDHI0, not eMMC.** The DTB describes SDHI0 as an 8-bit eMMC with HS200, but the EVK boots from eSD and runs an SD card at high speed behind that node (evidence §8). The unit models that. An eMMC for boot mode 1 is a separate decision.
- **Five U-Boot reads** (EVK-R74-R78) would fix the direct-mode start state and confirm `VERSION`, `CC_EXT_MODE` and the SCC reset values; they need a session at the U-Boot prompt. U-Boot also writes an offset the manual does not list (`0x08`); reading it could abort and reboot the board, so it is not in the list. The model accepts writes there and logs them.
- **No real-time behaviour:** transfers complete at once and the data timeout counter never fires; only "no card" ends in a timeout.

## Unit end

- **Met:** exit criteria 1-4. qtest `rzv2l-sdhi-test` (5 tests, 10 mutations red, `tasks.md`); M5 acceptance on G0 and G1: the card is found, ext4 written and read back across a restart, the image checked by `e2fsck` and `debugfs` on the host; M4 acceptance and the serial-port regression suite pass.
- **Seen in the run (O, model):** Linux probes SDIO with CMD5 and CMD52; QEMU's SD memory card does not answer them (logged by the card model, allowed in `tests/acceptance/m5/expected/log-allow.txt`). The card is `mmcblk0` or `mmcblk1` from boot to boot: the stock device trees have no `mmc` aliases, so the number depends on probe order (the G2 image adds the aliases for this reason).
- **Next (M5, layer verified: the Linux block device):** a root file system on the SD card, booting user space from it instead of the initramfs. With no aliases, `root=` needs a partition UUID, given by `-append` (a recorded gap, as the board's U-Boot sets the boot arguments). The eMMC behind SDHI0 in eMMC boot mode (`boot-mode=1`, an `emmc` card model) is a separate decision.
