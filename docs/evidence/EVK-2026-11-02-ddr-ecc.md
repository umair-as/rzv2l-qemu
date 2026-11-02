# EVK 2026-11-02: the DDR controller's ECC enable bits (EVK-R80)

**Board:** RZ/V2L SMARC EVK, console on SCIF0 (115200 8N1).

**Image:** EDGE AI OS 0.1.0, the image of [`EVK-2026-11-01-firmware.md`](EVK-2026-11-01-firmware.md) (a G2 image: a product built on the Renesas BSP); firmware banners as recorded there.

**Method:** the operator typed the command at the Linux root shell; the output was copied from the console. Stage: post-Linux. The request asked for the U-Boot prompt; BL2 sets the ECC configuration once, before U-Boot, and U-Boot reads it from the same Non-secure level as Linux, so the bits answer the same question (I).

**Question:** the value U-Boot's `board_fit_config_name_match()` reads at `0x1141018C` (bits 25:24, ECC enable), which picks its device tree, and which the model's DDR controller stub must return.

```
root@edge-rzv2l:~# devmem2 0x1141018c w
/dev/mem opened.
Memory mapped at address 0xedbfd9704000.
Read at address  0x1141018C (0xedbfd970418c): 0x00000FFF
```

**Reading (O):** bits 25:24 = 0: ECC disabled, so U-Boot selects `smarc-rzv2l` (memory `0x78000000`), consistent with the board's `DRAM:  1.9 GiB`. Bits 11:0 read `0xFFF`; the manual does not describe this register (the DDR controller is listed in Table 5.1 only), and no guest in this chain reads those bits. The model's stub window reads 0: right for bits 25:24, different in bits 11:0 (recorded in the device map). No read side effect.
