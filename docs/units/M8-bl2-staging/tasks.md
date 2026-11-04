# M8-bl2-staging — tasks

Branches `unit/M8-bl2-staging` (project from `main` `7e704a8`, fork from `rzv2l-dev` `fe92a06227`).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Evidence: the boot ROM, the image layout, BL2's accesses, the DDR block | `docs/research/bl2.md` | — | done |
| T2 | BL2 and `fiptool` builds; the SPI flash image (boot parameter block, BL2, FIP) | `tests/guests/fw/build-tf-a.sh`, `build-spi-image.sh` | header (size `0xE924`, `0x200`, `0x12000`, `55 AA`), FIP header `0xAA640001` at `0x20000`, `fiptool info`; BL31 unchanged; the image reproducible | done |
| T3 | CPG: PLL4, PLL6 (standby, clock settings, monitors) and the SRC clock and reset registers; both start states | fork `hw/misc/renesas_rzv2l_cpg.c` | qtest `rzv2l-cpg-test` | open |
| T4 | SYSC: master and slave access-control registers, Secure only; both start states | fork `hw/misc/renesas_rzg2l_sysc.c` | qtest `rzv2l-smarc-test` | open |
| T5 | Boot-ROM stand-in: boot modes 3 and 4 without `-bios`/`-kernel`: size block, copy to `0x12000`, core 0 at EL3; errors | fork `hw/arm/rzv2l-smarc.c`, `docs/system/arm/rzv2l-smarc.rst` | acceptance `tests/acceptance/m8/` | open |
| T6 | Acceptance: BL2's banner, the stop at the first DDR access, the stand-in's errors; M7 unchanged; log gate | `tests/acceptance/m8/` | M8 run | open |
| T7 | Device map rows and gap 9 (the access-control registers were not stored), research corrections (`boot-chain-firmware.md`: the BL33 EL file), walkthrough step, milestones | `docs/` | lint | open |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
