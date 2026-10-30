# M3b-ostm — tasks

Fork branch `unit/M3b-ostm` from `rzv2l-dev` `f512aba021`; project branch of the same name from `main` `92d6c0f`.

| ID | Task | Fork commit | Test | Status |
|---|---|---|---|---|
| T1 | OS timer model: free-running and interval modes on the virtual clock, TE/TS/TT, CTL rules, per-register access widths, an interrupt pulse per request (held high for interval CMP = 0) | `48f1d05d88` | `rzv2l-ostm-test`, hello probe | done |
| T2 | SoC: OSTM0-2 at `0x12801000` + n × `0x400`, SPI 46-48, count clock 100 MHz; M1 expectations | `a3a43f890c` | M1 and M2 acceptance PASS | done |
| T3 | qtest: reset values, free-running and interval counting, start/stop/forced restart, CTL rules, CMP = 0 level | `afe1e5b71b` | 5/5 green | done |
| T4 | Hello probe: OSTM2 one-shot interrupt on a real CPU (INTID 80, not before CMP + 1 counts, once), wrong-size and unlisted reads fault | project | probe PASS | done |
| T5 | Boot to the next blocker, recorded in `spec.md` | — | boot logs below | done |
| T6 | Review response: probe checks for the interval (periodic) interrupt and the free-running compare rewrite; labels (MD0 reading, bus-error choice); not-modelled list (CPG reset line, two-clock request); manual typo note | fork comment only | probe PASS; proofs 11-12 | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `ostm_count`: return the stored `s->cnt` while running (counter frozen) | `rzv2l-ostm-test.c:84 test_freerun`: `0x0 == 0x64` |
| 2 | `ostm_stop`: drop `s->te = false;` (TT leaves TE set) | `rzv2l-ostm-test.c:92`: `TE 0x1 == 0x0` |
| 3 | `ostm_write`, CTL: `if (s->te)` → `if (0)` (CTL writable while running) | `rzv2l-ostm-test.c:153 test_ctl`: `0x0 == 0x2` |
| 4 | `ostm_write`, CTL: drop the CNT update on a mode change | `rzv2l-ostm-test.c:143 test_ctl`: `0xffffffff == 0x0` |
| 5 | every `(uint64_t)s->reload + 1` → `(uint64_t)s->reload` (interval period CMP, not CMP + 1) | `rzv2l-ostm-test.c:121 test_interval`: `0x1f2 == 0x1f3` |
| 6 | `ostm_write`, TS: `if (!s->te \|\| !ostm_freerun(s))` → `if (!s->te)` (no forced restart in interval mode) | `rzv2l-ostm-test.c:129 test_interval`: `0x1d5 == 0x1f3` |
| 7 | `ostm_interval_load`: drop `ostm_set_level(s, true)` for CMP = 0 | `rzv2l-ostm-test.c:168 test_interval_cmp0`: `qtest_get_irq` should be TRUE |
| 8 | `ostm_start`: request an interrupt at every start (MD0 ignored) | hello probe: `FAIL OSTM2 CNT at IRQ >= CMP + 1` and `FAIL generic timer ticks to IRQ >= 1 ms` |
| 9 | SoC: `R9A07G054_OSTM0_SPI` 46 → 45 (OSTM2 on SPI 47) | hello probe: `FAIL OSTM2 IRQ taken: 0`, `FAIL OSTM2 IRQ INTID: 1023` |
| 10 | `ostm_check_access`: accept a wrong access size | hello probe: `FAIL OSTM2 TE as 32-bit: read completed without an abort` |
| 11 | `ostm_timer_cb`, interval path: drop `ostm_request(s)` (no interval interrupt; found green by the review) | hello probe: `FAIL OSTM2 interval IRQs within 250 periods >= 50` (re-run 2026-10-30 after the probe change in the PFC/IRQC unit) |
| 12 | `ostm_write_cmp`, free-running: drop the `ostm_freerun_arm()` re-arm (Table 20.5 rows c, d; found green by the review) | hello probe: `FAIL OSTM2 IRQ after the rewrite: 0` |

Each mutation was built with a confirmed relink and run alone; the model was restored and the full test passed after each. The first try at proof 5 changed only the counter read and stayed green; the period lives in the reload timer too, so the stated form changes both.

**Not proven by a mutation:** the free-running first interrupt at CMP + 1 rather than CMP counts (one 10 ns count). qtest cannot see a pulse or reach the secure-by-default GIC, and the probe sees the interrupt only after TCG's delivery latency. The probe proves "not before CMP + 1 counts" only to within that latency.

## Boot evidence (2026-10-29, fork `afe1e5b71b`)

```
build/qemu/qemu-system-aarch64 -M rzv2l-smarc \
    -kernel tests/guests/out/g0/linux/arch/arm64/boot/Image \
    -dtb tests/guests/out/g0/r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon keep_bootcon" \
    -display none -nodefaults -chardev file,id=scif0,path=build/serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D build/qemu.log
```

```
[    3.191742] clocksource: timer@12801400: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 19112604467 ns
[    3.206918] sched_clock: 32 bits at 100MHz, resolution 10ns, wraps every 21474836475ns
[    3.219221] /soc/timer@12801400: used for clocksource
[    3.229346] /soc/timer@12801800: used for clock events
```

Kernel time keeps advancing after the switch to the OS timer (3.2 s to 3.8 s in this run; it stopped at 2.133 s in EXP-002).
