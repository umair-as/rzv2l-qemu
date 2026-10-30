# M4-loader-fixups — tasks

Fork branch `unit/M4-loader-fixups` from `rzv2l-dev` `aa1764973d`; project branch of the same name from `main`.

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | List the vendor U-Boot's kernel-DT edits and their conditions (`renesas-u-boot-cip` `4eebfbaa4e`) | `spec.md` | source read | done |
| T2 | eSD mode: SD0 `vmmc-supply`/`vqmmc-supply` to the SD0 regulators, as U-Boot's `update_fdt()` (missing regulator keeps the value; a phandle is generated if needed) | fork `hw/arm/rzv2l-smarc.c` | `loader-fixups.sh` | done |
| T3 | Check on the DTB handed to the kernel (`-machine dumpdtb`), G0 and G1, eSD and eMMC; part of M4 acceptance | `tests/acceptance/m4/loader-fixups.sh`, `run.sh` | LOADER FIXUPS: PASS | done |
| T4 | Device map gap 8 and the boot-chain contract table: each edit applied or listed | `docs/device-map.md`, `docs/research/boot-chain-firmware.md` | lint | done |

## Proofs (each mutation: the exact change → the red line)

| # | Mutation | Red line |
|---|---|---|
| 1 | the edit is made in every boot mode (`if (true)`) | `loader-fixups.sh`: `FAIL g1 eMMC vqmmc-supply: 74, expected 18` |
| 2 | no `modify_dtb` hook | `loader-fixups.sh`: `FAIL g1 eSD vqmmc-supply: 18, expected 74` |
| 3 | a fixed phandle `0x8000` instead of `fdt_generate_phandle()` | `loader-fixups.sh`: `FAIL g1 eSD new phandle: 8000, expected 77` |

Each mutation was built with a confirmed relink and run alone; the source was restored and rebuilt, and the check passed again.
