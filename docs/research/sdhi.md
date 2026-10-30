# SD/MMC host interface (SDHI): what the kernels need

The register contract of SDHI0 and SDHI1 as the Linux driver `renesas_sdhi` uses it. The model and its qtest are written from this page; the unit is [M5-sdhi](../units/M5-sdhi/spec.md).

**Labels:** **F** = stated by the manual or visible in the cited code; **I** = code-derived inference; **A** = assumption; **O** = EVK observation.

**Citation key:** `file:N` is linux v6.12.59 `drivers/mmc/host/<file>:N` (G0). The vendor kernel (rz_linux-cip `212f6e88b7`, G1) has the same register contract except where marked **G1**. Manual = RZ/V2L HW manual Rev 1.50, section 40.

## 1. The block

| Item | Value | Label, cite |
|---|---|---|
| MMIO | SDHI0 `0x11C00000`, SDHI1 `0x11C10000`, 64 KiB each; registers 8 bytes apart, 16/32/64-bit access | F: §40.1.3, Table 40.2 p.3262-3263 |
| Interrupts | OXMNIRQn: SPI 104 + 2n, level (card access, card detect, DMAC); OXASIOIRQn: SPI 105 + 2n (SDIO, which also raises OXMNIRQ) | F: Table 8.2 p.537, Table 40.5 p.3305 |
| Clocks, reset | `CLK_ON 0x554` bits 0-3 (SDHI0) and 4-7 (SDHI1); `RST 0x854` bit n holds channel n (IXRST); SD mux `0x218` | F: Table 7.5; the CPG model has them |
| DMA | built-in DMAC per channel, 64-bit, 32-bit address (`DM_DTRAN_ADDR` + length ≤ 2^32); the SoC DMAC is not used (no `dmas` in the DT) | F: §40.2.25-40.2.32 p.3293-3298 |
| Consumer | `renesas_sdhi_internal_dmac` (`CONFIG_MMC_SDHI_INTERNAL_DMAC=y` in both kernels), matched by `renesas,rzg2l-sdhi` (`renesas_sdhi_internal_dmac.c:289`): `bus_shift = 2`, `scc_offset = 0x1000`, `max_segs = 1` (`:108-122`) | F |
| EVK | SDHI0: SDXC card, high speed, 4-bit, 50 MHz, 3.3 V; SDHI1: no card; 85134 interrupts on SPI 104, 0 on SPI 105 | O: [EVK evidence §8](../evidence/EVK-2026-10-30-linux.md) |

## 2. Registers

Start state: the manual reset value in both start states (A for direct mode until EVK-R74-R78 are read): U-Boot drives SDHI0 by PIO, and Linux resets the controller at probe through the CPG (`renesas_sdhi_core.c:585-596`), `SOFT_RST` (`tmio_mmc_core.c:195-197`) and `DM_CM_RST` (`renesas_sdhi_internal_dmac.c:320-321`). Driver accesses are 16-bit unless named; the driver's offset `CTL_x` is the manual offset / 4 (`tmio_mmc.h:26-46`).

| Offset | Register | Reset (manual) | Fields the driver uses | Class | Guest | Cite |
|---|---|---|---|---|---|---|
| `0x000` | SD_CMD | 0 | index 5:0, MD bits 15:8 (extended mode R1/R1b/R2/R3, data, read, multi, no auto CMD12); written only when CBSY = 0 | command | `tmio_mmc_core.c:339` | §40.2.1 p.3264 |
| `0x010`/`0x018` | SD_ARG / SD_ARG1 (= [31:16]) | 0 | argument, as two 16-bit writes | config | `tmio_mmc.h` `sd_ctrl_write32_as_16_and_16` | §40.2.2 |
| `0x020` | SD_STOP | 0 | SEC bit 8 before a multi-block command, 0 after | config | `tmio_mmc_core.c:320`, `:508` | §40.2.3 |
| `0x028` | SD_SECCNT | 0 | block count, a 32-bit write | config | `tmio_mmc_core.c:756` | §40.2.4 |
| `0x030`-`0x068` | SD_RSP10 … SD_RSP7 (mirrors) | 0 | R1/R3/R6/R7 in R[39:8]; R2 R[127:8] over RSP54 and RSP10; CMD18/CMD25 response kept in R[103:72] | status | `tmio_mmc_core.c:582`, `:506` | §40.2.5, Table 40.3 |
| `0x070` | SD_INFO1 | 0; bits 10, 7, 5 are pins | INFO0 response end, INFO2 access end, INFO3/4 card removal/insertion, INFO5 card present; write 0 to clear | status (event) | `tmio_mmc_core.c:711-715`, `:118` | §40.2.6 p.3271 |
| `0x078` | SD_INFO2 | `0x2000`; bit 7 is DAT0 | ERR6 response timeout, BRE/BWE, CBSY, SCLKDIVEN, DAT0 (card busy); bit 11 written 1 | status | `renesas_sdhi_core.c:251`, `:836-875` | §40.2.7 p.3274 |
| `0x080`/`0x088` | SD_INFO1_MASK / SD_INFO2_MASK | `0x1031D` / `0x8B7F` | 1 = masked; the driver's reset mask `0x8b7f031d` (`tmio_mmc.h:109`) | config | `tmio_mmc_core.c` irq enable | §40.2.8-40.2.9 |
| `0x090` | SD_CLK_CTRL | `0x0020` | SCLKEN bit 8, DIV 7:0; written only when SCLKDIVEN = 1 | config | `renesas_sdhi_core.c:195-232` | §40.2.10 p.3280 |
| `0x098` | SD_SIZE | `0x0200` | block size | config | `tmio_mmc_core.c:754` | §40.2.11 |
| `0x0A0` | SD_OPTION | `0x40EE` | bus width bits 15/13, EXTOP bit 9 | config | `renesas_sdhi_core.c:604-607` | §40.2.12 |
| `0x0B0`/`0x0B8` | SD_ERR_STS1/2 | `0x2000` / 0 | read on error only | status | — | §40.2.13-40.2.14 |
| `0x0C0` | SD_BUF0 | — | PIO data, 16-bit (**G1**: 64-bit, `TMIO_MMC_64BIT_DATA_PORT`) | side-effect | `tmio_mmc_core.c:354-404` | §40.2.15 |
| `0x0D0`/`0x0E0` | SDIO_MODE / SDIO_INFO1_MASK | 0 / `0xC007` | IOMOD = 1, mask `0xC007` | config | `tmio_mmc_core.c:215-216` | §40.2.16, §40.2.18 |
| `0x360` | CC_EXT_MODE | `0x1010` (bits 12, 4 read 1) | DMASDRW bit 1 | config | `renesas_sdhi_core.c:907` | §40.2.19 p.3290 |
| `0x380` | SOFT_RST | `0x0007` | SDRST bit 0: 0 then 1 | command | `tmio_mmc_core.c:195-197` | §40.2.20 |
| `0x388` | VERSION | `0xCC10` | the Gen3 paths need ≥ `0xcc10` | ID | `renesas_sdhi_core.c:56`, `:69`, `:604` | §40.2.21 p.3291 |
| `0x390` | HOST_MODE | 0 | WMODE bit 0, BUSWIDTH bit 8: 64-bit for DMA, 16-bit otherwise | config | `renesas_sdhi_core.c:61-91`, `:902-909` | §40.2.22 |
| `0x820` | DM_CM_DTRAN_MODE | `0x30` | CH_NUM 17:16 (0 to card, 1 from card), BUS_WIDTH 5:4 = 11 | config | `renesas_sdhi_internal_dmac.c:431` | §40.2.25 |
| `0x828` | DM_CM_DTRAN_CTRL | 0 | DM_START, after the command response | command | `renesas_sdhi_internal_dmac.c:445-461` | §40.2.26 |
| `0x830` | DM_CM_RST | all 1 | DTRANRST0/1 bits 8/9: 0 then 1 | command | `renesas_sdhi_internal_dmac.c:320-321` | §40.2.27 |
| `0x840`/`0x848` | DM_CM_INFO1 / _MASK | 0 / all 1 | DTRANEND0 bit 16 (to card), DTRANEND1 bit 20 (from card); write 0 to clear | status | `renesas_sdhi_internal_dmac.c:307`, `:336-339` | §40.2.28-40.2.29 |
| `0x850`/`0x858` | DM_CM_INFO2 / _MASK | 0 / all 1 | DTRANERR0/1 | status | `renesas_sdhi_internal_dmac.c:543-546` | §40.2.30-40.2.31 |
| `0x880` | DM_DTRAN_ADDR | 0 | buffer address, 8-byte unit, a 32-bit write | config | `renesas_sdhi_internal_dmac.c:432` | §40.2.32 |
| `0x1000`-`0x103F` | SCC | — | only for HS200/SDR104 tuning, and only if no CPG reset is given (`renesas_sdhi_core.c:580-602`) | not modelled | — | §40.6-40.7 |

## 3. Sequences

- **Request with data, DMA** (F, `renesas_sdhi_internal_dmac.c:404-461`; manual Figures 40.22-40.23 p.3326-3327): `CC_EXT_MODE` and `HOST_MODE` for DMA, `DM_CM_DTRAN_MODE`, `DM_DTRAN_ADDR`, then `SD_STOP.SEC`, `SD_SECCNT`, `SD_SIZE`, `SD_ARG`, `SD_CMD`; on the response end a work item writes `DM_START`. The request completes when both `SD_INFO1.INFO2` and `DM_CM_INFO1.DTRANEND` are seen (`:328-358`). So the card data must wait for `DM_START` (I). The manual's flowcharts write `CC_EXT_MODE = 0x1012` only after the response end, so a whole block is then already in SD_BUF (BRE set); the DMAC takes it from there (I, both orders are in the qtest).
- **PIO fallback** (F, `:389-399`, `:441-442`): only when `dma_map_sg()` fails or the buffer is not 128-byte aligned. Data then goes through `SD_BUF0` block by block on BRE/BWE.
- **Interrupt handler** (F, `tmio_mmc_core.c:706-727`): reads `SD_INFO1/2`, writes back `TMIO_MASK_IRQ` (keeps the flags it handles, clears the errors), then acks each source with a 0 write.
- **Write gate** (F, `renesas_sdhi_core.c:836-875`): before writes to `SD_CMD`, `SD_STOP`, `SD_SECCNT`, `SD_SIZE`, `SD_OPTION`, `SDIO_MODE`, `CC_EXT_MODE`, `HOST_MODE` the driver polls `CBSY` = 0; before `SD_CLK_CTRL`, `SCLKDIVEN` = 1; on a timeout it skips the write. Idle must read `CBSY = 0`, `SCLKDIVEN = 1`.
- **No card** (F, §40.2.7 ERR6): the command gets no response: `ERR6` and `INFO0` are set and the sequence ends.

## 4. Model choices

- **Untimed bus (A):** a command sequence ends within the register access that starts it; `SCLKDIVEN` reads 1 whenever `CBSY` is 0; the data timeout counter never fires. A card that sends no data ends the sequence with `ERR3`.
- **SD_BUF0 width (A):** each access moves as many bytes as it is wide, whatever `HOST_MODE` says. The manual does not say what a 64-bit access does while `WMODE` = 1 (the G1 PIO case), and the EVK cannot show it without a write.
- **Card pins (I):** `INFO5` and `INFO10` read 1 with a card in the slot; `INFO7` reads 1 unless the card is read-only (`TMIO_STAT_WRPROTECT` = writable, `tmio_mmc_core.c:1016`); `DAT0` reads 1.
- **Normal mode (A):** `SD_CMD[10:8]` = 000 takes the response length the card gives (48 or 136 bits); CMD0, CMD4 and CMD15 have no response, every other command times out when the card does not answer. Data moves only for CMD17/18/24/25. Linux uses extended mode only; U-Boot (M7) may need more. Logged as unimplemented.
- **Not modelled:** SDIO functions, HPI, the read wait state, the `SD_BUF0` byte swap, CRC errors, the SCC (logged, reads 0, so tuning fails visibly).

## 5. Open (EVK, U-Boot prompt)

EVK-R74-R78 in [`../evidence/requests.md`](../evidence/requests.md) §1.8: `VERSION` on both channels, SDHI0 as U-Boot leaves it, the DMAC and SCC reset values, SDHI1 card detect.
