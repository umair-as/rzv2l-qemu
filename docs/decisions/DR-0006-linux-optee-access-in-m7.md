# DR-0006: Linux reaches OP-TEE in M7, through a project-owned kernel build

**Status:** accepted by the operator, 2026-11-02.

## Context

M7 runs the board's chain after BL2: TF-A BL31, OP-TEE (`CFG_RZ_SCE=n`) and U-Boot, all vendor builds. OP-TEE runs, but Linux cannot use it, for two reasons on the vendor stack: the vendor kernel's `defconfig` leaves `CONFIG_TEE` unset, and no device tree Linux receives has `/firmware/optee` (the 6.12 vendor kernel dropped the node its 5.10 kernels carried; the vendor U-Boot's device tree never had one). The board's product image (edge-ai-yocto, G2) adds both: `CONFIG_TEE=y`, `CONFIG_OPTEE=y` in a kernel fragment, and the node in U-Boot's device tree, which U-Boot copies into the kernel's at `booti`. On the board its Linux prints `optee: initialized driver` and has `/dev/tee0` ([EVK-2026-11-02](../evidence/EVK-2026-11-02-optee-driver.md)).

## Decision

M7 is complete only when Linux reaches OP-TEE: the OP-TEE driver probes, `/dev/tee0` and `/dev/teepriv0` exist, and a user-space client invokes a trusted application and gets its answer (REQ-TEE-001). Features the emulated OP-TEE build does not have (hardware crypto and RNG, RPMB) are reported separately (REQ-TEE-002).

To get there, the project builds its own TEE-enabled kernel from the vendor source: the vendor `defconfig` plus a project fragment with `CONFIG_TEE=y` and `CONFIG_OPTEE=y`, and the vendor DTB with a `/firmware/optee` node added by an overlay at build time. Both live in this repository; edge-ai-yocto is a reference, not a build dependency. TF-A, OP-TEE and U-Boot stay the vendor builds.

This is an exception to REQ-GUEST-001 (stock DTB) for the TEE acceptance run only, listed as a fidelity gap under REQ-GUEST-004. It is not a driver patch (REQ-GUEST-002 holds: the kernel source is unchanged). The vendor-only run (stock kernel and DTB) stays in the acceptance as the regression baseline.

## Consequences

- A new M7 unit, `M7-optee-linux`; `M7-optee-uboot` stays the vendor baseline.
- The kernel node follows Renesas's own 5.10 route (a kernel device tree node) rather than the product's U-Boot route, so the vendor U-Boot stays unmodified; the product route is documented as the alternative.
- The SD card for the TEE run carries the TEE kernel, its DTB and the OP-TEE client and example from their public 4.8.0 releases.
