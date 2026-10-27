---
name: soc-wiring
description: Put a device model into the rzv2l-smarc machine — SoC child, memory map, GIC SPI wiring, chardev, Kconfig select chain — and update the acceptance expectations from docs/device-map.md. Use after a device model compiles, or when adding an UNIMP window or a board-level property.
---

# SoC wiring

Files: `qemu/hw/arm/r9a07g054.c` (SoC), `qemu/include/hw/arm/r9a07g054.h`, `qemu/hw/arm/rzv2l-smarc.c` (board), `qemu/hw/arm/Kconfig`.

## Steps

1. **Header:** add the device state as a member of `R9A07G054State` (an array for repeated instances, e.g. SCIF0-4). Document any new SoC property in the "QEMU interface" comment.
2. **Memory map:** add an enum entry and the base to `r9a07g054_memmap[]`. Base and size come from the `docs/device-map.md` row, never from a driver or a sibling SoC.
3. **init:** `object_initialize_child(obj, "<name>", &s-><dev>, TYPE_...)`. Board-facing properties of the device become SoC aliases (`object_property_add_alias`), as `boot-mode` does.
4. **realize:** set properties, `sysbus_realize(..., errp)` (return on failure), `sysbus_mmio_map()`.
5. **IRQs:** DT `GIC_SPI n` is GIC input `n`: `sysbus_connect_irq(sbd, line, qdev_get_gpio_in(DEVICE(&s->gic), n))`. INTID is n + 32; don't add 32 yourself. Take n and the line order from the device-map row (e.g. SCIF0 SPI 380-384 = ERI, BRI, RXI, TXI, TEI/DRI). Realize the GIC before wiring.
6. **Chardev:** the board console is SCIF0. Wire `serial_hd(0)` to it (`qdev_prop_set_chr`); the other instances get `serial_hd(n)` in DT alias order.
7. **Placeholder windows:** `create_unimplemented_device()` reads as zero. Use it only where the device map says UNIMP **and** a read of 0 is honest (spec §7). Otherwise leave the window unmapped (abort) or write a real stub.
8. **Kconfig:** `config R9A07G054` gets `select <NEW_DEVICE>`. Without it the file never compiles.
9. Build: `cd build/qemu && ninja qemu-system-aarch64`.
10. **Check the machine against the documents**, not against itself:
    - `printf 'info mtree -f\nquit\n' | build/qemu/qemu-system-aarch64 -M rzv2l-smarc -S -display none -nodefaults -monitor stdio`
    - same with `info qtree`
    - every new window and property must match its device-map row.
11. **Acceptance expectations:** add the new lines to the milestone's `tests/acceptance/<m>/expected/*.txt` **from the device-map row**, with a comment naming the row. Never paste QEMU output into an expected file: that proves only that the model did not change.
12. Run the acceptance run for the current milestone (e.g. `tests/acceptance/m1/run.sh`). An unexpected line in the log gate means the guest touched something not modelled or listed.

## Pitfalls

- The order of `sysbus_connect_irq` lines is the device's `sysbus_init_irq` order. A swap passes every register qtest and breaks only under a running guest; the probe or a qtest using `qtest_irq_intercept_in` catches it.
- `num-irq` and IRQ numbers are coupled: changing one without the other aborts QEMU at startup (`docs/learning/testing.md` §1, the fourth mutation row).
- A device the SoC realizes but the board never needs still appears in `info qtree`: the acceptance qtree check is exact, so update it in the same change.
- Firmware-reserved DDR (`0x40000000`-`0x47FFFFFF`) stays free of QEMU blobs; don't move `loader_start` to make something fit.
