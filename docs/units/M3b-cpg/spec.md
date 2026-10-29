# M3b-cpg — spec

**Milestone:** M3 (unit M3b-1). **Requirement:** REQ-CPG-001. **Status:** written 2026-10-29. The operator lifted the stop after this page: they review by booting the model, so implementation follows straight on.

## Scope

A new device `renesas-rzv2l-cpg` at `0x11010000` (64 KiB, 32-bit accesses only), wired into `r9a07g054`. It is FUNCTIONAL and faithful for what is modelled:

- **Every clock and reset family register in Table 7.5** (HW manual Rev 1.50 §7.2.3, p.246-251) holds its manual reset value. That is CLK_ON, CLK_MON, RST, RSTMON and MSTOP, DRP and MBUS included. The table also covers the PLL1 setting words, the dividers and the selectors. Each register's writable bits and write-enable bits come from its bit table in §7.2.4. Reserved bits keep their reset value.
- **Write enables** (§2.1 of `../../research/cpg-reset.md`): a field changes only when its own enable bit, 16 above the field's lowest bit, is set in the same write. Linux's hiword writes also set reserved upper bits, and those are ignored.
- **Monitors are computed on read.** CLK_MON = CLK_ON & the implemented bits, plus the monitor's own reserved read-as-1 bits. RSTMON = ~RST & the implemented bits. There is no settle latency, so Linux's 10 µs and 200 µs polls succeed on the first read.
- **CLKSTATUS reads 0.** Every divider and selector switch completes inside the write.
- **Two start states** behind a `direct-boot` property, which the board sets when it loads a kernel (as for SCIF0). The property selects the manual reset values or the EVK post-firmware values.

**Not modelled, honest fault:** the PLL monitors (SAMPLLn_MON, SIPLLn_MON, OTPPLLn_MON), PLL4/PLL6 and SIPLL5_CLK1-5, PLL1_SETTING and SAMPLL1_STBY, the PCH handshake (`0xB30-0xB44`, Stage B, M7), WDTOVF_RST/WDTRST_SEL, OTHERFUNC1/2. Every offset that Table 7.5 does not list is also a fault. Each of these logs `LOG_UNIMP` and returns a bus error. No clock, reset or MSTOP state gates another device; that gap is already recorded in the device map.

## What the guest needs

G0 = linux v6.12.59 `drivers/clk/renesas/rzg2l-cpg.c`, with the tables in `r9a07g044-cpg.c` (`r9a07g054_cpg_info`, `has_clk_mon_regs = true` at :500). `CONFIG_CLK_R9A07G054=y`. Every line below was checked on 2026-10-29.

| Access (guest `file:line`) | Register | Reset (manual) | Direct mode (EVK) |
|---|---|---|---|
| read PLL1 rate :968-969 (rate :971-974, ÷ PDIV) | SAMPLL1_CLK1 `0x004` / CLK2 `0x008` (§7.2.4.2-3 p.255-259) | `0x1901` / `0x180601` = 1200 MHz | same (R10) |
| read divider/mux values :293, :739 | PL1/PL2/PL3A/PL3B/PL6_DDIV `0x200-0x210`, PL3_SSEL `0x408`, PL6_SSEL `0x414`, PL6_ETH_SSEL `0x418` | all 0; `0x111`, `0x101`, `0x10` | PL3A `0x100`, PL3_SSEL `0x11` (R11) |
| SD mux write :475 + CLKSTATUS poll :169-176; 266 MHz step :208 | PL2SDHI_DSEL `0x218` (§7.2.4.21), CLKSTATUS `0x280` | `0x11`, 0 | `0x22`, 0 (R11) |
| write SIPLL5_STBY at probe :929-930 | `0x140` (§7.2.4.9) | `0x14` | not read (A: reset) |
| CLK_ON write :1231, CLK_MON poll 10 µs :1239-1240, is_enabled :1304 | `0x500-0x5E8` / `+0x180` | Table 7.5 | X01, all words |
| RST write :1437/:1467, RSTMON poll 200 µs :1450/:1480, status :1515 | `0x800-0x8E8` / `+0x180` | Table 7.5 | X02, all words |
| MSTOP written only by PM-domain callbacks :1683/:1696, never installed on V2L | `0xB60-0xB88` | 0 | 0 (R19) |
| critical clocks gic, ia55_clk, dmac_aclk (`r9a07g044-cpg.c:435-439`) | CLK_ON `0x514`, `0x518`, `0x52C` | `0x1`, `0x3`, 0 | `0x1`, `0x3`, 0 |

The direct-mode overlay is the 23 words where the EVK differs from Table 7.5. It is taken from the raw dumps of 2026-10-29 (`../../evidence/EVK-2026-10-29-post-firmware.md`). Registers no dump covers (SIPLL5_STBY, PL5_SDIV) start at the manual value (A); G0 never reads them.

## Questions the operator delegated (settled from the manual and the EVK, 2026-10-29)

1. **WDT CLK_MON bits 7:6.** The manual gives CLK_MON_WDT a reset value of `0xC3`, with bits 7:6 reserved as 1 (Table 7.5 p.248, §7.2.4.83). The EVK reads CLK_ON `0xFF` and CLK_MON `0x3F` (R16, X01). Silicon is the authority for behaviour, so the model reads them as 0. Elsewhere the monitor keeps the manual's reserved 1s, because the EVK confirms them there: CLK_MON_MBUS reads `0x7FF`, as the manual says. **Conflict recorded:** in firmware mode the model's CLK_MON_WDT reads `0x03`, not the Table's `0xC3`.
2. **PL1_DDIV reset value.** Table 7.5 p.246 writes `H'0000 000x`. The bit table in §7.2.4.16 p.274 gives 00b, and the EVK reads 0 (R11). Settled: 0.
3. **Direct-mode values the dumps do not cover.** All CLK_ON, CLK_MON, RST, RSTMON and MSTOP words are covered. SIPLL5_STBY and PL5_SDIV are not; they take the manual value, labelled (A).
4. **Correction to the EVK record.** X01/X02 say that holes read 0. That is wrong for 60 words. The CLK_ON/CLK_MON and RST/RSTMON ranges hold live registers at offsets Table 7.5 does not list: `0x510`, `0x530`, `0x59C-0x5F0`, `0x824` = `0x1FFF`, `0x830`, `0x89C-0x8F0`, and their monitors (O). No G0 path touches them; the driver tables use only listed offsets. **Design choice listed for the operator:** they are a bus error in the model, not read-as-zero, because a zero would be silently wrong where silicon reads non-zero.

## Exit criterion

The G0 kernel with DTB-U no longer aborts in the CPG. The `-d` log has no access to `0x1101xxxx`. The boot then stops at a block that needs a model of its own (OSTM, PFC, IRQC or sh-sci). Windows touched before that point are mapped with their device-map class. The qtests assert the manual and EVK values above, and each one is seen red on a plausible mutation (`tasks.md`).

From the repository root, with the project's QEMU (a distribution `qemu-system-aarch64` has no `rzv2l-smarc` machine; QEMU 8.x also lacks the `invalid_mem` mask and prints the `-d` help instead):

```
build/qemu/qemu-system-aarch64 -M rzv2l-smarc \
    -kernel tests/guests/out/g0/linux/arch/arm64/boot/Image \
    -dtb tests/guests/out/g0/r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon" \
    -display none -nodefaults -chardev file,id=scif0,path=build/serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D build/qemu.log
```

The terminal stays empty; see `../../learning/building-and-testing.md` §8 for the output files and a live-console variant. `Image` and the DTB come from `tests/guests/g0/build-kernel.sh` and `build-dtb.sh`. Add `keep_bootcon` to see past the console handover; it is for diagnosis only, as in M2. After the panic QEMU keeps running: stop it with Ctrl-C.

## Evidence

`../../research/cpg-reset.md` §2, §5, §7 and its EVK results; EVK rows R10-R19, R72, X01, X02 and the raw `md.l` dumps; HW manual Rev 1.50 Table 7.5 and §7.2.4.1-209 (masks extracted from every bit table and cross-checked against Table 7.5); `../M2-first-character/first-blocker.md`.

## Next blocker (2026-10-29, fork `4ae1d307eb`)

```
[    2.108378] Internal error: synchronous external abort: 0000000096000010 [#1] PREEMPT SMP
[    2.158650] pc : ostm_timer_stop+0x8/0x60
[    2.164525] lr : ostm_init+0x1a0/0x278
```

- **Guest code:** linux v6.12.59 `drivers/clocksource/renesas-ostm.c`. `ostm_timer_stop` reads the 8-bit OSTM_TE register (`+0x010`, :34) of OSTM1 at `0x12801400`, the first OSTM register access after `ostm_init` takes the clock and releases the reset through the CPG.
- **Model:** the OSTM window is unmapped. The read takes a synchronous external abort: an honest fault.
- **Layer verified:** the `-d` log's only unmapped access is `Invalid read at addr 0x12801410, size 1`, which matches the PC and DFSC `0x10`. The CPG part of the probe (RST_GTM `0x834` write, RSTMON_GTM `0x9B4` = `0x4`; CLKON_GTM `0x534` write, CLKMON_GTM `0x6B4` = `0x2`) completed first, as the trace shows. The cause is the missing OSTM model, the next M3b unit.
- **Seen with every window read-as-zero ([EXP-002](../../experiments/EXP-002-read-as-zero-survey.md), diagnostic build, not committed):** OSTM1 becomes `sched_clock` at 100 MHz and time stops at 2.133 s, because the counter reads 0. The kernel then reaches PFC, ravb, USB host and SDHI, and ends at "No working init found". OSTM must be FUNCTIONAL, as the device map says.

### Coverage list (`-d unimp,guest_errors,invalid_mem`, acceptance and diagnostic runs)

| Log lines | Window (device map) | Class | Status |
|---|---|---|---|
| `rz-dmac: unimplemented device write` × 18 (CHCTRL of channels 0-15, DCTRL of both groups) | DMAC `0x11820000` | write-retaining STUB | mapped this unit |
| `usbphy-ctrl: unimplemented device read/write` at `+0x0` | USB PHY control `0x11C40000` | UNIMP | mapped this unit |
| `tsu: unimplemented device read/write` × 15; guest prints `Failed to start TSU`, probe -110 | TSU `0x10059400` | UNIMP (honest bounded failure, as the device map predicts) | mapped this unit |
| `Invalid read at addr 0x12801410, size 1` | OSTM1 `0x12801400` | FUNCTIONAL, needs a model | next unit |

No CPG line appears: every CPG access the kernel makes is to a modelled register.

### Listed for the operator (classes not changed here)

- **CPG offsets Table 7.5 does not list** (question 4 above) answer with a bus error, while silicon reads live values at 60 of them. No guest touches them yet.
- **DMAC:** the stub keeps written values with a reset to 0. That is the device map's class; at probe the driver only writes, so read-as-zero would behave the same until a client starts a transfer.
