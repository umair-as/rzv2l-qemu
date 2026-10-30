# M6-ravb — spec

**Milestone:** M6 (networking; one unit). **Requirements:** REQ-ETH-001, REQ-ETH-002 (proposed with this page).

## Scope

**The Gigabit Ethernet interface** (manual §30, "GbEthernet"; Linux `ravb`, gbeth variant), channels ETH0 and ETH1 at `0x11C20000` and `0x11C30000`, **the board's KSZ9131 PHYs**, and **IRQ0-7 of the interrupt control unit**, which carry the PHY interrupts. Before this unit both windows were logged stubs (UNIMP: reads 0): the driver timed out entering CONFIG mode and the probe failed (`-110`). Register evidence: [`research/ravb.md`](../../research/ravb.md).

- **DMAC** (§30.4.1, §30.5.1-30.5.5): `CCC`/`CSR` operating modes; `DBAT` with the TX queue (q = 0) and RX queue (q = 4) entries; 8-byte descriptors with the manual's types and write-back (Tables 30.7, 30.12, 30.14), split RX frames, queue full (`RIS2.QFF0`), invalid types and bus errors (`EIS.QEF`, `ESR.ET`); status flags cleared by a 0 write; set/clear aliases of the enable registers; `ISS` and `pif_int_n` from the enabled flags.
- **E-MAC** (§30.4.2): `CXR20` (ECMR) enables and address filter, `CXR21`/`CXR22` with `LINKI` on a link change, `CXR2B` link status, `CXR23` bit-banged MDIO (clause 22 frames to the PHY at address 7), `CXR24`/`CXR25` address, frame length limit `CXR2A`, the counters.
- **TOE** (§30.5.6): TX checksums (IPv4 header, TCP/UDP over IPv4 and IPv6) as `CSR1` enables them; the RX result in place of the CRC.
- **PHY** (board, SoM UM §4.3): Microchip KSZ9131, address 7: the clause 22 registers, MMD skew/DLL/EEE registers, latched-low BMSR, the `0x1B` interrupt and `INT_N` (level-low), always-ready gigabit link partner; a cable while the NIC has a backend and `set_link` is on.
- **IRQC** (§8.6.3-8.6.4): IRQ0-7 pin inputs, `IITSR` detection (low level, falling, rising, both), `ISCR`; IRQn → SPI 1 + n. ETH0's PHY drives IRQ2, ETH1's IRQ3.
- **CPG:** `CPG_RST_ETH` drives each channel's reset (`eth-rst` lines). While held, registers read their reset values.
- **Start states:** firmware mode: manual reset values (MAC address registers 0). Direct mode: the same registers; the vendor U-Boot's `fdt_fixup_ethernet()` is applied to the DT instead (each `ethernetN` alias node gets `local-mac-address` = the NIC's MAC), because on the EVK the address reaches Linux that way (O, [EVK Ethernet evidence](../../evidence/EVK-2026-06-11-ethernet.md); I for the path, [ravb.md §2](../../research/ravb.md#2-mac-address)). Gap 8 lists it.
- **Not modelled** (honest): timing (transfers complete at once), flow control and PAUSE, the hardware MDIO controller (`MDIOMOD.SEL_MDIO_N` must stay 1), EEE/LPI, the TOE filters, wake-up and ARP/NS (`int_fil_n`, `int_arp_ns_n` never asserted), DLR reloads, error frames (`RCR.EFFS`), TX frames over 1.5 KB (dropped, logged), the `CXR2C` link polarity, the frame counters (they read 0, except multicast frames received in `CXR57`); IPv6 extension headers and IPv4 options read as unsupported in the TOE. Those registers fail with a decode error. IRQC NMI and TINT0-31 stay unrouted (gap 15).

## What the guest needs

Both kernels build `CONFIG_RAVB=y`, `CONFIG_MICREL_PHY=y`, `CONFIG_MDIO_BITBANG=y`, `CONFIG_RENESAS_RZG2L_IRQC=y` (effective `.config`). The driver contract is [ravb.md §3](../../research/ravb.md#3-what-the-driver-does-gbeth-path), the hardware rules §4, the PHY contract §5. The points that decide the model:

- `CSR.OPS == 1 << CCC.OPC` within 100 ms; `TCCR.TSRQ0`, `CSR.TPO/RPO`, `CSR0.TPE/RPE` read 0 when idle (`ravb_main.c:49-84`, `:1075-1102`, `:488-515`).
- Every TX frame is FSTART + FEND; both are written back FEMPTY (`ravb_main.c:195-236`, `:2132-2221`).
- TX checksums are left to the TOE (`NETIF_F_HW_CSUM`); RX checks the 4-byte TOE result (`ravb_main.c:750-786`; G1 differs, §3).
- One interrupt line, shared and level: NAPI masks `RIC0`/`TIC` and the line must drop; flags clear on a 0 write (`ravb_main.c:1184-1215`, `:1368-1414`).
- The PHY is interrupt-driven: `ANRESTART` self-clears for the single link check after `phy_start`; link changes reach Linux only through `INT_N` → IRQ2 → SPI 3 (`phy.c:1523`, `phy_device.c:2576`, `micrel.c:563-579`).
- G1 enables `LINKI` and clears RX/TX when `CXR2B.LINK` reads 0 (`ravb_main.c:1117-1131` in G1): `CXR2B` follows the PHY link.

## Exit criterion

1. qtests assert manual and IEEE 802.3 values: reset values, the CPG reset, MDIO frames, PHY link interrupts through the IRQC (level and edge), `LINKI`, TX and RX rings (write-back, wrap, split frames, queue full), interrupt lowering, the TOE result, invalid descriptors and DMA outside RAM, mode changes; each seen red on a mutation.
2. G0 and G1 (unchanged kernels, stock DTBs, the BusyBox initramfs) with ETH0 on QEMU user networking: both MACs and PHYs probe; eth0 1 Gb/s full duplex; DHCP lease (kernel `ip=on` and `udhcpc`); ping payloads 0-1472 bytes; 3 MiB each way with equal SHA-256; more frames than the RX ring (1024) and TX ring (64) hold; `set_link` off/on, interface down/up and `system_reset` each recover with a new checked transfer. ETH1 without a backend has no carrier.
3. M1-M5 acceptance and the serial-port regression suite still pass; the `-d` log lists only recorded stub windows.

## Evidence

Manual §30 (p.2077-2315), §8.6 (p.552-553), Table 8.2; SoM UM Table 4.1 p.19, Figures 4.3-4.4 p.35, 4.7 p.38; pinned U-Boot `boot/fdt_support.c:560-632`; [EVK Ethernet evidence](../../evidence/EVK-2026-06-11-ethernet.md) (the PHY probe lines, link 1 Gb/s, the MAC from U-Boot's environment; O); [`research/ravb.md`](../../research/ravb.md). Leads from a research packet in the working area.

## For the operator

- **Network backend:** user networking (slirp): no host interface, no root; slirp would forward a connection to any other address through the host, which the test never makes, so it needs no physical LAN. The host side of each transfer is a server on 127.0.0.1, which the guest reaches as `10.0.2.2`. QEMU must be configured with slirp: the walkthrough adds `libslirp-dev` to the host packages (a `build/qemu` configured before has no slirp).
- **A cable on ETH0 by default (operator's decision):** with Ethernet working, the stock boot arguments' `ip=on` waits up to 120 s for a carrier when no channel has one, as on an uncabled board; the M3 and M4 boots then missed their boot timeout. The model keeps "no backend = no cable"; `scripts/run.sh` and the M3-M5 acceptance boots with the stock arguments add `-nic user,id=net0`, like the EVK's cabled port (`--no-net` turns it off).
- **MAC address:** taken from the DT (U-Boot's edit, applied by the loader), not preloaded into `CXR24/CXR25`: Linux would read those only without a DT address. The QEMU NIC's MAC (`-nic …,mac=`) is the address Linux uses.
- **PHY wiring:** the PHY interrupt goes straight to the IRQC input; the PFC pin function of P1_0/P1_1 (IRQ2/IRQ3) is not checked. The PHY revision nibble (`PHYID2` bits 3:0) and the vendor registers' reset values are not measured (A); Linux does not read them. An EVK U-Boot `mii read 7 <reg>` session would settle them.
- **Conflicts recorded:** `CXR23.MM` modelled read/write (the manual says read 0; the driver needs read-back); `CSR2.RTCP4` "read as 0" line taken as misplaced; `RCPT = 1` without the TOE RX path stores the CRC (A).

## Unit end

- **Met:** exit criteria 1-3. qtest `rzv2l-gbeth-test` (10 tests, 25 mutations red, `tasks.md`); M6 acceptance `tests/acceptance/m6/` on G0 and G1: every check passes; M1 acceptance with the new devices.
- **Seen in the run (O, model):** the kernel's `ip=on` from the stock bootargs gets its lease during boot; the vendor kernel enables `LINKI` and follows `CXR2B` on each `set_link`; about 4500 frames in and 2400 out per transfer pair, no RX/TX errors.
- **Next (layer verified: Linux sockets over the guest network stack):** M7, the real firmware. Networking is not on its boot path; U-Boot's own `ravb` driver (a firmware-mode user of this model) is untested until then.
