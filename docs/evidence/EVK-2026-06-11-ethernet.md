# EVK Ethernet observations — console capture of 2026-06-11

**Board:** RZ/V2L SMARC EVK (2 GB variant), Ethernet cable in one RJ45 port.
**Image:** a G2 product image (the `edge-ai-yocto` build): U-Boot `2024.07 (Sep 22 2025 - 10:51:32 +0000), Build: edge-local`; kernel `6.12.90-cip24-yocto-standard`, built on the vendor `rz_linux-cip` base. The Ethernet nodes, the PHY nodes and the aliases of its device tree are those of the stock SMARC module tree (`rzg2l-smarc-som.dtsi`), so the driver behaviour transfers to G0 and G1 (I).
**Boot stage:** U-Boot environment print and Linux dmesg, two boots in one capture.
**Method:** passive serial capture at 115200 8N1 by the operator; no register access.
**Provenance:** the image was not built by this project. Capture `tio_ttyUSB0_2026-06-11T10:27:15.log`, SHA-256 `6ffb159b7051377d9ca9755629c404359975da080be7764b824f4442bfb5db8b` (148386 bytes), kept privately by the operator. Excerpts are verbatim.

| Observation (verbatim excerpt) | Answers |
|---|---|
| `Microchip KSZ9131 Gigabit PHY 11c20000.ethernet-ffffffff:07: attached PHY driver (mii_bus:phy_addr=11c20000.ethernet-ffffffff:07, irq=46)`, the same for `11c30000.ethernet-ffffffff:07` with `irq=48` | Each MAC has its own MDIO bus with the KSZ9131 driver at address 7, and its PHY interrupt is a separate Linux IRQ (through the IRQC: I, from the DT) (research/ravb.md §1) |
| `ravb 11c20000.ethernet eth0: Link is Up - 1Gbps/Full - flow control off` | The cabled port links at 1 Gb/s full duplex |
| Boot 1: `ravb 11c20000.ethernet eth0: Base address at 0x11c20000, f2:4c:8e:42:4e:4b, IRQ 45.` / `ravb 11c30000.ethernet: no valid MAC address supplied, using a random one` | Without an address for a channel, the driver falls back to a random MAC (`ravb_main.c:122-141`) |
| Boot 2: `ravb 11c20000.ethernet eth0: Base address at 0x11c20000, fe:be:9d:9b:da:11, IRQ 45.` / `ravb 11c30000.ethernet eth1: Base address at 0x11c30000, fe:be:9d:9b:da:12, IRQ 47.`, and U-Boot's environment, printed later in the same session: `ethaddr=fe:be:9d:9b:da:11`, `eth1addr=fe:be:9d:9b:da:12` | Linux uses exactly U-Boot's `ethaddr`/`eth1addr`, as U-Boot's `fdt_fixup_ethernet()` writes them into the `ethernetN` alias nodes (research/ravb.md §2). Which path (DT property or `CXR24/CXR25`) carried them was not read on the board (I: the DT, since U-Boot writes it on every boot) |

Not observed here: the PHY ID registers, the vendor PHY register values, or `CXR24/CXR25` after U-Boot. A U-Boot `mii read 7 <reg>` and `md.l 0x11c205c0 1` session would read them (`docs/evidence/requests.md` conventions; reading PHY register `0x1B` clears its status).
