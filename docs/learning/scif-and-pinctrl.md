# SCIF and pin control in plain terms

Companion to `../research/scif.md` and `../research/pinctrl.md`.

## SCIF: the UART

SCIF0 is the serial port behind the board's debug console (`ttySC0`). From software's point of view it is a few registers:

| Register | Role | Plain meaning |
|---|---|---|
| `FTDR` | transmit data | write a byte here to send it |
| `FRDR` | receive data | read a received byte |
| `FSR` | status | flags: "TX FIFO has room" (TDFE), "transmission finished" (TEND), "data ready" (RDF/DR), errors |
| `SCR` | control | turn the transmitter/receiver and interrupts on (TE, RE, TIE, RIE) |
| `SMR`, `BRR`, `SEMR`, `MDDR` | format and speed | 8N1, baud-rate divisor and fine-tune |
| `FCR`, `FDR` | FIFO control and levels | reset the FIFOs, set trigger levels, read how full they are |

**The 16-byte FIFOs.** The hardware has a 16-byte queue in each direction. Software dumps up to 16 bytes and the UART shifts them out one bit at a time.

**TEND, the subtle part.** Firmware (TF-A, U-Boot, OP-TEE) prints a character like this:
1. Write the byte to `FTDR`.
2. Read `FSR` and write it back with TEND cleared ("I'm waiting for this byte").
3. Loop until TEND becomes 1 again ("the byte left the wire").

If a QEMU model sets TEND *instantly* during step 1, step 2 clears it and step 3 waits forever, because nothing will set it again. So the model needs a small timer per character that sets TEND a moment later, like real hardware finishing a transmission. Status flags follow the manual's rule: they can only be cleared by writing 0 after reading them as 1.

**Why a new model.** QEMU's existing `sh_serial.c` uses the older SH4 register layout, resets FSR to the wrong value (`0x60` vs the manual's `0x20`) and sets TEND on every read. It is close, but not this hardware.

**Two ways Linux prints:**
- **earlycon**, very early: pokes `SCR` and `FTDR`/`FSR` directly, polling, with no clocks or interrupts needed. It needs `earlycon` on the kernel command line.
- **ttySC0**, the real driver: needs clocks, resets, pins and the interrupt controller ready first (see the CPG note), but its console output also polls.

**The baud-rate mystery, explained.** TF-A sets the baud rate, then selects a mode in which offset 0x02 addresses `MDDR` instead of `BRR`. U-Boot's later divisor write therefore lands on `MDDR`, which ignores writes while the UART is running. The baud rate TF-A chose survives, and the console works even though U-Boot "computed it wrong".

## Pin control (PFC): which job each pin does

Most SoC pins can do several jobs: GPIO, UART, I²C, Ethernet and so on. The **PFC** (pin function controller) chooses the job per pin. For the console, pins on port 38 must be switched from GPIO to "SCIF0 TX/RX".

| Register | Plain meaning |
|---|---|
| `PWPR` | the safety catch: PFC registers are write-protected until software unlocks them |
| `PMC` | per pin: plain GPIO (0) or peripheral function (1) |
| `PFC` | per pin: *which* peripheral function (a small number per pin) |
| `PM` | GPIO direction (input/output), when the pin is a GPIO |

Unlocking is a fixed dance: clear B0WI, set PFCWE, write `PMC`/`PFC`, then lock again.

**Why the console needs pinctrl to probe.** The UART's device-tree node says "apply my pin settings first". If the pin-control driver never appears, Linux keeps postponing the UART forever, with no timeout in this path for the pinned kernel. So the PFC model must let the driver probe and must store and read back what it writes. A model that returned zeros would let the probe pass while silently lying about pin state, which the project forbids.

**The dependency chain.** IRQC (interrupt controller for external pins) → pin control (GPIO interrupts need IRQC) → UART.

## Spot checks (HW manual Rev 1.50, printed page numbers)

| # | Page | Register | Confirm |
|---|---|---|---|
| 1 | p.1278, §22.2.7 | `FSR` | initial value `0x0020`: TDFE (b5) = 1, TEND (b6) = 0; flags cannot be written to 1 |
| 2 | p.1287, §22.2.9 | `MDDR` | reset `0xFF`; shares the address with `BRR` when `SEMR.MDDRS` = 1; writable only while TE = RE = 0 (the baud-rate mystery) |
| 3 | p.1271, Table 22.4 | SCIFA register list | offsets 0x00–0x16 and reset values (BRR `0xFF`) |
| 4 | p.1323, Table 22.19 vs p.544, Table 8.2 | SCIF interrupts | ERI and BRI on separate SPIs; TEI and DRI share one SPI |
| 5 | p.3404, §41.3.10 | `PWPR` | initial `0x80`: B0WI (b7) = 1 at reset; PFCWE (b6) unlocks PFC writes |
| 6 | p.3371 / p.3373 / p.3370 | `PMC36`, `PFC36`, `PM36` | the port-38 register offsets and their zero reset values |
