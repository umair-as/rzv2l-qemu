# M5-sdhi — tasks

Fork branch `unit/M5-sdhi` from `rzv2l-dev` `76685b0c82`; project branch of the same name from `main`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Register evidence: every SDHI and DMAC register the driver touches, reset values, bits, `file:line` | `docs/research/sdhi.md` | review of the page | done |
| T2 | SDHI register file, command engine on the SD bus, response timeout without a card, PIO through `SD_BUF0` | fork `hw/sd/renesas_sdhi.c` | qtest `/rzv2l-sdhi/*` | done |
| T3 | Built-in DMAC: `DM_CM_*`, `DM_DTRAN_ADDR`, transfers to and from guest RAM after `DM_START`, `DTRANEND0/1` | fork `hw/sd/renesas_sdhi.c` | qtest `/rzv2l-sdhi/dma` | done |
| T4 | CPG `RST_SDHI` reset lines; SoC wiring at `0x11C00000`/`0x11C10000`, SPI 104-107; `-drive if=sd` index 0/1 on the board; QEMU board doc | fork `hw/misc/renesas_rzv2l_cpg.c`, `hw/arm/r9a07g054.c`, `rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` | qtest `/rzv2l-sdhi/cpg-reset`; G0/G1 boot | done |
| T5 | SD image build script; storage acceptance (write, sync, unmount; host `e2fsck`/`debugfs`; second boot reads back); M1/M3/M4 expectations for the new device | `tests/guests/sd/build-image.sh`, `tests/acceptance/m5/`, `tests/acceptance/m1/expected/`, `m3`/`m4` log allow lists | M5 ACCEPTANCE | done |
| T6 | Review response: `DM_START` takes over a transfer started without DMA (the manual's Figure 40.22-40.23 order); normal-mode commands time out without an answer; qtest checks for R2 placement, the access end on a timed-out data command, `SOFT_RST`, `INFO7` | fork `hw/sd/renesas_sdhi.c`, `rzv2l-sdhi-test.c` | proofs 11-17 | done |
| T7 | `mmc0`/`mmc1` aliases added by the loader when the DTB has none (SDHI0, SDHI1); `loader-fixups.sh`, the M1 DTB check and the storage test expect them | fork `hw/arm/rzv2l-smarc.c`; `tests/acceptance/m4/loader-fixups.sh`, `m1/check.py`, `m5/storage.py` | proof 18; storage acceptance mounts `mmcblk0p1` | done |
| T8 | EVK reads at the U-Boot prompt (EVK-R74-R78); the card detect and write protect pins as the board routes them (`cd-connected`, `wp-connected`: off for SDHI0, CD on for SDHI1) | `docs/evidence/`; fork `hw/sd/renesas_sdhi.c`, `hw/arm/r9a07g054.c`, `rzv2l-sdhi-test.c` | proofs 16, 18, 19 | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `VERSION` reads `0xCD10` (the R-Car MMC value) | `rzv2l-sdhi-test.c:207 test_reset_values`: `0x0000cd10 == 0x0000cc10` |
| 2 | `SD_INFO2_MASK` resets to `0x837F` (bit 11 clear) | `rzv2l-sdhi-test.c:199 test_reset_values`: `0x0000837f == 0x00008b7f` |
| 3 | flags clear on a 1 write instead of a 0 | `rzv2l-sdhi-test.c:258 test_no_card`: `0x00000040 == 0x00000000` |
| 4 | the DMAC sets the other channel's `DTRANEND` | `rzv2l-sdhi-test.c:401 test_dma`: `0x00010000 == 0x00100000` |
| 5 | the CMD18 response is not kept in `SD_RSP54` | `rzv2l-sdhi-test.c:417 test_dma`: `0x00000006 == 0x00000004` |
| 6 | `CC_EXT_MODE.DMASDRW` ignored (data always through `SD_BUF0`) | `rzv2l-sdhi-test.c:395 test_dma`: `0x00004100 == 0x00004000` |
| 7 | the CPG never drives the SDHI reset line | `rzv2l-sdhi-test.c:228 test_cpg_reset`: `0x00000040 == 0x00000200` |
| 8 | OXASIOIRQ follows every interrupt, not only SDIO | `rzv2l-sdhi-test.c:254 test_no_card`: `'qtest_get_irq(qts, 1)' should be FALSE` |
| 9 | no automatic CMD12 after a multiple block transfer | `rzv2l-sdhi-test.c:418 test_dma`: `0x00000004 == 0x00000005` |
| 10 | `SD_BUF0` writes advance 2 bytes whatever their width | `rzv2l-sdhi-test.c:359 test_pio`: `0x00000000 == 0x00000004` |
| 11 | `DM_START` only after a command issued with DMA enabled (the manual's order refused) | `rzv2l-sdhi-test.c:433 test_dma`: `0x00000000 == 0x00100000` |
| 12 | an R2 response stored one byte off (R[127:64] in `SD_RSP54` instead of R[127:72]) | `rzv2l-sdhi-test.c:156 card_init`: `0xaa585951454d5521 == 0xaa585951454d55` |
| 13 | a data command halted by the response timeout sets no access end | `rzv2l-sdhi-test.c:267 test_no_card`: `0x00000001 == 0x00000005` |
| 14 | normal mode takes no answer as a command without response | `rzv2l-sdhi-test.c:273 test_no_card`: `0x00000000 == 0x00000040` |
| 15 | `SOFT_RST.SDRST = 0` resets nothing | `rzv2l-sdhi-test.c:306 test_soft_reset`: `0x0000c0ee == 0x000040ee` |
| 16 | the write protect pin reported although the board does not route it | `rzv2l-sdhi-test.c:287 test_card_pins_sdhi1`: `0x000004a0 == 0x00000420` |
| 17 | the DMAC refuses a write started without DMA (Figure 40.23 order) | `rzv2l-sdhi-test.c:467 test_dma`: `0x00000000 == 0x00010000` |
| 18 | SDHI0's card detect pin routed (`cd-connected` on for both channels, `hw/arm/r9a07g054.c`) | `rzv2l-sdhi-test.c:331 test_pio`: `0x00000420 == 0x00000400` |
| 19 | SDHI1's routed card detect ignored | `rzv2l-sdhi-test.c:287 test_card_pins_sdhi1`: `0x00000400 == 0x00000420` |

Each mutation was built with a confirmed relink and run alone; the source was restored from git and rebuilt, and the tests passed again (six after the review), as did the other six RZ/V2L qtest files. All proofs were run again against the final test file (seven tests); the lines above are from that run.
