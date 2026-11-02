# M7-optee-linux — spec

**Milestone:** M7 (real firmware; third unit). **Requirements:** REQ-TEE-001, REQ-TEE-002 (proposed); the REQ-GUEST-001 exception of [DR-0006](../../decisions/DR-0006-linux-optee-access-in-m7.md). **Status:** implemented. M7 is complete only with this unit.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A).

## Scope

**Linux reaches OP-TEE on the M7 boot chain, and a user-space client calls a trusted application.** The chain is [M7-optee-uboot](../M7-optee-uboot/spec.md)'s, unchanged: the vendor TF-A BL31, OP-TEE `82a5cd3b` (`CFG_RZ_SCE=n`) and U-Boot `4eebfbaa4e`, with QEMU in BL2's place. Only the card changes: it carries the project's TEE kernel and the OP-TEE user space. The vendor run (stock kernel and DTB) stays in the acceptance as the regression baseline.

- **Why the vendor kernel cannot:** its `defconfig` leaves `CONFIG_TEE` unset, and no device tree Linux receives has `/firmware/optee` (M7-optee-uboot spec, "What Linux sees of OP-TEE").
- **The project's TEE kernel** (`tests/guests/g1-tee/build-kernel.sh`): the vendor source at `212f6e88b7`, unchanged; the vendor `defconfig` plus `tee.config` (`CONFIG_TEE=y`, `CONFIG_OPTEE=y`, merged with the kernel's `merge_config.sh`); the vendor DTB with `optee.dtso` applied by `fdtoverlay`: `/firmware/optee`, `compatible = "linaro,optee-tz"`, `method = "smc"`. No `reserved-memory`: OP-TEE uses dynamic shared memory (its banner and the board's `optee: dynamic shared memory is enabled`, EVK-2026-11-02) and its memory lies below Linux's `0x48000000`.
- **DT integration, the two routes.** This unit puts the node in the kernel's device tree, the route of Renesas's own 5.10 kernels (`r9a07g054.dtsi` carried the node disabled; the RZ/V2L Security Package v3.2.0.0 enabled it), so the vendor U-Boot stays unmodified. The board's product image puts the node in U-Boot's device tree instead (edge-ai-yocto `0004-smarc-rzv2l-dts-add-optee-firmware-node-for-rng.patch`), and the vendor U-Boot's `optee_copy_fdt_nodes()` copies it into the kernel's at `booti` (`lib/optee/optee.c:112-140`, enabled by `CONFIG_OPTEE_LIB=y` in the effective `.config`); that route also lets U-Boot's own OP-TEE drivers bind. Both give Linux the same node. edge-ai-yocto is a reference here, not a build dependency.
- **User space** (`tests/guests/g1-tee/build-optee-user.sh`): `optee_client` 4.8.0 (`9d6f69844f`): `libteec` and `tee-supplicant`, static, TAs looked up in `/lib/optee_armtz`, secure storage in `/var/lib/tee`; `optee_examples` 4.8.0 (`3ef17eb1f3`) `hello_world`: its client, static, and its TA, built with the TA dev kit of the project's OP-TEE build and signed with OP-TEE's public development key (an emulation test, not a product key). The releases match OP-TEE 4.8.
- **The card** (`tests/guests/sd/build-image.sh --tee`, `sd-tee.img`): the M5 root file system plus the above.
- **Unsupported, reported separately (REQ-TEE-002):** hardware crypto (TSIP, closed; OP-TEE built `CFG_RZ_SCE=n`, so TAs get OP-TEE's software crypto); a hardware RNG service (`CFG_HWRNG_PTA=n`, software PRNG: Linux's TEE bus lists no devices); RPMB (`CFG_RPMB_FS=n`: secure storage lives in the REE file system without a rollback counter, and OP-TEE warns `Failed to get monotonic counter for REE FS`).
- **Not in this unit:** `xtest` (the OP-TEE test suite); the product's random-seed path (`kaslr-seed` through U-Boot's OP-TEE RNG, needs TSIP); a production TA key.

## Exit criterion

`tests/acceptance/m7/tee.py`, inside `tests/acceptance/m7/run.sh`: the boot checks of the M7 chain with the TEE kernel; `optee: initialized driver` and `optee: revision 4.8 (82a5cd3b`, as on the board (EVK-2026-11-02); `/dev/tee0` and `/dev/teepriv0` character devices; `tee-supplicant` running; `optee_example_hello_world` invoking the TA (`I/TA: Got value: 42 from NW`, `TA incremented value to 43`, status 0); the three NOTE lines of REQ-TEE-002; its QEMU log inside the M7 log gate. The vendor runs of M7-el3-platform and M7-optee-uboot pass unchanged.

## Evidence

- Board: [EVK-2026-11-02-optee-driver](../../evidence/EVK-2026-11-02-optee-driver.md) (the driver's lines; no TA call was made on the board).
- Sources: OP-TEE `82a5cd3b` effective `conf.mk` (`CFG_RZ_SCE=n`, `CFG_HWRNG_PTA=n`, `CFG_RPMB_FS=n`, `CFG_REE_FS=y`, `CFG_CORE_DYN_SHM=y`); the TEE kernel's effective `.config` (`CONFIG_TEE=y`, `CONFIG_OPTEE=y`).
