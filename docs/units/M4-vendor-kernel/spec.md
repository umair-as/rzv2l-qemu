# M4-vendor-kernel — spec

**Milestone:** M4 (first unit; the loader fixups follow). **Requirements:** REQ-GUEST-001, REQ-GUEST-002, REQ-WDT-001.

## Scope

**The vendor kernel (G1).** `tests/guests/g1/build-kernel.sh` builds `rz_linux-cip` at `212f6e88b7` (branch `rz-6.12-cip14`, the kernel the reference EVK runs; `../../sources.md`) with its own in-tree arm64 `defconfig`, as the Renesas BSP recipe does (`KBUILD_DEFCONFIG = "defconfig"`, no RZ/V2L config fragments), and its own `r9a07g054l2-smarc.dtb` (DTB-V). It boots in direct mode with the M3 BusyBox initramfs and the DTB's own bootargs (no `-append`).

**The watchdog timer** (manual §21, `renesas-rzg2l-wdt`), WDT0-2 at `0x12800800`, `0x12800C00`, `0x12800400`, FUNCTIONAL:

- The nine registers of Table 21.4 (p.1246), 32-bit, with their reset values. WDTSET keeps WDTTIME (bits 31:20); WDTSET and WDTTIM ignore writes while the counter runs; WDTEN cannot be cleared (§21.3.1-21.3.3).
- The counter runs at WDTn_CLK, 24 MHz (§21.1.1), and overflows every (WDTTIME + 1) × 2²⁰ clocks (§21.3.2). The first overflow sets WDTINT.INTDISP and the WDTINT interrupt (SPI 49 + 2n, level); writing INTDISP = 1 clears both and the counter (§21.3.4); a second overflow asserts WDTRSTB (§21.4.1). The EVK confirms the formula: U-Boot's WDTSET `0x2AE00000` (EVK-R40) is a 30 s cycle and its stated 60 s timeout.
- PEEN = 1 forces WDTRSTB when PECR = 0 and PERROUT (SPI 50 + 2n) otherwise (Table 21.5 rows 7-8, p.1262). Which PECR bit governs the forced error is not stated; the model uses "any bit set" (I). PESR, PEER and PEPO are stored only: no parity inputs.
- **CPG side** (§7.2.4.121, §7.2.4.182-183): `CPG_RST_WDT` bit n drives channel n's PRESETN, so applying it resets the channel. That is how Linux stops the watchdog and changes a running timeout (`rzg2l_wdt.c` `rzg2l_wdt_stop`). `CPG_WDTRST_SEL` (reset `0x88`) bits 2:0 let WDTRSTB reset the system; QEMU's watchdog action (default: reset) does it. `CPG_WDTOVF_RST` records the channel, is cleared by writing 1 under its write-enable bit, and survives the system reset it reports. Bits 10:8 (cold reset) and 6:4 (WDTOVFOUT pin) are stored only.
- **Start states:** firmware mode: manual reset values (`RST_WDT 0x9` holds WDT1 and WDT2 in reset). Direct mode: `RST_WDT 0xF` (EVK-R16), `WDTRST_SEL 0x8F` (TF-A `cpg_setup` sets bits 2:0; code-derived, EVK-R73 requested), and the WDT registers at reset values: **not running**, although U-Boot autostarts WDT0 on the EVK (EVK-R40; device map gap 16, spec §9). A kernel with no watchdog daemon would otherwise reset after 60 s.

**Windows the vendor kernel touches:** its `defconfig` builds in drivers that mainline builds as modules. Each window is mapped as the device map records it (UNIMP): display (MIPI DSI, VSPD, FCPVD, DU), SSI0/1, RSPI1, CAN-FD, ADC, USB0 function, RPC (registers, write buffer, flash window).

**Not in this unit:** U-Boot's loader fixups (the next unit, REQ-GUEST-005); the downstream image's device-tree patches (CMA and DRP-AI reserved memory, watchdog channel bindings): they are G2, studied only.

## What the guest needs

- `drivers/watchdog/rzg2l_wdt.c` (identical in G0 and G1): start writes WDTINT, WDTSET, WDTTIM, WDTCNT after deasserting the reset (:99-124); ping writes WDTINT (:226-233); stop asserts the reset (:126-140), and a timeout change while running stops and starts it (:142-162); restart writes PECR = 0, then PEEN = 1 (:192-196). PSCI's restart handler has the higher priority, so `reboot` does not take this path.
- The vendor `defconfig`: `CONFIG_RENESAS_RZG2LWDT=y`, `CONFIG_DRM_RZG2L_MIPI_DSI=y`, `CONFIG_CAN_RCAR_CANFD=y`, `CONFIG_SPI_RPCIF=y`, `CONFIG_USB_RENESAS_USBHS=y` and others `=m` in G0.

## Exit criterion

1. The M3 acceptance list passes on G1, on two cold boots: console takeover, a marker command, both CPUs, the CPG, pin controller and SCIF0 drivers bound, guest time rate, and a log with only recorded stub windows.
2. On WDT0 through `/dev/watchdog`: pinged, no reset in 8 s; stopped by the daemon, no reset in 8 s; not pinged, the board resets and `CPG_WDTOVF_RST` reads 1 after the new boot.
3. qtests assert the manual values; M3 acceptance (G0) still passes.

## Evidence

Manual §21 (p.1241-1264), §7.2.4.121 (p.394), §7.2.4.182-183 (p.459-461), Table 8.2 (p.536); EVK R16, R40 (`../../evidence/EVK-2026-10-29-post-firmware.md`); TF-A `cpg_setup` (`WDTRST_SEL |= 7`); linux v6.12.59 and rz_linux-cip `212f6e88b7` `drivers/watchdog/rzg2l_wdt.c`.

## Coverage list (G1, `-d unimp,guest_errors,invalid_mem`)

| Window | Guest outcome |
|---|---|
| `mipi-dsi`, `vspd` | DSI probe continues on zeros; no display |
| `canfd` | `reset controller failed: -ETIMEDOUT`; the driver's error path then disables a clock twice (a kernel WARN in `rcar_canfd_global_deinit`, a driver bug on a failed probe) |
| `rpc-if`, `rpc-if-dirmap` | the QSPI driver polls (about 377000 reads per boot); no flash |
| `usb0-func`, `adc` | probes fail within a bound |
| G0 windows (ETH, RIIC, USB host, SDHI, DMAC, TSU, USB PHY control) | as in M3 |

No unmapped access, no guest error from a modelled block.

## For the operator

- **Direct mode starts with the watchdog stopped** (gap 16). The EVK's U-Boot leaves it running with 60 s; mimicking that would reset any guest without a watchdog daemon.
- **`CPG_WDTRST_SEL` = `0x8F` after firmware** is read from TF-A's code, not the EVK (request EVK-R73).
