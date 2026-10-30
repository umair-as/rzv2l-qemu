# M5-sdhi — tasks

Fork branch `unit/M5-sdhi` from `rzv2l-dev` `76685b0c82`; project branch of the same name from `main`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Register evidence: every SDHI, DMAC register the driver touches, reset values, bits, `file:line` (register-evidence skill) | `docs/research/sdhi.md` | review of the page | todo |
| T2 | SDHI register file, command engine on the SD bus, response timeout without a card, PIO through `SD_BUF0` | fork `hw/sd/renesas_sdhi.c` | qtest `/rzv2l-sdhi/*` | todo |
| T3 | Internal DMAC: `DM_CM_*`, `DM_DTRAN_ADDR`, transfers to and from guest RAM, `DTRANEND` | fork `hw/sd/renesas_sdhi.c` | qtest | todo |
| T4 | SoC wiring: SDHI0/1 at `0x11C00000`/`0x11C10000`, SPI 104/106, SCC as a logged stub, `-drive if=sd` on SDHI0 | fork `hw/arm/r9a07g054.c`, `rzv2l-smarc.c` | G0/G1 boot: `mmc0` card, partitions | todo |
| T5 | SD image build script and persistence acceptance (hashes in guest, on host, after restart) | `tests/guests/`, `tests/acceptance/m5/` | M5 ACCEPTANCE | todo |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
