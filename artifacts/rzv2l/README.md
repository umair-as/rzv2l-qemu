# RZ/V2L documentation baseline

This is the reference collection for the specification (`docs/spec/project.md`), collected 2026-10-08.

**The documents are Renesas copyright and are not redistributed.** Only this index, `manifest.json` (path, SHA-256, size, page count) and `SHA256SUMS` are tracked. The PDFs and their text extracts stay local and are gitignored. Obtain them from renesas.com under the document numbers below, then verify them with `SHA256SUMS`.

## Start here

| Reference | Use |
| --- | --- |
| SoC hardware manual Rev.1.50 (`hardware/r01uh0936ej0150-rzv2l.pdf`) | Primary authority for address map, interrupts, SCIF, CPG/reset, power, storage, Ethernet and firmware-visible registers. |
| Arm CoreLink GIC-600 r1p6 TRM, 100336_0106_00 (`hardware/arm-100336_0106_00-gic600-r1p6-trm.pdf`) | GIC-600 register values. The SoC manual defers to it (§8.4 p.548). Arm copyright; obtain from developer.arm.com. |
| Datasheet Rev.1.10 (`hardware/r01ds0485ej0110-rzv2l.pdf`) | Device variants and capabilities. |
| SMARC module manual Rev.2.00 (`hardware/r01uh0964ej0200-…`) | Module memory, peripherals and wiring. Confirm the physical board revision. |
| SMARC carrier manual Rev.2.00 (`hardware/r01uh0966ej0200-…`) | Carrier connections, switches and console routing. |
| Linux Start-up Guide Rev.1.05 (`guides/r01us0617ej0105-…`) | BSP build, boot media, board setup and firmware programming. |
| BSP driver manuals (`bsp-drivers/`) | Software-interface evidence only, not a replacement for the hardware manual. |
| Security guides (`security/`) | Secure boot, security package and key-management formats. |
| Deferred references (`deferred/`) | AI and GStreamer guides, kept for later; they do not expand the emulation scope. |

## Searching

The local `text/` directory mirrors the PDF paths with `pdftotext -layout` extracts. Cite the PDF's printed section, table or page, and check diagrams and tables against the PDF itself.

```bash
rg -n 'SCIF|CPG|GIC' artifacts/rzv2l/text/hardware/r01uh0936ej0150-rzv2l.txt
(cd artifacts/rzv2l && sha256sum -c SHA256SUMS)
```

## Not included

The following are not part of this collection:
- schematics
- pinned Linux, TF-A, U-Boot and OP-TEE sources (see `docs/sources.md`)
- acceptance guest binaries
- board observations

## Inventory

| File | PDF pages |
| --- | ---: |
| `guides/EPBZ-IMB-22-0032-8_RZV2L_Easy_Download_Guide.pdf` | 2 |
| `hardware/arm-100336_0106_00-gic600-r1p6-trm.pdf` | 216 |
| `hardware/r01ds0485ej0110-rzv2l.pdf` | 71 |
| `hardware/r01uh0936ej0150-rzv2l.pdf` | 3559 |
| `hardware/r01uh0964ej0200-rzg2l-v2l-smarc-module-um.pdf` | 58 |
| `hardware/r01uh0966ej0200-rz-smarc-carrier-um.pdf` | 60 |
| `guides/r01us0617ej0105-rz-v(Linux+Start-up+Guide+RZV2L).pdf` | 56 |
| `deferred/r01us0619ej0202-rzg2l_rzv2l_GStreamer_UME.pdf` | 76 |
| `deferred/r11an0616ej0750-rzv-ai-imp-getstarted.pdf` | 86 |
| `deferred/r11an0622ej0750-rzv-ai-imp-appendix.pdf` | 55 |
| `bsp-drivers/r01us0468ej0107-rz-g_Kernel_Core_UME.pdf` | 23 |
| `bsp-drivers/r01us0474ej0107-rz-g_SD_MMC_UME.pdf` | 25 |
| `bsp-drivers/r01us0475ej0107_rz-g_Gigabit_Ethernet_UME.pdf` | 25 |
| `bsp-drivers/r01us0476ej0107-rz-g_MTU3a_UME.pdf` | 32 |
| `bsp-drivers/r01us0477ej0107-rz-g_I2C_UME.pdf` | 30 |
| `bsp-drivers/r01us0478ej0107-rz-g_CANFD_UME.pdf` | 24 |
| `bsp-drivers/r01us0479ej0107-rz-g_WDT_UME.pdf` | 25 |
| `bsp-drivers/r01us0480ej0107-rz-g_DMAC_UME.pdf` | 19 |
| `bsp-drivers/r01us0481ej0107-rz-g_SPI_UME.pdf` | 20 |
| `bsp-drivers/r01us0482ej0107-rz-g_SPI_Multi IO_UME.pdf` | 21 |
| `bsp-drivers/r01us0483ej0107-rz-g_SCIFA_UME.pdf` | 23 |
| `bsp-drivers/r01us0484ej0107-rz-g_GPT_UME.pdf` | 26 |
| `bsp-drivers/r01us0485ej0107-rz-g_USB2.0_Host_UME.pdf` | 22 |
| `bsp-drivers/r01us0486ej0107-rz-g_Thermal_Sensor__UME.pdf` | 20 |
| `bsp-drivers/r01us0487ej0107-rz-g_AD_Converter_UME.pdf` | 22 |
| `bsp-drivers/r01us0488ej0107-rz-g_GPIO_UME.pdf` | 24 |
| `bsp-drivers/r01us0489ej0107-rz-g_LCDC_UME.pdf` | 28 |
| `bsp-drivers/r01us0490ej0107-rz-g_SSI_UME.pdf` | 35 |
| `bsp-drivers/r01us0491ej0107-rz-g_USB2.0_Function_UME.pdf` | 23 |
| `bsp-drivers/r01us0499ej0107-rz-g_CRU_UME.pdf` | 23 |
| `bsp-drivers/r01us0552ej0107-rz-g_POE3_UME.pdf` | 20 |
| `bsp-drivers/r01us0605ej0107-rz-g_Power_Management_UME.pdf` | 37 |
| `security/r11an1001ej0100-rzv2l-security-startup-guide.pdf` | 40 |
| `security/r11an1002ej0100-rzg2l-rzv2l-security-users-manual.pdf` | 79 |
| `security/r11ut0112ej0100-rzv2l-release-note.pdf` | 8 |
| `security/r11an1043ej0100-sblib.pdf` | 26 |
| `security/r20ut5349ej0111-security.pdf` | 211 |
