# EXP-002: which windows the G0 kernel touches after the CPG

Date: 2026-10-29. Status: complete. Unit: M3b-cpg.

## Question

With the CPG modelled, which peripheral windows does the G0 kernel touch, and in which order, before it reaches a block that needs a model of its own? The answer decides which windows the unit maps (by their device-map class) and where it stops.

## Setup

- Fork at the CPG model, before the stubs (`c3e83bbbd2` plus OTHERFUNC1/2, uncommitted at the time).
- One diagnostic change in `hw/arm/r9a07g054.c`, never committed: a catch-all `unimplemented-device` over the whole peripheral space, below every real device.

```c
/* SURVEY ONLY, not for commit */
create_unimplemented_device("survey", 0x10000000, 0x04000000);
```

- Guest: the G0 kernel and DTB-U of `../units/M2-first-character/first-blocker.md`, unmodified.

```
qemu-system-aarch64 -M rzv2l-smarc -kernel Image -dtb r9a07g054l2-smarc.dtb \
    -append "ignore_loglevel rw root=/dev/nfs ip=on earlycon keep_bootcon" \
    -display none -nodefaults -chardev file,id=scif0,path=serial.log -serial chardev:scif0 \
    -d unimp,guest_errors,invalid_mem -D qemu.log
```

## Result (observation of the model, not of silicon)

First access to each 4 KiB window, in log order:

| Order | Window | Block (device map) | First access |
|---|---|---|---|
| 1 | `0x11820000` | DMAC | write `+0x028` (channel 0 CHCTRL) |
| 2 | `0x11C40000` | USB PHY control | read `+0x000` |
| 3 | `0x10059000` | TSU (`0x10059400`) | read `+0x418` |
| 4 | `0x12801000` | OSTM1 (`0x12801400`) | 1-byte read `+0x410` (TE) |
| 5 | `0x11031000`, `0x11030000`, `0x11033000` | PFC | reads, then PWPR write |
| 6 | `0x11C20000`, `0x11C30000` | ravb ETH0, ETH1 | reads |
| 7 | `0x11C50000`, `0x10058000`, `0x11C70000` | USB host, RIIC, USB host 1 | reads, writes |
| 8 | `0x11C00000`, `0x11C10000` | SDHI0, SDHI1 | 16-bit reads `+0x388` |

- With every window read as zero, OSTM1 became `sched_clock` at 100 MHz (`sched_clock: 32 bits at 100MHz`). Its counter read 0, so the kernel time stayed at 2.133064 s for the rest of the boot.
- TSU printed `Failed to start TSU` and its probe returned -110, the bounded failure the device map predicts.
- The boot ended at `Kernel panic - not syncing: No working init found` (no initramfs).

## Conclusion

The unit maps the three windows before OSTM by their device-map class (DMAC write-retaining, USB PHY control and TSU read-as-zero) and stops at OSTM1. A read-as-zero OSTM would be silently wrong: it stops time. This confirms the device map's FUNCTIONAL class for OSTM.
