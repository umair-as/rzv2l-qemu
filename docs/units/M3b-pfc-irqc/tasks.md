# M3b-pfc-irqc — tasks

Fork branch `unit/M3b-pfc-irqc` from `rzv2l-dev` `2696c12ddf`; project branch of the same name from `main` `ae47943`.

| ID | Task | Fork commit | Test | Status |
|---|---|---|---|---|
| T1 | IRQC register file (Table 8.3), clear-only status, bus error elsewhere | `23d2b22d1c` | qtest `/irqc/registers`; probe | done |
| T2 | PFC register file (592 registers from the extracted map), PWPR gate, byte-wise access with undefined bytes read as 0, PIN, post-firmware values | `eb794cac5f` | qtest `/pfc/*` | done |
| T3 | SoC: PFC at `0x11030000`, IRQC at `0x110A0000`, `pfc-direct-boot` with `-kernel`; M1 expectations | `6ff2b2bc18` | M1 and M2 acceptance PASS | done |
| T4 | Windows the boot touches next, mapped by their device-map class (UNIMP): ETH0/1, RIIC0/1/3, USB0/1 host, SDHI0/1 | `37266f2c52` | coverage list in `spec.md` | done |
| T5 | qtest for both blocks | `7cdc8ea6a8` | 5/5 green | done |
| T6 | Hello probe: an IRQC read at an unlisted offset must fault | project | probe PASS | done |
| T7 | Boot loop to the next blocker (no root file system: the shell unit) | — | boot logs below | done |
| T8 | Review response: OS timer probe checks get lower bounds (the rewritten match no earlier than 10 ms, the n-th interval interrupt no earlier than n periods) and count only OS timer interrupts (a spurious IRQ had been counted); 50 interval interrupts within 250 periods; PFC assumptions labelled (undefined-byte writes, byte split, PIN) | fork comments only | probe PASS; proofs 10-13 | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `pfc_write_reg`: drop the PWPR.PFCWE gate on PFC registers | `rzv2l-pfc-irqc-test.c:119 test_pfc_pwpr`: `0x11111 == 0x0` |
| 2 | `pfc_write_reg`: PFCWE writable while B0WI is 1 | `rzv2l-pfc-irqc-test.c:125`: `PWPR 0xc0 == 0x80` |
| 3 | `pfc_write_reg`: `m = r->mask & bytes` → `m = bytes` (implemented bits ignored) | `rzv2l-pfc-irqc-test.c:133`: `0xffffffff == 0x77777` |
| 4 | `pfc_pin_value`: PIN follows Pn for any non-zero PMn | `rzv2l-pfc-irqc-test.c:162 test_pfc_port`: `0x7 == 0x5` |
| 5 | table: IOLH06 reset `0x20202` → `0x10101` (group B pins as group A) | `rzv2l-pfc-irqc-test.c:70 test_pfc_reset`: `0x10101 == 0x20202` |
| 6 | overlay: PFC36 `0x11` → `0x01` | `rzv2l-pfc-irqc-test.c:91 test_pfc_direct_boot`: `0x1 == 0x11` |
| 7 | `irqc_write`: status registers store the written value | `rzv2l-pfc-irqc-test.c:209 test_irqc`: `NSCR 0xffffffff == 0x0` |
| 8 | table: IITSR writable mask `0xffff` → `0xffffffff` | `rzv2l-pfc-irqc-test.c:201`: `0xffffffff == 0xffff` |
| 9 | `irqc_read`: an unlisted offset reads 0 instead of a bus error | hello probe: `FAIL IRQC +0x08 (unlisted): read completed without an abort` |
| 10 | `pfc_read`: an undefined byte reads `0xff` instead of 0 | `rzv2l-pfc-irqc-test.c:179 test_pfc_port`: `0xffffffff == 0x00000000` |
| 11 | `renesas_rz_ostm.c`: every `(uint64_t)s->reload + 1` → `((uint64_t)s->reload + 1) * 20` (interval period 20 ms) | hello probe: `FAIL OSTM2 interval IRQs within 250 periods >= 50` |
| 12 | as 11, `/ 2` (interval period 0.5 ms) | hello probe: `FAIL generic timer ticks to the n-th IRQ >= n periods` |
| 13 | `ostm_freerun_arm`: `m -= 900000` when `cmp > 200000` (rewritten match 9 ms early) | hello probe: `FAIL generic timer ticks to the rewritten match >= 10 ms` |

Each mutation was built with a confirmed relink and run alone; the model was restored and the full test passed after each. Proof 5 was re-run after the table was reformatted for checkpatch. Proofs 11-12 change the period in all five places: changing only the first `timer_mod` delays the first interrupt by 19 ms and stays green, because each interval starts from the previous deadline.

## Boot evidence (2026-10-29, fork `7cdc8ea6a8`)

```
build/qemu/qemu-system-aarch64 -M rzv2l-smarc \
    -kernel tests/guests/out/g0/linux/arch/arm64/boot/Image \
    -dtb tests/guests/out/g0/r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon" \
    -display none -nodefaults -chardev file,id=scif0,path=build/serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D build/qemu.log
```

`pinctrl-rzg2l 11030000.pinctrl: pinctrl-rzg2l support registered`, then `printk: legacy console [ttySC0] enabled`: the real serial driver takes over the console, and the boot runs to `No working init found` (`spec.md`, "Next blocker").
