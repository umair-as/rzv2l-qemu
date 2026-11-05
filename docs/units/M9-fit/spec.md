# M9-fit — spec

**Milestone:** M9 (platform behaviour; first unit). **Requirements:** REQ-BOOT-001, REQ-BOOT-002 (proposed here), REQ-GUEST-003 (second exception, DR-0008). Statuses change at release closure. **Status:** written; implementation follows.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The profile, the slot state and the boot-attempt contract are [DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md); this unit builds decisions 1-4 and the U-Boot half of decision 6. U-Boot paths are at `renesas-u-boot-cip` `4eebfbaa4e`.

## Scope

**No new block, and no QEMU change expected.** The whole chain runs from the QSPI flash as in M8, with the M9 U-Boot in the FIP in place of the vendor-default build. If a check exposes a model gap, the fix is a new task with its qtest, its mutation and a review build.

- **M9 U-Boot** (`tests/guests/fw/build-u-boot-m9.sh`): the pinned source, `smarc-rzv2l_defconfig`, then the fragment `u-boot-m9.cfg` (DR-0008 decision 1). The effective `.config` is kept beside the binary, and the build fails if an option of the fragment is missing from it.
- **Key and trust anchor:** `tests/guests/fw/m9-key.sh` makes one RSA-2048 key the first time, under `tests/guests/out/m9/keys/` (untracked), and later runs reuse it. The public key goes into U-Boot's control DTB with `required = "conf"`. The vendor build uses `CONFIG_MULTI_DTB_FIT` (F, `.config`): its control DTBs are a FIT of two, `smarc-rzv2l` and `smarc-rzv2l-ecc`. U-Boot picks one by the ECC bit (`board/renesas/rzv2l-dev/rzv2l-dev.c` `board_fit_config_name_match`), so the key goes into both. A check reads the key node back from each DTB in the built binary.
- **The FIT** (`tests/guests/fw/build-fit-m9.sh`): the vendor kernel `Image`, the vendor DTB unmodified, one configuration `conf`, with hashes `sha256` and a configuration signature `sha256,rsa2048` that covers `kernel` and `fdt`. No initramfs.
- **Flash and card:** a flash image `spi-m9.img`, as M8's but with the M9 U-Boot as BL33. A card `sd-m9.img` with DR-0008's layout: partition 1 data from `0x400000`; partition 2 slot A's root, with the FIT in `/boot`; partition 3 slot B's. Both environment copies hold the M9 policy. The card builder asserts the bounds `0x1F0000`-`0x20FFFF`, `0x210000`-`0x22FFFF` and partition 1 at `0x400000`.
- **The automatic boot route** (DR-0008 decision 6): select a slot, decrement and save its counter before the attempt, `bootm` its FIT, reset if `bootm` returns, and stop at the prompt with the slots and counters printed when no attempt is left. This unit tests it on slot A only. M9-ab adds slot B, the health service and rollback.
- **Not in this unit:** slot B, Linux's commit, updates and interruptions (M9-ab, M9-update-failure); dm-verity; anti-rollback.

## Open choice (operator)

**A FIT-signature fix that the pinned source lacks.** Upstream U-Boot commit `2092322b31cc` ("boot: Add fit_config_get_hash_list() to build signed node list") changes `fit_config_check_sig()`: it builds the list of signed nodes from the configuration's own image references and no longer reads the `hashed-nodes` property. It names a FIT crafted so that the signature covers a decoy node, not the image that boots. The G2 sample carries it as a CVE backport (a lead; the commit header is its source, not checked against upstream yet). The pinned `4eebfbaa4e` (2024.07) predates it (I). Two options:

- **(a) Pinned source as it is.** The project's own negative cases (below) do not use that attack, so they test the pinned code honestly. The weakness is recorded as a known gap of the M9 profile, and a crafted-FIT case may show it being accepted.
- **(b) Backport the upstream commit** as a listed source change of the M9 profile (one patch, its upstream hash and the reason), and add the crafted-FIT case as a negative check that must be refused.

Recommendation: (b). A profile that demonstrates signature enforcement should not carry a known way around it. The patch is a public upstream fix, not a QEMU-specific change. Until you choose, the implementation starts with (a) and leaves the crafted case out.

## What the guest needs

1. **U-Boot verifies the configuration** (`boot/image-fit-sig.c` `fit_config_verify`, called from `boot/image-fit.c` `fit_image_load` when `CONFIG_FIT_SIGNATURE` is set). It checks every key node that is marked `required = "conf"`. A configuration without a valid signature by that key is refused before any image loads.
2. **U-Boot checks each image's hash** when it loads the image (`fit_image_verify`), so a changed kernel or DTB fails even under a valid configuration signature.
3. **The environment** is read from the two copies at `0x1F0000` and `0x210000` (`env/mmc.c` with `CONFIG_SYS_REDUNDAND_ENVIRONMENT`).

The exact function and line citations are filled in from the source during T2, and the messages are checked against the source, not copied from elsewhere.

## Exit criterion

New acceptance script `tests/acceptance/m9/fit.py`. It runs from the QSPI flash, boot mode 3, with no `-bios`, `-kernel`, `bl32=` or `bl33=`, and uses a fresh copy of each image for each case.

1. **Accepted:** U-Boot prints the FIT's configuration check as passed for the project key (`sha256,rsa2048:<key name>+`) and each image's hash as OK, then starts the kernel. Linux reaches the shell with `/` on slot A's PARTUUID. `BOOT_A_LEFT` went from 3 to 2 and was saved before `bootm` (the order of the lines shows it).
2. **Rejected, each before kernel entry**, with `Starting kernel` never printed. In each case U-Boot prints its reason, resets, and tries again until the counter is 0. It then stops at the prompt and prints the slot and its counter. Nothing boots by another route. The cases:
   - a kernel byte changed after signing (the image hash fails);
   - the DTB in the FIT replaced with a different DTB, the configuration signature left as it was (the image hash fails);
   - a FIT with no configuration signature (the required key finds none);
   - a FIT signed with a second key (the required key does not verify it);
   - with option (b) only: the crafted FIT whose signature covers a decoy node.
3. **Trust anchor:** each run records the SHA-256 of the public key, of each control DTB that carries it, of each FIT, and of the flash and card images it used. Every negative case uses the same U-Boot binary and key as the accepted case, and the hashes show it.
4. **Profiles side by side:** M8 acceptance (the vendor-default profile) runs unchanged.
5. **Log gate:** the `-d unimp,guest_errors,invalid_mem` lines of each run are those of M8's chain list, or new lines checked at their source.

## Evidence

[DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md); spec §8 (v0.4), §12; `tests/guests/out/fw/u-boot.config` (the vendor build's effective configuration); `../../evidence/EVK-2026-10-29-post-firmware.md` (the board's product image enables a redundant environment, FIT signatures and bootcount: G2, a sample); U-Boot `doc/usage/fit/signature.rst` at the pinned commit.

## Next blocker

Written at the end.
