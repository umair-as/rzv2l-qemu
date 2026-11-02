# EVK 2026-11-02: Linux's OP-TEE driver on the board

**Board:** RZ/V2L SMARC EVK, console on SCIF0 (115200 8N1).

**Image:** EDGE AI OS 0.1.0, the image of [`EVK-2026-11-01-firmware.md`](EVK-2026-11-01-firmware.md) (a G2 image: a product built on the Renesas BSP, whose kernel enables `CONFIG_TEE`/`CONFIG_OPTEE` and whose U-Boot adds `/firmware/optee` to the kernel's device tree).

**Method:** the operator typed the commands at the Linux root shell; the output was copied from the console. Stage: post-Linux.

**Question:** what Linux shows when it reaches OP-TEE on the board: the reference for the QEMU TEE acceptance (REQ-TEE-001).

```
root@edge-rzv2l:~# ls /dev/tee*
/dev/tee0  /dev/teepriv0
root@edge-rzv2l:~# dmesg | grep -i tee
[    0.707573] optee: probing for conduit method.
[    0.707728] optee: revision 4.8 (82a5cd3b26ed319e)
[    0.724352] optee: dynamic shared memory is enabled
[    0.725641] optee: initialized driver
```

**Reading (O):** the board's OP-TEE is commit `82a5cd3b` (the one QEMU runs), revision 4.8; the driver uses dynamic shared memory, so no reserved shared-memory region is needed in the device tree. A trusted-application call was not made on the board.
