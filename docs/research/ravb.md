# Gigabit Ethernet (ravb "gbeth"), MDIO and the KSZ9131 PHY: what the kernels need

The register contract of ETH0 and ETH1, their PHYs and the PHY interrupt path, as the Linux drivers `ravb`, `micrel` and phylib use them. The model and its qtest are written from this page; the unit is [M6-ravb](../units/M6-ravb/spec.md).

**Labels:** **F** = stated by the manual or visible in the cited code; **I** = code-derived inference; **A** = assumption; **O** = EVK observation.

**Citation key:** `m:N` = linux v6.12.59 `drivers/net/ethernet/renesas/ravb_main.c:N`, `h:N` = `ravb.h:N`, `micrel.c:N` = `drivers/net/phy/micrel.c:N` (G0). **G1** (rz_linux-cip `212f6e88b7`) where it differs. Manual = RZ/V2L HW manual Rev 1.50, chapter 30 (ETHER), chapter 8 (IRQC). SoM UM = `r01uh0964ej0200`.

## 1. The block and the board

| Item | Value | Label, cite |
|---|---|---|
| MMIO | ETH0 `0x11C20000`, ETH1 `0x11C30000`, 64 KiB each, 32-bit registers: DMAC `0x000-0x48C`, E-MAC (`CXRnn`) `0x500-0x7DC`, TOE `0x800-0x9FF` | F: Table 30.3-30.6 p.2082-2086 |
| Not R-Car AVB | one TX queue (q = 0) and one RX queue (q = 4); 8-byte descriptors only; no gPTP, no APSR, no extended descriptors | F: Table 30.4 p.2082-2083 |
| Interrupts | `pif_int_n` SPI 84 / 87 (Linux `mux`), `int_fil_n` 85 / 88, `int_arp_ns_n` 86 / 89, level | F: Table 8.2 p.537; dtsi:1095-1098 |
| Clocks, reset | `CLK_ON 0x57C` b0/b1 (axi + chi coupled), `RST 0x87C` b0/b1 (`ETHn_RST_HW_N`), `RSTMON 0x9FC` reset `0x3` | F: Table 7.5, §7.2.4.133, §7.2.4.171 |
| PHY | Microchip KSZ9131RNXC per channel, address 7, RGMII 1.8 V; `INT_N` → IRQ2 (ETH0, pin P1_0) / IRQ3 (ETH1, P1_1); `RESET_N` from the PMIC reset (PRESET#), no GPIO | F: SoM UM Table 4.1 p.19, Figure 4.3-4.4 p.35, Figure 4.7 p.38; `rzg2l-smarc-som.dtsi:94-135, 205-206, 235-236` |
| Consumers | `CONFIG_RAVB=y`, `CONFIG_MICREL_PHY=y`, `CONFIG_MDIO_BITBANG=y`, `CONFIG_RENESAS_RZG2L_IRQC=y` in both kernels; matched by `renesas,rzg2l-gbeth` (`m:2823`) | F: effective `.config` of G0 and G1 |
| EVK | both PHYs probe as "Microchip KSZ9131 Gigabit PHY" at `…ethernet-ffffffff:07`, PHY IRQ through the IRQC; ETH1 cabled: "Link is Up - 1Gbps/Full - flow control off"; ETH0 down (no cable) | O: operator's raw captures (`tio_ttyUSB0_*`), [EVK evidence](../evidence/EVK-2026-10-30-linux.md) interrupt table |

## 2. MAC address

Neither DT has `local-mac-address`. U-Boot's `fdt_fixup_ethernet()` writes `local-mac-address` (and `mac-address` if present) into the node of each `ethernetN` alias from `ethaddr` / `eth1addr` before it starts Linux (U-Boot `4eebfbaa4e` `boot/image-fdt.c:622`, `boot/fdt_support.c:560-632`; F). The SoM DT has `ethernet0 = &eth0`, `ethernet1 = &eth1` (`rzg2l-smarc-som.dtsi:23-26`; F). The EVK's U-Boot environment holds `ethaddr`/`eth1addr`, and Linux reports exactly those addresses (O). So Linux takes the address from the DT (`m:122-141`); `CXR24`/`CXR25` (MAHR/MALR, reset 0) are read only without it, and then the driver picks a random address (F).

## 3. What the driver does (gbeth path)

- **Probe** (`m:2914-3130`): CPG reset deassert; one IRQ, `mux`, `IRQF_SHARED` (`multi_irqs = 0`, `m:2869`); `fil` and `arp_ns` are never requested (F). CONFIG mode: `CCC.OPC = 1`, polls `CSR.OPS == 1 << OPC` for 100 ms (`m:49-84`); MDIO bus registered on the MAC node, PHY at address 7 created from the compatible, so PHYID is never read (`fwnode_mdio.c:141-145`; F); RESET mode again.
- **Open** (`m:1929-1989`): CONFIG; `DBAT`; rings (RX 1024 + LINKFIX, buffers DS = 1726; TX 64 slots × 2 descriptors + LINKFIX, `m:355-401`); `RCR = 0x60000000`, `RTC = 0x7ffc2000`, `TGC = 0x00222200`, `RIC0 = 1`, `RIC2 = 0x80000001`, `TIC = 1` (`m:609-642`); OPERATION; E-MAC: `CXR35 = 0x03e80000`, `CXR31` in-band link, `RFLR = 0x2004`, `ECMR` G0 `0x020b0060` / **G1** `0x021c0060`, MAHR/MALR, `ECSR = 0x15`, TOE `CSR0 = 0` → poll `TPE|RPE = 0` → `CSR1`/`CSR2` → `CSR0 = 0x30`, `ECSIPR` G0 `0x01` / **G1** `0x15` (LINKIM) (`m:488-554`; F).
- **TX** (`m:2099-2254`): every frame is two descriptors, FSTART (1-4 bytes from an aligned bounce buffer) then FEND, written FEND first; `TCCR |= TSRQ0`. Completion walks descriptors and needs **both** written back FEMPTY (`m:195-236`; F). Checksums of IPv4 TCP/UDP (G0) or IPv4/IPv6 TCP/UDP behind ≤ 1 C-tag (**G1**) are left to the hardware (`NETIF_F_HW_CSUM`, `CSR1` G0 `0x31`, **G1** `0x00300030`; `m:2068-2114`; F).
- **RX** (`m:804-951`): stops at the first FEMPTY; FSINGLE/FSTART/FMID/FEND joined; MSC bits CRC/RFE/RTSF/RTLF/CEEF drop the frame; the 4-byte TOE result is trimmed: G0 verified when both halves are 0 and IPv4, **G1** when the last two bytes are 0 (`m:750-786`; F).
- **Interrupt** (`m:1229-1290`): reads ISS; FRS/FTS → masks `RIC0`/`TIC` bit 0 and schedules NAPI; MS → reads `ECSR`, writes it back; on LCHNG reads `PSR` bit 0 and clears or sets `ECMR.RE|TE` (**G1** only, through LINKIM); ES → `EIS`, `RIS2`. NAPI clears `RIS0`/`TIS` with `~bit` writes, then unmasks (F). A level line that stays high with no matching ISS branch ends in "nobody cared" (I).
- **Stop** (`m:1075-1102`): polls `TCCR.TSRQ0`, `CSR.TPO`, `CSR.RPO` to 0, then CONFIG. `ethtool -G` does not rewrite `DBAT` (`m:1685-1745`; F).
- **Link** (`m:1424-1471`): `adjust_link` writes `GECMR` `0x00/0x10/0x20` and `ECMR.DM`; G0 clears `ECMR.TXF` on link up; **G1** resolves pause into `CCC.FCE` and `ECMR.TXF/RXF` (F).

## 4. The hardware rules the model follows

| Rule | Cite |
|---|---|
| `CSR.OPS = 1 << CCC.OPC`; entering OPERATION loads `CDARq = DBAT + 8q`; leaving it clears the status flags; CONFIG returns status registers to reset values; `DBAT` writable in CONFIG/OPERATION | F: §30.4.1.1-30.4.1.5 p.2087-2093, §30.5.1.1 p.2235 |
| Descriptor word 0: DT[31:28], DIE[27:24], content [23:12] (RX: MSC[23:16], EI b13), DS[11:0]; word 1 DPTR. DT: LEMPTY 2, EEMPTY 3, FMID 4, FSTART 5, FEND 6, FSINGLE 7, LINK 8, LINKFIX 9, EOS 10, FEMPTY 12, FEMPTY_ND 15; others reserved | F: Figure 30.7 p.2242, Table 30.7 p.2241 |
| TX: Fxxx → FEMPTY, LINK → LEMPTY, EOS → EEMPTY and TSRQ0 = 0; FEMPTY/LEMPTY/EEMPTY stop the queue, refetched on the next TSRQ0 | F: Table 30.14 p.2255, §30.4.1.10 |
| RX: FEMPTY → FSINGLE or FSTART/FMID/FEND with DS = stored length; a software-owned descriptor = queue full: frame discarded, `RIS2.QFF0` | F: Table 30.12 p.2250, p.2252 |
| Reserved DT: CDAR unchanged, frame lost, `EIS.QEF`, `ESR.ET` = 2; ET 0/1/4/5 for descriptor/data read/write errors | F: p.2241, §30.5.5.3 p.2262-2263, §30.4.1.6 p.2094 |
| `DIS`, `EIS`, `RIS0-3`, `TIS`: write 0 clears, 1 no effect; `CXR21` FCI/LINKI: write 1 clears | F: p.2104-2129, §30.4.2.3 p.2143 |
| ISS: FRM = RIC0&RIS0 (or RDPF with CIE), FTM = TIC&TIS, EM = EIC&EIS or EIS.QFS, MM = pending MAC interrupt; CIE gates only RDPF/TDPF | F: §30.4.1.43 p.2137, Table 30.20 p.2299; MM = `CXR21 & CXR22` (I) |
| TOE: TX inserts enabled checksums (an IPv4 UDP checksum of 0 stays 0); RX puts IPv4-header and L4 results in place of the CRC (0 = OK, `FFFF` = unsupported), error → MSC b6, unsupported → MSC b5; needs `CXR20.RCPT` | F: §30.5.6 p.2265-2267, Figure 30.25, Table 30.13 p.2251 |
| `CXR23` bit-bang MDIO: MDC b0, MM b1, MDO b2, MDI b3; clause 22 frame, MDO sampled on MDC rising; MM reads back as written | F: §30.5.14.3 p.2309-2315; **conflict**: MM "read value should be 0" (p.2145) vs the procedure and Linux's read-modify-write (`m:143-176`): model R/W |
| Frame size limits: TX 1.5 KB, RX 8 KB; `CXR2A.LEN_LMT` ≤ `0x5EE` = 1518 | F: Table 30.1 p.2079, §30.4.2.2 |
| IRQC IRQn: `IITSR` 00 low level (reset), 01 falling, 10 rising, 11 both; `ISCR.ISTATn` follows the pin in level mode (writes invalid), latched in edge modes (0 clears); IRQn → SPI 1 + n | F: §8.6.3-8.6.4 p.552-553, §8.7.2 p.570, Table 8.2 p.535 |

## 5. The PHY contract (phylib + micrel)

- Interrupt mode: phylib does not poll (`phy.c:1523`); `phy_start` checks the link once after `config_aneg`, so `BMCR.ANRESTART` must read 0 at once for the first pass to see link up (`phy_device.c:2576`; F). Afterwards only the PHY interrupt reports link changes (I).
- Register `0x1B`: Linux reads it to clear, writes `0x0500` (link-up/link-down enables b8/b10); status b0/b2 clear on read; the handler returns `IRQ_NONE` unless b0 or b2 is set (`micrel.c:563-579`; F). `0x1F` bit 14 = 0: `INT_N` active low (F). With the DT's level-low IRQ, a line asserted without a latched bit would storm (I).
- BMSR link is latched low (IEEE 802.3 22.2.4.2.13); `genphy_update_link` reads it twice after a down (F). Also read: ANAR, ANLPAR, CTRL1000, STAT1000 (bit 15 must be 0), ESTATUS, `0x14` (link detected, MDI), `0x1C` (auto MDI-X), MMD 2.0/2.4-2.8/2.76/2.77 (skews and DLLs, written from the DT), MMD 3.20, 7.60, 7.61 (EEE) (F).
- **Not measured:** the PHYID2 revision nibble and the vendor registers' reset values; Linux ignores them (A). An EVK U-Boot `mii read 7 <reg>` session would settle them; `0x1B` reads clear status.

## 6. Conflicts and open points

1. `CXR23.MM` read value (§4 above): modelled R/W, as the driver requires.
2. CIE: gates only RDPF/TDPF; Linux never writes it, so FRF/FTF must reach `pif_int_n` with CIE = 0 (F, I).
3. MSC b5/b6 are TOE bits here, not R-Car CRL/CEEF; Linux drops b6 frames (F).
4. `CSR2.RTCP4` row says "read as 0" while being an enable (p.2190); Linux writes 1 (A: misplaced line).
5. RX trailer with `RCPT = 1` and the TOE RX path off: modelled as the CRC; not measured (A).
6. Linux rewrites `ECMR` with TPE = RPE = 1 although §30.4.2.1 forbids it; the model accepts it (F/I).
