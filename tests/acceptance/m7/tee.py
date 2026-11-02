#!/usr/bin/env python3
"""M7 acceptance for rzv2l-smarc: Linux reaches OP-TEE (REQ-TEE-001/002).

Usage: tee.py OUTDIR

The vendor chain after BL2 as in bootloader.py (BL31, OP-TEE with
CFG_RZ_SCE=n, U-Boot), with the project's TEE kernel on the card
(tests/guests/out/sd/sd-tee.img, DR-0006): the vendor kernel source with
CONFIG_TEE/CONFIG_OPTEE and the vendor DTB with a /firmware/optee node,
plus tee-supplicant and the hello_world client and trusted application
from the OP-TEE 4.8.0 releases. Checks, on the serial line:
  boot:  as bootloader.py's boot 1 (banners, U-Boot's load, PSCI with
         OP-TEE, the shell, both CPUs), with the TEE kernel
  driver: the OP-TEE driver probes ("optee: initialized driver") and
         reports OP-TEE 82a5cd3b, as the board does (EVK-2026-11-02)
  devices: /dev/tee0 and /dev/teepriv0 are character devices
  supplicant: tee-supplicant runs
  trusted application: optee_example_hello_world opens a session with the
         hello_world TA, which tee-supplicant loads from /lib/optee_armtz,
         and invokes it: the TA logs the value it got and the client
         prints the incremented value; exit status 0
Then a separate report (REQ-TEE-002) of what this OP-TEE build lacks,
printed as NOTE lines, not checks. Writes OUTDIR/serial.log and qemu.log.
Exit 0 only if every check passes. QEMU binary: $QEMU.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bootloader  # noqa: E402
import firmware  # noqa: E402
from firmware import check, run  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "guests", "out")
bootloader.KERNEL = os.path.join(OUT, "g1-tee", "linux", "arch", "arm64",
                                 "boot", "Image")
bootloader.IMAGE = os.path.join(OUT, "sd", "sd-tee.img")


def tee_checks(s):
    log = run(s, "dmesg | grep optee:") or ""
    check("optee: initialized driver" in log and
          "optee: revision 4.8 (82a5cd3b" in log,
          "driver: the OP-TEE driver probes; OP-TEE 4.8 (82a5cd3b)")
    out = run(s, "for d in /dev/tee0 /dev/teepriv0; do [ -c $d ] && "
                 "echo chr:$d; done") or ""
    check("chr:/dev/tee0" in out and "chr:/dev/teepriv0" in out,
          "devices: /dev/tee0 and /dev/teepriv0")
    out = run(s, "tee-supplicant -d; sleep 1; pidof tee-supplicant") or ""
    check(re.search(r"^\d+\r?$", out, re.M) is not None,
          "supplicant: tee-supplicant runs")
    pos = len(s.buf)
    out = run(s, "optee_example_hello_world; echo status=$?", 60) or ""
    check("TA incremented value to 43" in out and "status=0" in out and
          "I/TA: Got value: 42 from NW" in s.buf[pos:],
          "trusted application: hello_world TA invoked, 42 -> 43, status 0")

    # REQ-TEE-002: reported, not checked
    tee_bus = (run(s, "ls /sys/bus/tee/devices/ | wc -l") or "").split()
    print("NOTE unsupported: hardware crypto (TSIP; OP-TEE built "
          "CFG_RZ_SCE=n): trusted applications get OP-TEE's software crypto")
    print("NOTE unsupported: hardware RNG (CFG_HWRNG_PTA=n, software PRNG): "
          "no RNG service on Linux's TEE bus (%s device(s) listed)"
          % next((w for w in tee_bus if w.isdigit()), "?"))
    rollback = "Failed to get monotonic counter for REE FS" in s.buf[pos:]
    print("NOTE unsupported: RPMB (CFG_RPMB_FS=n): secure storage in the "
          "REE file system without a rollback counter%s"
          % (" (OP-TEE warns: Failed to get monotonic counter for REE FS)"
             if rollback else ""))


def main():
    out = sys.argv[1]
    proc, s, log = bootloader.start(out)
    try:
        if bootloader.boot_checks(s, 0, 1):
            run(s, "watchdog -T 10 -t 2 /dev/watchdog0")
            tee_checks(s)
    finally:
        bootloader.stop(proc, log)
    return 1 if firmware.failures else 0


if __name__ == "__main__":
    sys.exit(main())
