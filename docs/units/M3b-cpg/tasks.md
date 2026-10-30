# M3b-cpg — tasks

Fork branch `unit/M3b-cpg` from `rzv2l-dev` `1c74716c64`; project branch of the same name from `main` `95cbd22`.

| ID | Task | Fork commit | Test | Status |
|---|---|---|---|---|
| T1 | CPG model: Table 7.5 register file, per-field write enables, computed CLK_MON/RSTMON, CLKSTATUS 0, `direct-boot` overlay from the EVK dumps; OTHERFUNC1/2 added when the boot read `0xBE8` | `d73770d84c` | `rzv2l-cpg-test` | done |
| T2 | SoC and board: CPG at `0x11010000`, `cpg-direct-boot` set with `-kernel` | `c3e83bbbd2` | M1 and M2 acceptance PASS (M1 mtree/qtree updated from the device map) | done |
| T3 | qtest: reset values, direct-boot values, write enables, monitors, system reset | `90550b42b8` | 5/5 green | done |
| T4 | Windows the boot touches before OSTM, mapped by their device-map class: DMAC (write-retaining stub, through a new `retain-writes` option of the unimplemented device), USB PHY control and TSU (UNIMP; USB PHY control made write-retaining in T6) | `94127a7b5f`, `4ae1d307eb` | `rzv2l-smarc-test` `/stubs` | done |
| T5 | Boot loop to the next blocker; next blocker recorded in `spec.md` | — | boot logs below | done |
| T6 | Review response: every post-firmware word asserted, also after a system reset; MSTOP writes; unmodelled CPG reads abort (hello probe, a real CPU: qtest cannot see bus errors); USB PHY control write-retaining (operator decision); doc fixes | see the PR | `rzv2l-cpg-test` 5/5, `rzv2l-smarc-test` 6/6, hello probe PASS; proofs 8-13 | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `cpg_monitor`: `return ~s->regs[idx] & ctl->rw;` → `return s->regs[idx] & ctl->rw;` (RSTMON same polarity as RST) | `rzv2l-cpg-test.c:182 check_values` at offset `0x980`: `0x1fff == 0x0` |
| 2 | `rzv2l_cpg_write`: `mask = cpg_wen_mask(r, data);` → `mask = cpg_wen_mask(r, data) \| r->rw;` (write enables ignored; this form compiles under `--enable-werror`) | `rzv2l-cpg-test.c:225`: `CLKON_SCIF 0x1f == 0` |
| 3 | `cpg_wen_mask`: loop condition `while (0 && …)` (an enable bit gates one bit, not its field) | `rzv2l-cpg-test.c:237`: `PL2_DDIV 0x1 == 0x5` |
| 4 | table: `CPG_MON(0x6c8, CLKMON_WDT, 0x0)` → `0xc0` (reserved bits as Table 7.5, not as silicon) | `rzv2l-cpg-test.c:182` at offset `0x6c8`: `0xc3 == 0x3` |
| 5 | overlay: `{ 0x884, 0x00000001 }` → `0x00000003` (RST_SCIF) | `rzv2l-cpg-test.c:182` at offset `0x884` in `/cpg/direct-boot`: `0x3 == 0x1` |
| 6 | `cpg_monitor`: drop `\| r->reset` (CLK_MON loses its reserved 1s) | `rzv2l-cpg-test.c:182` at offset `0x738`: `0x208 == 0x7ff` |
| 7 | `r9a07g054_unimp`: `rz-dmac` `retain_writes` `true` → `false` | `rzv2l-smarc-test.c:188 test_stubs`: `0x0 == 0x2027a` |
| 8 | overlay: `{ 0x578, 0x0000000f }` → `0x00000007` (CLKON_USB) | `rzv2l-cpg-test.c:182` at offset `0x578` in `/cpg/direct-boot`: `0x7 == 0xf` |
| 9 | overlay: `{ 0x880, 0x0000000f }` → `0x00000007` (RST_I2C) | `rzv2l-cpg-test.c:182` at offset `0x880` in `/cpg/direct-boot`: `0x7 == 0xf` |
| 10 | table: `BUS_MCPU1_MSTOP` rw `0xfff7` → `0xffff` (reserved bit 3 writable) | `rzv2l-cpg-test.c:266`: `MSTOP_MCPU1 0xffff == 0xfff7` |
| 11 | `rzv2l_cpg_reset_hold`: apply the overlay at the first reset only (`static bool applied`) | `rzv2l-cpg-test.c:182` at offset `0x208` after the system reset in `/cpg/direct-boot`: `0x0 == 0x100` |
| 12 | `rzv2l_cpg_read`: an unmodelled offset returns `*data = 0; MEMTX_OK` instead of `MEMTX_DECODE_ERROR` | hello probe: `FAIL CPG +0x510 (unlisted): read completed without an abort` and the same for `+0xb30`; `RESULT: FAIL (2 failures)` |
| 13 | `r9a07g054_unimp`: `usbphy-ctrl` `retain_writes` `true` → `false` | `rzv2l-smarc-test.c:192 test_stubs`: `0x0 == 0x303` |

Each mutation was built with a confirmed relink and run alone; the model was restored and the full test passed after each.

## Boot evidence (fork `4ae1d307eb`)

```
qemu-system-aarch64 -M rzv2l-smarc -kernel Image -dtb r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon keep_bootcon" \
    -display none -nodefaults -chardev file,id=scif0,path=serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D qemu.log
```

`-trace "renesas_rzv2l_cpg_*"` shows the probe sequence: PLL1 `0x1901`/`0x180601`, the dividers and selectors, SIPLL5_STBY `0x50001`, the three critical clocks enabled and seen in CLK_MON, then IA55, DMAC, USB, TSU and GTM resets released and seen as 0 in RSTMON. TSU's error path applies its reset again and RSTMON_TSU reads 1. No `Failed to enable CLK_ON` and no reset timeout appear.
