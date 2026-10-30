# M5-sdhi — tasks

Fork branch `unit/M5-sdhi` from `rzv2l-dev` `76685b0c82`; project branch of the same name from `main`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Register evidence: every SDHI and DMAC register the driver touches, reset values, bits, `file:line` | `docs/research/sdhi.md` | review of the page | done |
| T2 | SDHI register file, command engine on the SD bus, response timeout without a card, PIO through `SD_BUF0` | fork `hw/sd/renesas_sdhi.c` | qtest `/rzv2l-sdhi/*` | done |
| T3 | Built-in DMAC: `DM_CM_*`, `DM_DTRAN_ADDR`, transfers to and from guest RAM after `DM_START`, `DTRANEND0/1` | fork `hw/sd/renesas_sdhi.c` | qtest `/rzv2l-sdhi/dma` | done |
| T4 | CPG `RST_SDHI` reset lines; SoC wiring at `0x11C00000`/`0x11C10000`, SPI 104-107; `-drive if=sd` index 0/1 on the board; QEMU board doc | fork `hw/misc/renesas_rzv2l_cpg.c`, `hw/arm/r9a07g054.c`, `rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` | qtest `/rzv2l-sdhi/cpg-reset`; G0/G1 boot | done |
| T5 | SD image build script; storage acceptance (write, sync, unmount; host `e2fsck`/`debugfs`; second boot reads back); M1/M3/M4 expectations for the new device | `tests/guests/sd/build-image.sh`, `tests/acceptance/m5/`, `tests/acceptance/m1/expected/`, `m3`/`m4` log allow lists | M5 ACCEPTANCE | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `VERSION` reads `0xCD10` (the R-Car MMC value) | `rzv2l-sdhi-test.c:195 test_reset_values`: `0x0000cd10 == 0x0000cc10` |
| 2 | `SD_INFO2_MASK` resets to `0x837F` (bit 11 clear) | `rzv2l-sdhi-test.c:187 test_reset_values`: `0x0000837f == 0x00008b7f` |
| 3 | flags clear on a 1 write instead of a 0 | `rzv2l-sdhi-test.c:246 test_no_card`: `0x00000040 == 0x00000000` |
| 4 | the DMAC sets the other channel's `DTRANEND` | `rzv2l-sdhi-test.c:333 test_dma`: `0x00010000 == 0x00100000` |
| 5 | the CMD18 response is not kept in `SD_RSP54` | `rzv2l-sdhi-test.c:349 test_dma`: `0x00000006 == 0x00000004` |
| 6 | `CC_EXT_MODE.DMASDRW` ignored (data always through `SD_BUF0`) | `rzv2l-sdhi-test.c:327 test_dma`: `0x00004100 == 0x00004000` |
| 7 | the CPG never drives the SDHI reset line | `rzv2l-sdhi-test.c:216 test_cpg_reset`: `0x00000040 == 0x00000200` |
| 8 | OXASIOIRQ follows every interrupt, not only SDIO | `rzv2l-sdhi-test.c:242 test_no_card`: `'qtest_get_irq(qts, 1)' should be FALSE` |
| 9 | no automatic CMD12 after a multiple block transfer | `rzv2l-sdhi-test.c:350 test_dma`: `0x00000004 == 0x00000005` |
| 10 | `SD_BUF0` writes advance 2 bytes whatever their width | `rzv2l-sdhi-test.c:291 test_pio`: `0x00000000 == 0x00000004` |

Each mutation was built with a confirmed relink and run alone; the source was restored from git and rebuilt, and the five tests passed again, as did the other six RZ/V2L qtest files.
