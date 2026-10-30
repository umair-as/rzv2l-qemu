# M6-ravb — tasks

Fork branch `unit/M6-ravb` from `rzv2l-dev` `10df946cc8`; project branch of the same name, rebased on `main` `f15f61e` (M5 merged).

| ID | Task | Fork commit | Test | Status |
|---|---|---|---|---|
| T1 | Register evidence: MAC, MDIO, PHY, IRQC; driver paths of both kernels; board wiring; U-Boot's MAC address edit | — (`docs/research/ravb.md`) | review of the page | done |
| T2 | CPG `CPG_RST_ETH` reset lines (`eth-rst`) | `d4206bd103` | `/rzv2l-gbeth/cpg-reset` | done |
| T3 | IRQC IRQ0-7 inputs: `IITSR` detection, `ISCR`, outputs to SPI 1-8 | `195fc6aef0` | `/rzv2l-gbeth/link-irq` | done |
| T4 | KSZ9131 PHY: clause 22 and MMD registers, latched BMSR, `0x1B` interrupt, `INT_N`, cable | `152e4774d6` | `/rzv2l-gbeth/mdio`, `link-irq` | done |
| T5 | GbEthernet: DMAC rings, E-MAC with MDIO decoder and `LINKI`, TOE checksums, honest faults | `b7ab54f7ec` | `/rzv2l-gbeth/*` | done |
| T6 | SoC and board: ETH0/1 at `0x11C20000`/`0x11C30000`, SPI 84-89, PHYs at address 7 on IRQ2/IRQ3, NIC order, U-Boot's `local-mac-address` edit; QEMU board doc | `29e1718206` | M1 acceptance (mtree, qtree, DTB); G0/G1 boot | done |
| T7 | qtest `rzv2l-gbeth-test` (10 tests) | `d0269cf05e` | proofs 1-25 | done |
| T8 | M6 acceptance (`tests/acceptance/m6/`): DHCP, hashes both ways, frame sizes, ring turns, `set_link`, ifdown/up, reset, both kernels; M1 and M4 loader-fixup expectations for the new devices and the MAC address edit | — | M6 ACCEPTANCE; proof 26 | done |
| T9 | A cable on ETH0 by default: `scripts/run.sh` (`--no-net` to leave it out) and the M3-M5 boots with the stock `ip=on` add `-nic user,id=net0`; `libslirp-dev` joins the build packages | — | M3-M5 acceptance within their boot timeouts | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `RTC_RESET` `0x7ffc2000` (the driver's value) | `rzv2l-gbeth-test.c:370 test_reset_values`: `0x7ffc2000 == 0x7ffc7ffc` |
| 2 | the reset input ignored (`in_reset = false`) | `rzv2l-gbeth-test.c:388 test_cpg_reset`: `0x12345678 == 0x00000000` |
| 3 | the PHY drives the turnaround bit high | `rzv2l-gbeth-test.c:407 test_mdio`: `0x0000ffff == 0x00000022` |
| 4 | `BMCR.ANRESTART` not self-clearing | `rzv2l-gbeth-test.c:417 test_mdio`: `0x00000200 == 0x00000000` |
| 5 | BMSR link status not latched low | `rzv2l-gbeth-test.c:460 test_link_irq`: `0x00000004 == 0x00000000` |
| 6 | IRQC level detection stored instead of following the pin | `rzv2l-gbeth-test.c:454 test_link_irq`: `'qtest_get_irq(qts, PHY_IRQ_ETH0)' should be TRUE` |
| 7 | PHY register `0x1B` not cleared on read | `rzv2l-gbeth-test.c:466 test_link_irq`: `'qtest_get_irq(qts, PHY_IRQ_ETH0)' should be FALSE` |
| 8 | `CXR21` flags clear on a 0 write instead of a 1 | `rzv2l-gbeth-test.c:506 test_mac_link`: `'qtest_get_irq(qts, 0)' should be FALSE` |
| 9 | IRQC falling-edge mode detects rising edges | `rzv2l-gbeth-test.c:475 test_link_irq`: `0x00000000 == 0x00000004` |
| 10 | FSTART descriptors not written back FEMPTY | `rzv2l-gbeth-test.c:547 test_tx`: `0x50000004 == 0xc0000004` |
| 11 | `ISS.FTM` ignores `TIC` | `rzv2l-gbeth-test.c:557 test_tx`: `'qtest_get_irq(qts, 0)' should be FALSE` |
| 12 | `TIS` flags clear on a 1 write | `rzv2l-gbeth-test.c:563 test_tx`: `0x00000000 == 0x00000001` |
| 13 | LINKFIX written back LEMPTY | `rzv2l-gbeth-test.c:576 test_tx`: `0x00000002 == 0x00000009` |
| 14 | RX DS reports the stored total, not the descriptor's part | `rzv2l-gbeth-test.c:608 test_rx`: `0x40000080 == 0x40000040` |
| 15 | queue full sets no `RIS2.QFF0` | `rzv2l-gbeth-test.c:341 wait_rx` (from `test_rx`): `0x00000000 == 0x00000001` |
| 16 | queue full skips the owned descriptor (`CDAR` + 8) | `rzv2l-gbeth-test.c:641 test_rx`: `0x48002010 == 0x48002008` |
| 17 | TOE L4 checksum without the pseudo-header | `rzv2l-gbeth-test.c:690 test_rx_checksum`: `0x70402040 == 0x70002040` |
| 18 | TOE reports unsupported frames as 0 (correct) | `rzv2l-gbeth-test.c:710 test_rx_checksum`: `0x00000000 == 0x00000020` |
| 19 | a reserved descriptor type stops the queue without `EIS.QEF` | `rzv2l-gbeth-test.c:734 test_tx_errors`: `0x00000000 == 0x00000004` |
| 20 | a failed data read ignored | `rzv2l-gbeth-test.c:745 test_tx_errors`: `0x00000200 == 0x00000400` |
| 21 | leaving OPERATION keeps the status flags | `rzv2l-gbeth-test.c:780 test_opmode`: `0x00000001 == 0x00000000` |
| 22 | entering OPERATION does not reload `CDAR` from `DBAT` | `rzv2l-gbeth-test.c:786 test_opmode`: `0x48002008 == 0x48000020` |
| 23 | the board swaps the PHY interrupts (ETH0 on IRQ3) | `rzv2l-gbeth-test.c:454 test_link_irq`: `'qtest_get_irq(qts, PHY_IRQ_ETH0)' should be TRUE` |
| 24 | the board puts the PHY at address 1 | `rzv2l-gbeth-test.c:407 test_mdio`: `0x0000ffff == 0x00000022` |
| 25 | the reset input's polarity inverted | `rzv2l-gbeth-test.c:388 test_cpg_reset`: `0x12345678 == 0x00000000` |
| 26 | the board writes each channel's MAC into the other channel's node (`eth[1 - i]` in `rzv2l_smarc_set_mac_addresses`) | `tests/acceptance/m4/loader-fixups.sh`: `FAIL g0 eth0 local-mac-address: 52 54 0 12 34 57, expected 52 54 0 12 34 56`; M1 `check.py dtb`: `FAIL dtb: /soc/ethernet@11c20000 differs` |

Each mutation was built with a confirmed relink and run alone; the source was restored from git and rebuilt, and the ten tests passed again. The lines above are from a run against the final test file. A first `IITSR` edge-mode check passed with mutation 9 (it read `ISCR` only after the pin rose again); the test now reads it after the falling edge and after a rising edge.

## Boot evidence (fork `d0269cf05e`)

`tests/acceptance/m6/net.py OUT --tier g0` (and `g1`), from `tests/acceptance/m6/run.sh`:

```
[    5.610241] ravb 11c20000.ethernet eth0: Link is Up - 1Gbps/Full - flow control off
[    5.761853] IP-Config: Got DHCP answer from 10.0.2.2, my address is 10.0.2.15
PASS transfer: 3145729 bytes host -> guest, SHA-256 equal
PASS transfer: 3145731 bytes guest -> host, SHA-256 equal (host got 3145731)
PASS transfer: 4490 frames received, 2422 sent: beyond one turn of the RX ring (1024) and the TX ring (64)
PASS link: set_link off -> the guest reports link down
PASS reset: 3145731 bytes guest -> host, SHA-256 equal (host got 3145731)
```
