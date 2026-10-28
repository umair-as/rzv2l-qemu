---
name: soc-wiring
description: Put a device model into the rzv2l-smarc machine — SoC child, memory map, GIC SPI wiring, chardev, Kconfig select chain — and update the acceptance expectations from docs/device-map.md. Use after a device model compiles, or when adding an UNIMP window or a board-level property.
---

# SoC wiring

Files: the SoC `qemu/hw/arm/r9a07g054.c` (+ header), the board `qemu/hw/arm/rzv2l-smarc.c`, `qemu/hw/arm/Kconfig`.

## Steps

1. The device is a child of `R9A07G054State` (an array for repeated instances, e.g. SCIF0-4). Board-facing properties become SoC aliases, as `boot-mode` does; document them in the header's "QEMU interface" comment.
2. Base and size go into `r9a07g054_memmap[]` **from the `docs/device-map.md` row**, never from a driver or a sibling SoC.
3. Realize the GIC before wiring IRQs. DT `GIC_SPI n` is GIC input `n` (INTID n+32): don't add 32 yourself. Line order comes from the device-map row (e.g. SCIF0 SPI 380-384 = ERI, BRI, RXI, TXI, TEI/DRI).
4. The board console is SCIF0 (`serial_hd(0)`); other instances follow DT alias order.
5. `config R9A07G054` must `select` the new device, or its file never compiles.
6. **Check the machine against the documents, not against itself:** every new window in `info mtree -f` and every new device and property in `info qtree` matches its device-map row.
7. Add the new lines to the milestone's `tests/acceptance/<m>/expected/*.txt` **from the device-map row**, with a comment naming the row. Never paste QEMU output into an expected file: that only proves the model did not change.
8. Run the milestone's acceptance run. An unexpected line in the log gate means the guest touched something not modelled or listed.

## Placeholder windows

`create_unimplemented_device()` reads as zero. Use it only where the device map says UNIMP **and** a read of 0 is honest (spec §7), and list it with its fidelity class. Otherwise write a real stub, or leave the window unmapped; spec §7 reserves unmapped windows for regions that also fault on the board, so an unmapped window over working silicon is a fidelity gap to record.

## Traps

- `sysbus_connect_irq` order is the device's `sysbus_init_irq` order. A swap passes every register qtest and breaks only a running guest; a probe or an output-intercept qtest catches it.
- `num-irq` and the IRQ numbers are coupled: change one without the other and QEMU aborts at startup (`docs/learning/testing.md` §1).
- A device the SoC realizes appears in `info qtree` even if the board never uses it: the acceptance qtree check is exact, so update it in the same change.
- DDR below `0x48000000` is where the board's firmware lives (BL31 `0x44000000`, OP-TEE and its SHM up to `0x47FFFFFF`; device-map DDR row). Keeping QEMU blobs out of it is the project's own placement rule (I), checked by the M1 acceptance run; don't move `loader_start` to make something fit.
