# M3b-pfc-irqc — spec

**Milestone:** M3 (third unit, after the OS timer). **Requirements:** REQ-PFC-001, REQ-IRQC-001.

## Scope

**Pin function controller** (PFC/GPIO, manual section 41, `0x11030000`, 64 KiB): `renesas-rzg2l-pfc`, FUNCTIONAL for configuration.

- All 592 registers of §41.2: per port Pn, PMn, PMCn, PFCm, PINn, ISEL, IOLH, SR, PUPD, IEN, the noise filter registers, and SD_ch0/1, QSPI, ETH_ch0/1, PWPR, ETH MII/RGMII. Reset values and implemented bits per port come from §41.2 and the pin correspondence tables (pins per port: Table 41.1 p.3386-3387). The map was extracted by a research pass and spot-checked against the manual (IEN list p.3385; IOLH group A 01b / group B 10b reset, §41.3.7 Note 1).
- **PWPR** (§41.3.10): PFC registers take writes only while PFCWE = 1; PFCWE changes only while B0WI was 0 before the write (an inference: the manual does not say whether the old or the new B0WI gates one combined write). PMC is not protected.
- **Accesses are split into bytes** (A). A register byte follows its implemented bits. A byte with no register reads 0, because the EVK reads PFC `+0x3100` as 0 with no bus error (R71). That it ignores writes, and that a wider access returns its neighbours' bytes, are assumptions: R71 is one 32-bit read. Undefined bytes and access sizes the manual does not list are logged. **Conflict recorded:** the manual gives PWPR as 8-bit; Linux and TF-A write it with 32-bit stores, so the model treats it as 32-bit wide.
- **PINn** (A) reads Pn for pins with PMn = 11b (output with input enabled) and 0 otherwise. **Assumption:** no pin is driven from outside; §41.3.5 says only that PINn gives the input value of the pin, so the qtest asserts the model's rule here, not a manual value.
- **Start states:** reset values; with `-kernel`, the EVK post-firmware values (R30-R36): PMC/PFC for SCIF0 (P38), SD0 (P47) and SD1 (P19) = `0x03` / `0x11`, SD_ch0 = 1, ETH MII/RGMII = `0x00`. TF-A's IOLH/SR/PUPD values for the SD and QSPI pins were not read on the EVK and stay at reset (A).
- **Not modelled:** electrical settings and IO voltages (stored only); ISEL routing to the IRQC; SD_ch0/QSPI becoming read-only in eMMC/QSPI boot modes; pin functions gating peripherals; TF-A's 64-bit stores (they are split into two 32-bit halves, one of which can be a hole).

**Interrupt control unit** (IA55, §8.5-8.6, `0x110A0000`, 64 KiB): `renesas-rzg2l-irqc`, a register-file STUB as the device map classes it.

- The 19 registers of Table 8.3 (p.549), 32-bit, reset 0. Selection registers (NITSR, IITSR, TITSR0/1, TSSR0-7) keep their implemented bits. Status registers (NSCR, ISCR, TSCR, BEISR0/1, EREISR0/1) can only be cleared (§8.6); with no input modelled they read 0. Other offsets and widths are a bus error (a design choice; the manual says only "prohibit to write undefined area"). The PFC reads its holes as 0 because the EVK does (R71); no IRQC hole has been read on the EVK, so the IRQC keeps the visible failure.
- **Not modelled:** the NMI, IRQ0-7 and TINT0-31 inputs and their routing to the GIC; NSCR.NSMON (NMI pin level) reads 0 (A).

## What the guest needs

linux v6.12.59 `drivers/pinctrl/renesas/pinctrl-rzg2l.c` and `drivers/irqchip/irq-renesas-rzg2l.c`, both built in.

- **IRQC:** probe does no register access; at interrupt allocation the driver read-modify-writes ISCR/IITSR/TSCR/TITSR/TSSR. IMSK/TMSK (`0x10010`, `0x10020`) are used only by RZ/Five. The pin controller binds only after the IRQC domain exists (`pinctrl.md` §6).
- **PFC at probe:** the `sound_clk` default state read-modify-writes IEN04 (`0x1820`, 32-bit); the GPIO hogs read-modify-write PMC, Pn and PMn (16-bit); `sh-sci` applies the SCIF0 pins with the PWPR unlock, PMC, PFC, relock sequence; Ethernet, SD and I2C pin groups write PFC, IOLH, SR, PUPD, ETH MII/RGMII and SD_ch (`pinctrl.md` §3-§4).

## Exit criterion

The G0 boot passes the pin controller probe and the `sh-sci` console takeover, and stops at the next block that needs its own model or a unit of its own. Windows touched before that are mapped by their device-map class.

## Evidence

HW manual Rev 1.50 §41 (p.3368-3421), §8.5-8.6 (Table 8.3 p.549); `../../research/pinctrl.md`; EVK R30-R36, R71 (`../../evidence/EVK-2026-10-29-post-firmware.md`); the extracted register map (working area, spot-checked as above).

## Next blocker (fork `7cdc8ea6a8`)

The kernel now boots to the end of its init:

```
[    6.475917] 1004b800.serial: ttySC0 at MMIO 0x1004b800 (irq = 36, base_baud = 0) is a scif
[    6.486472] printk: legacy console [ttySC0] enabled
[   24.345624] Kernel panic - not syncing: No working init found.  Try passing init= option to kernel.
[   24.365056] CPU: 0 UID: 0 PID: 1 Comm: swapper/0 Not tainted 6.12.59 #1
```

- **Cause:** there is no root file system. `root=/dev/nfs ip=on` finds no NFS server, and no initramfs is loaded. This is not a device model: it is the shell unit (a BusyBox initramfs built by a script under `tests/guests/`).
- **Layer verified:** the `-d` log has no unmapped access and no access to a modelled block outside its registers. The console handover now works without `keep_bootcon`: the acceptance run prints 423 lines on `ttySC0`.

### Coverage list (`-d unimp,guest_errors,invalid_mem`)

| Log lines | Window (device map) | Class | Guest outcome |
|---|---|---|---|
| `ravb-eth0/1` reads | ETH0/1 `0x11C20000`, `0x11C30000` | UNIMP (this unit) | probe -110 (`failed to switch device to requested mode`) |
| `riic0/1/3` reads and writes | RIIC `0x10058000` + n × `0x400` | UNIMP (this unit) | buses register; PMIC `raa215300` and clock chip `vc3` time out (-110) |
| `usb0-host`, `usb1-host` | `0x11C50000`, `0x11C70000` | UNIMP (this unit) | EHCI -110, OHCI -75 |
| `sdhi0/1` (polls) | `0x11C00000`, `0x11C10000` | UNIMP (this unit) | `timeout waiting for SD bus idle`; CMD52 timeout |
| `rz-dmac`, `usbphy-ctrl`, `tsu` | earlier units | as recorded | as before |

No PFC, IRQC, CPG, OS timer or SCIF line appears.
