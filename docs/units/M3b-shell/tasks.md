# M3b-shell — tasks

Project branch `unit/M3b-shell` from `main` `98c3970`. No fork change: the machine is `rzv2l-dev` `01168f7f3e`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | G0 initramfs: static BusyBox 1.36.1 (pinned SHA-256), `/init` with a ready line, a shell on the console | `tests/guests/g0/build-initramfs.sh` | boot: `G0-INIT: ready` | done |
| T2 | M3 acceptance: M2 (and M1), two cold boots, a shell session on SCIF0 over a socket, the log gate | `tests/acceptance/m3/` | M3 ACCEPTANCE: PASS | done |
| T3 | Boot with the DTB's own bootargs, no `-append`; gap list: generic timer rate (gap 18) | `docs/device-map.md` §4 | kernel command line in the serial log | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | `r9a07g054_mp_affinity`: CPU 1 `0x100` → `0x1` (Aff0 instead of Aff1; PSCI `CPU_ON` for `cpu@100` finds no core) | `shell.py`: `FAIL both CPUs online: /sys/devices/system/cpu/online = 0` |
| 2 | `rz_scifa_receive`: drop each received byte | `shell.py`: `FAIL the shell answers a per-run command` |
| 3 | run with `-icount shift=0,sleep=off` (guest time no longer follows host time) | `shell.py`: `FAIL guest time / host time = 18.890 over sleep 3` |
| 4 | log gate: remove the `^sdhi[01]` allow line | `run.sh` log gate: 55 kinds of line outside the allow list |

Proofs 1-2 were built with a confirmed relink, run alone, restored and rebuilt. Proof 3 changes only the run arguments, and proof 4 changes only the allow list. The first draft of `shell.py` matched the CPU line before its last characters arrived and read `0`; the pattern now needs the line end.

## Boot evidence (2026-10-30, fork `01168f7f3e`)

```
build/qemu/qemu-system-aarch64 -M rzv2l-smarc \
    -kernel tests/guests/out/g0/linux/arch/arm64/boot/Image \
    -dtb tests/guests/out/g0/r9a07g054l2-smarc.dtb \
    -initrd tests/guests/out/g0/initramfs.cpio.gz \
    -display none -nodefaults -serial mon:stdio \
    -d unimp,guest_errors,invalid_mem -D build/qemu.log
```

`Kernel command line: ignore_loglevel rw root=/dev/nfs ip=on`, `legacy console [ttySC0] enabled` at 1.1 s, `Run /init as init process` at 18 s, `G0-INIT: ready, cpus online 0-1`, then the `~ #` prompt. M3 acceptance: PASS (both cold boots).
