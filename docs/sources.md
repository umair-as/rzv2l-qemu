# RZ/V2L source register

The local documentation collection is indexed in [artifacts/rzv2l/README.md](../artifacts/rzv2l/README.md). It contains the SoC hardware manual Rev.1.50, SMARC module and carrier manuals Rev.2.00, datasheet, Linux startup guide, BSP driver manuals and security guides, plus secondary project notes.

[manifest.json](../artifacts/rzv2l/manifest.json) records the collection-relative paths, file hashes, sizes and PDF page counts. Searchable text extracts are under `artifacts/rzv2l/text/`; the original PDFs remain the citation authority.

Sources are authoritative by **domain**, not by a single ranking (spec §5):

| Domain | Authority |
|---|---|
| Intended register layout, bit meaning, reset values | the HW manual |
| Board wiring and straps | the SMARC module and carrier manuals |
| Actual silicon behaviour | measurements on the EVK (`evidence/`), with boot stage and build identity |
| What guest software requires | the pinned guest and firmware sources, checked against their effective build configuration |
| Emulation mechanisms | upstream QEMU |
| Leads only | BSP driver manuals, analogous QEMU ports, issues, blogs |

When sources disagree, the disagreement is recorded with all sides and resolved explicitly (example: the DEVID value, where Table 6.1 and §6.3.43 conflict and the EVK decides). No retrieval score or global rank silently picks a winner. Confirm document applicability to the physical board revision and the chosen BSP before deriving contracts.

Pinned firmware sources studied so far: see `research/boot-chain-firmware.md` (TF-A `f59ed5a31`, U-Boot `4eebfbaa4e`, OP-TEE `82a5cd3b`, kernel 6.12.59-cip14).

**Status (2026-10-08):**
- Derived: the device map (`device-map.md`) and the boot dependency graph (`research/boot-dependency-graph.md`).
- Pinned: guest and firmware sources (below, and `research/boot-chain-firmware.md`).
- First EVK evidence recorded (`evidence/EVK-2026-10-08-boot-log.md`).
- **Still missing:** standalone board schematics; built acceptance guest artifacts, including a checked effective G0 `.config` (the research used the arm64 defconfig source); and the post-firmware register measurements listed in `evidence/requests.md`.

## Pinned guest kernels (2026-10-08)

| Tier | Source | Revision |
|---|---|---|
| **G0** (OSS reference) | https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git | `v6.12.59` (`d5dc97879`) |
| **G1** (vendor reference) | https://github.com/renesas-rz/rz_linux-cip | branch `rz-6.12-cip14`, `212f6e88b7` (6.12.59-cip14; the kernel the reference EVK runs) |

**Why G0 = v6.12.59 and not the newest mainline:** G1 is v6.12.59 plus CIP and Renesas patches. Pinning G0 to the same base makes any G0/G1 difference attributable to the vendor delta alone. Measured diff lines on the boot path:

| File | v6.12.59 → G1 | v6.12.59 → v6.18.55 |
|---|---:|---:|
| `drivers/clk/renesas/rzg2l-cpg.c` | 5 | 583 |
| `drivers/clk/renesas/r9a07g044-cpg.c` | 55 | 221 |
| `drivers/pinctrl/renesas/pinctrl-rzg2l.c` | 745 | 944 |
| `drivers/tty/serial/sh-sci.c` | 2 | 890 |
| `drivers/soc/renesas/renesas-soc.c` | 33 | 45 |
| `drivers/clocksource/renesas-ostm.c` | 0 | 4 |
| `drivers/irqchip/irq-renesas-rzg2l.c` | 0 | 111 |
| `arch/arm64/boot/dts/renesas/r9a07g054.dtsi` | 0 | 115 |

Behavioural example: v6.18 drives the CPG MSTOP registers on every module clock change; v6.12.59 and G1 do not for RZ/V2L. Newer mainline (v6.18 LTS) is a later regression target, not on the M3 critical path. The latest vendor branch at the time of pinning is `rz-6.12-cip15` (v6.12.63); move G0 and G1 together if G1 moves.
