# M6: networking

> **Context.** Milestone M6 (spec [§17](../spec/project.md#17-milestones)): the Gigabit Ethernet of the RZ/V2L and the board's PHY, used by the unchanged Linux drivers, to a DHCP lease and checked data in both directions. Unit M6-ravb: [spec](../units/M6-ravb/spec.md), [tasks](../units/M6-ravb/tasks.md), register evidence [`../research/ravb.md`](../research/ravb.md). The manual chapter is §30 (Gigabit Ethernet Interface), and §8 for the interrupt control unit. Linux paths are under linux v6.12.59 `drivers/net/`.

This page follows one Ethernet frame out of the guest and one back in, and shows the three parts that must work together: the MAC with its DMA engine, the PHY behind the MDIO pins, and the interrupt that tells Linux the cable is there. It is written for two readers. If you know embedded Linux, it shows what the `ravb` driver and phylib expect from the hardware. If you are new to QEMU, it shows how a network card is modelled and joined to a QEMU network backend.

## 1. Three parts, two buses

```
  Linux:  ravb (MAC driver)        phylib + micrel (PHY driver)       IRQC driver
            |  registers, DMA          |  MDIO frames                    |
  SoC:    GbEthernet --- MDIO pins (CXR23) ---> KSZ9131 PHY  --INT_N--> IRQC IRQ2 --> GIC SPI 3
            |  descriptors in DDR                 |  the cable
  QEMU:   NIC  <------------------------------------------>  network backend (-nic user)
```

- **The MAC** (GbEthernet, `0x11C20000` for ETH0) moves frames between memory and the wire. Its DMA engine reads and writes **descriptors** in DDR. It raises one interrupt line, `pif_int_n` (SPI 84), when a frame has gone out or come in.
- **The PHY** (Microchip KSZ9131 on the SMARC module, MDIO address 7) owns the cable: it negotiates the speed with the other end and reports the link. Linux talks to it through two pins of the MAC, MDC and MDIO, with a 16-bit register protocol (IEEE 802.3 clause 22).
- **The PHY interrupt** does not go to the MAC. The PHY's `INT_N` pin is wired to the SoC pin IRQ2, so it reaches the GIC through the interrupt control unit (IRQC).

In the real board, the MAC and the PHY are joined by RGMII signal lines. In QEMU there are no signals: the MAC hands whole frames to a QEMU **network backend**, and the backend's link state is the cable.

## 2. Descriptors: who owns the buffer

The MAC and the CPU share rings of 8-byte descriptors. Each holds a type (DT, 4 bits), a size (DS, 12 bits) and a buffer address. The type says who owns it (manual Table 30.7):

| Type | Value | Owner on transmit | Owner on receive |
|---|---|---|---|
| FEMPTY | 12 | the CPU: nothing to send | the MAC: an empty buffer to fill |
| FSTART, FMID, FEND, FSINGLE | 5, 4, 6, 7 | the MAC: part of a frame to send | the CPU: part of a received frame |
| LINKFIX | 9 | follow the address; the ring wraps | the same |
| EEMPTY | 3 | the CPU: the end of the work | the CPU |

**Transmit.** The Linux driver puts every frame in two descriptors: FSTART with the first 1-4 bytes (copied to an aligned buffer, because this MAC needs 4-byte-aligned data), then FEND with the rest. It writes FEND first and FSTART last, so the MAC never sees half a frame. Then it sets `TCCR.TSRQ0`. The MAC sends the frame and writes FEMPTY into **both** descriptors. The driver frees its buffers only when it finds FEMPTY, so a MAC that marks only one of the two stops the queue after 63 frames.

**Receive.** At open, the driver fills a ring of 1024 FEMPTY descriptors, each with a 1726-byte buffer, and a LINKFIX at the end. For each frame, the MAC writes the data, the length into DS, and FSINGLE into DT. A frame longer than one buffer goes into several descriptors: FSTART, FMID…, FEND. When the MAC meets a descriptor that the CPU still owns, the ring is full: the frame is dropped and `RIS2.QFF0` is set. The MAC tries the same descriptor again with the next frame, so the driver never has to restart the queue.

The first descriptor of each ring comes from a small table at `DBAT`: entry 0 for transmit, entry 4 for receive. The MAC loads them each time it enters OPERATION mode.

## 3. MDIO by hand

The Linux driver does not use the MAC's MDIO controller. It moves the pins itself, through register `CXR23` (MDC bit 0, MM bit 1 = "the MAC drives the line", MDO bit 2, MDI bit 3), with the generic `mdio-bitbang` code. A read of PHY register 1 is 32 preamble bits, start `01`, opcode `10`, the PHY address, the register, then the PHY's answer:

```
MAC drives (MM = 1):  1 x32 | 0 1 | 1 0 | 0 0 1 1 1 | 0 0 0 0 1 |
PHY drives (MM = 0):                                             | 0 | D15 ... D0 |
                                                                  turnaround
```

After each rising edge of MDC the PHY presents its next bit, and Linux reads MDI after the falling edge. The turnaround bit must be 0: a 1 means "no PHY here", and Linux returns `0xffff`. Every step is a read-modify-write of `CXR23`, so the register must read back what was written, although the manual says MM reads 0 (a recorded conflict, [`ravb.md`](../research/ravb.md) §6).

The device tree names the PHY by its ID (`ethernet-phy-id0022.1640`) and address (`reg = <7>`), so Linux never reads the ID registers and never scans the bus.

## 4. The link, and why the interrupt matters

The board's device tree gives the PHY an interrupt (`interrupts-extended = <&irqc RZG2L_IRQ2 IRQ_TYPE_LEVEL_LOW>`). With an interrupt, phylib does not poll. It checks the link once when the interface comes up, and after that only when the PHY interrupt fires:

```
[    5.550088] Microchip KSZ9131 Gigabit PHY 11c20000.ethernet-ffffffff:07: attached PHY driver (mii_bus:phy_addr=11c20000.ethernet-ffffffff:07, irq=46)
[    5.610241] ravb 11c20000.ethernet eth0: Link is Up - 1Gbps/Full - flow control off
[   13.599718] ravb 11c20000.ethernet eth0: Link is Down
```

The last line is the QEMU monitor's `set_link net0 off`. Its path: the backend tells the NIC, the NIC tells the PHY model "no cable", the PHY latches "link down" in its register `0x1B` and pulls `INT_N` low, the IRQC sees a low level on IRQ2 (`IITSR` = 00) and raises SPI 3, Linux reads `0x1B` (which clears it, so `INT_N` returns high) and then BMSR. Each step had to exist: before M6, the IRQC had registers but no inputs, so this event would never reach Linux.

Two details of this path are easy to get wrong:

- **BMSR link status is latched low** (IEEE 802.3 22.2.4.2.13): after a loss, the first read gives 0 even if the link is back, and phylib reads twice.
- **The PHY must lower `INT_N`** as soon as its status is read. The interrupt is level-triggered and shared; a line that stays low with nothing to report makes Linux disable it ("nobody cared").

## 5. Checksums the hardware computes

The MAC has a checksum engine (TOE). Linux turns it on and then leaves the IPv4, TCP and UDP checksums of outgoing frames for it to fill in. A model that sends the frames as given sends wrong checksums, and QEMU's user network drops them, so even DHCP fails. On receive, the engine puts a 4-byte result where the CRC was: 0 for "correct", `FFFF` for "not a frame I check". The mainline driver trusts IPv4 frames with both halves 0; Renesas's kernel looks only at the last two bytes and also offloads IPv6.

## 6. The model in QEMU

- **A NIC**: the MAC model calls `qemu_new_nic()` and gives QEMU a `receive` function. It sends with `qemu_send_packet()`. `link_status_changed` tells it when `set_link` pulls the cable.
- **Synchronous work**: a transmit request runs the ring at once; a received frame is stored when QEMU delivers it. So the "busy" bits Linux polls (`TSRQ0`, `CSR.TPO`, `CSR.RPO`) read 0 whenever Linux looks, as on an idle MAC.
- **A separate PHY device** (`ksz9131-phy`), on the board, not in the SoC: it sits on the SMARC module. Its `INT_N` is a GPIO into the IRQC's `irq` input 2; its "link" output goes back to the MAC, which reports it in `CXR2B` and in the `LINKI` interrupt the vendor kernel enables.
- **The MAC address**: on the board, U-Boot writes it into the device tree (`local-mac-address`) before it starts Linux. QEMU's loader does the same with the NIC's address, so `-nic ...,mac=` sets the address Linux uses.
- **User networking** (`-nic user`) gives the guest a private network with a DHCP server and the host as `10.0.2.2`. It needs no root and no host interface, so the acceptance test runs anywhere.

## 7. Try it

The commands are in the [walkthrough](../walkthrough.md#m6-ethernet). To see the MDIO frames and the descriptor work, add `-trace 'renesas_gbeth_*' -trace 'ksz9131_*' -D build/net.log` to the `run.sh` line.

## 8. How we know it works

The qtest `rzv2l-gbeth-test` drives the registers and the descriptor rings directly, with the test itself as the link partner on a socket, and checks values from the manual and IEEE 802.3. Each case was seen to fail on a deliberate fault in the model ([tasks](../units/M6-ravb/tasks.md)). The acceptance run `tests/acceptance/m6/net.py` boots both kernels and checks DHCP, transfers of 3 MiB each way by SHA-256, frame sizes from 60 to 1514 bytes, more frames than the rings hold, `set_link` off and on, interface down and up, and a machine reset.

## 9. Pitfalls

- **Two descriptors per frame.** The `ravb` driver splits every transmitted frame into FSTART and FEND (`ravb_main.c:2132-2221`), and frees buffers only when both read FEMPTY. A MAC that writes back only the last descriptor of a frame stalls the queue after 63 frames.
- **Checksum offload is not optional.** With `NETIF_F_HW_CSUM` on (the driver's default), Linux sends TCP/UDP frames with only the pseudo-header sum in the checksum field (manual §30.5.6). Without the engine's work, a strict peer drops every frame, starting with DHCP.
- **No polling with a PHY interrupt.** phylib reads the PHY once at link-up and then waits for the interrupt (`phy.c:1523`). A model without the interrupt path comes up once and never notices a cable change.
- **Self-clearing bits.** `BMCR` reset and auto-negotiation restart must read 0 when they are done, or phylib reports no link on its single pass (`phy_device.c:2576`).
- **MM reads back.** The manual says `CXR23.MM` reads 0 (p.2145), but bit-banged MDIO is a sequence of read-modify-writes: a model that follows the text there breaks every MDIO frame.
- **The interrupt the PHY shares.** The PHY interrupt is level-low and shared: assert it only while an enabled status bit is set, and drop it when the status register is read (`micrel.c:563-579`).
