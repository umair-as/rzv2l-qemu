# M9-fit — spec

**Milestone:** M9 (platform behaviour; first unit). **Requirements:** REQ-BOOT-001, REQ-BOOT-002 (proposed here), REQ-GUEST-003 (second exception, DR-0008). Statuses change at release closure. **Status:** implemented.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The profile, the slot state and the boot-attempt contract are [DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md); this unit builds decisions 1-4 and the U-Boot half of decision 6. U-Boot paths are at `renesas-u-boot-cip` `4eebfbaa4e`.

## Scope

**No new block, and no QEMU change expected.** The whole chain runs from the QSPI flash as in M8, with the M9 U-Boot in the FIP in place of the vendor-default build. If a check exposes a model gap, the fix is a new task with its qtest, its mutation and a review build.

- **M9 U-Boot** (`tests/guests/fw/build-u-boot-m9.sh`): the pinned source, `smarc-rzv2l_defconfig`, then the fragment `u-boot-m9.cfg` (DR-0008 decision 1). The effective `.config` is kept beside the binary, and the build fails if an option of the fragment is missing from it.
- **Key and trust anchor:** `build-u-boot-m9.sh` makes one RSA-2048 key the first time, under `tests/guests/out/m9/keys/` (untracked), and later runs reuse it. The public key goes into U-Boot's control DTB with `required = "conf"`. The vendor build uses `CONFIG_MULTI_DTB_FIT` (F, `.config`): its control DTBs are a FIT of two, `smarc-rzv2l` and `smarc-rzv2l-ecc`. U-Boot picks one by the ECC bit (`board/renesas/rzv2l-dev/rzv2l-dev.c` `board_fit_config_name_match`), so the key goes into both. A check reads the key node back from each DTB in the built binary.
- **The FIT** (`tests/guests/fw/build-fit-m9.sh`): the vendor kernel `Image`, the vendor DTB unmodified, one configuration `conf`, with hashes `sha256` and a configuration signature `sha256,rsa2048` that covers `kernel` and `fdt`. No initramfs. The same script makes the negative FITs from the signed one and the same key, and the host's `fit_check_sign` (M9 source) must accept the signed FIT and refuse each negative before any boot.
- **Flash and card:** a flash image `spi-m9.img`, as M8's but with the M9 U-Boot as BL33. A card `sd-m9.img` with DR-0008's layout: partition 1 data from `0x400000`; partition 2 slot A's root, with the FIT in `/boot`; partition 3 slot B's. Both environment copies hold the M9 policy. The card builder asserts the bounds `0x1F0000`-`0x20FFFF`, `0x210000`-`0x22FFFF` and partition 1 at `0x400000`.
- **The automatic boot route** (DR-0008 decision 6): select a slot, decrement and save its counter before the attempt, `bootm` its FIT, reset if `bootm` returns, and stop at the prompt with the slots and counters printed when no attempt is left. This unit tests it on slot A only. M9-ab adds slot B, the health service and rollback.
- **Not in this unit:** slot B, Linux's commit, updates and interruptions (M9-ab, M9-update-failure); dm-verity; anti-rollback.

## The FIT-signature backport (operator's choice: backport)

Upstream U-Boot commit `2092322b31cc` ("boot: Add fit_config_get_hash_list() to build signed node list", fetched from upstream by its hash) changes `fit_config_check_sig()`. It builds the list of signed nodes from the configuration's own image references and no longer reads the signature's `hashed-nodes` property, which the signature does not cover (the commit's own `doc/usage/fit/signature.rst`). The pinned `4eebfbaa4e` predates it (F: the patch's context is the old code). The G2 sample carries it as a CVE backport (a lead).

The M9 profile carries it as its one source patch (`tests/guests/fw/patches/u-boot-m9/`): the code and doc hunks, with `FIT_COMPAT_PROP`, which this tree lacks, written as its upstream value `"compatible"`. The hunk for U-Boot's own Python test is dropped, because it does not apply here and is not built.

**What the tests show about it.** One case separates the two codes (found by the independent review): a FIT signed with the profile key whose signature covers only the kernel (`sign-images = "kernel"`), so its DTB could be swapped. The pinned code builds the signed region from the signature's `hashed-nodes` list and accepts it. The patched code builds the list from the configuration, which names the DTB too, and refuses it. `build-fit-m9.sh` checks both with the host `fit_check_sign` of each build, and `fit.py` boots it on the target, where it must be refused. Upstream's two crafted FITs (`test/py/tests/vboot_evil.py`: `fakeroot`, `kernel@`) do not separate them: U-Boot's format check refuses both before any signature check (`boot/image-fit.c:2082-2086`), with or without the patch.

## What the guest needs

1. **U-Boot verifies the configuration.** `fit_image_load` calls `fit_config_verify` while `images->verify` is set (`boot/image-fit.c:2120-2126`). That function checks every key node marked `required = "conf"` (`boot/image-fit-sig.c:607`, `:684`). A configuration without a valid signature by that key is refused, with `Verifying Hash Integrity ... ` then `Bad Data Hash`, before any image loads.
2. **U-Boot checks each image's hash** when it loads the image (`fit_image_select`, `boot/image-fit.c:1975`, `:2145`; `fit_image_verify`, `:1423`), so a changed kernel or DTB fails even under a valid configuration signature: `Bad hash value for 'hash-1' hash node in '<image>' image node` (`boot/image-fit.c:1338`, `:1404`).
3. **The environment** is read from the two copies at `0x1F0000` and `0x210000` (`env/mmc.c:397-439` with `CONFIG_SYS_REDUNDAND_ENVIRONMENT`).

The refusal lines `fit.py` matches are the ones these functions print, as seen in the runs.

## Exit criterion

New acceptance script `tests/acceptance/m9/fit.py`. It runs from the QSPI flash, boot mode 3, with no `-bios`, `-kernel`, `bl32=` or `bl33=`, and uses a fresh copy of each image for each case.

1. **Accepted:** U-Boot prints the FIT's configuration check as passed for the project key (`sha256,rsa2048:<key name>+`) and each image's hash as OK, then starts the kernel. Linux reaches the shell with `/` on slot A's PARTUUID. `BOOT_A_LEFT` went from 3 to 2 and was saved before `bootm` (the order of the lines shows it).
2. **Rejected, each before kernel entry**, with `Starting kernel` never printed. In each case U-Boot prints its reason, resets, and tries again until the counter is 0. It then stops at the prompt and prints the slot and its counter. Nothing boots by another route. The cases:
   - a kernel byte changed after signing (the image hash fails: `Bad hash value for 'hash-1' hash node in 'kernel' image node`);
   - one byte of the DTB's data changed after signing (the image hash fails: `... in 'fdt' image node`; the configuration signature still verifies, because it covers no image data);
   - a FIT with no configuration signature (the required key finds none);
   - a FIT signed with a second key (the required key does not verify it);
   - a FIT signed with the profile key whose signature covers only the kernel (the patched code refuses it; the pinned code would boot it);
   - the unsigned FIT with `verify=n` stored: the boot command sets `verify` itself before `bootm`, so the stored value cannot turn the checks off (`boot/bootm.c:262`);
   - upstream's two crafted FITs, `fakeroot` and `kernel@`: U-Boot's format check refuses them before the signature check (`Bad FIT kernel image format`; for `kernel@` also `Signature checking prevents use of unit addresses (@) in nodes`).
3. **Trust anchor:** each run directory records the SHA-256 of the flash and card images it used and of the FIT in slot A (`images.sha256`, `fit.sha256`), and keeps a copy of the two build records with the public key, each control DTB that carries it, U-Boot and every FIT (`u-boot-m9.txt`, `fit-m9.txt`). Every negative case uses the same U-Boot binary and key as the accepted case, and the hashes show it.
4. **Profiles side by side:** M8 acceptance (the vendor-default profile) runs unchanged.
5. **Log gate:** the `-d unimp,guest_errors,invalid_mem` lines of each run are those of M8's chain list, or new lines checked at their source.

## Evidence

[DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md); spec §8 (v0.4), §12; `tests/guests/out/fw/u-boot.config` (the vendor build's effective configuration); `../../evidence/EVK-2026-10-29-post-firmware.md` (the board's product image enables a redundant environment, FIT signatures and bootcount: G2, a sample); U-Boot `doc/usage/fit/signature.rst` at the pinned commit.

## Next blocker (fork `176d418966`)

None for this unit, and no model change. The `-d unimp,guest_errors,invalid_mem` logs of every M9 run hold only lines already listed for M4, M5 and the M8 chain. Layer verified: U-Boot's serial output and the environment copies on the card. Next: M9-ab. With no commit from Linux, each boot of slot A spends an attempt; after three, U-Boot boots slot B (seen in proof 1). M9-ab adds Linux's health check and commit, rollback, and the damaged-copy cases.
