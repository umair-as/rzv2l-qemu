# M9: a boot policy on the emulated board

> **Context.** Milestone M9 (spec [§17](../spec/project.md#17-milestones)): platform behaviour, within the limits of spec [§12](../spec/project.md#12-secure-world-and-the-limits-of-security-claims). The decision record is [DR-0008](../decisions/DR-0008-m9-boot-policy-profile.md). Units: M9-fit ([spec](../units/M9-fit/spec.md), [tasks](../units/M9-fit/tasks.md)), M9-ab ([spec](../units/M9-ab/spec.md), [tasks](../units/M9-ab/tasks.md)), M9-update-failure ([spec](../units/M9-update-failure/spec.md), [tasks](../units/M9-update-failure/tasks.md)). U-Boot paths are at `renesas-u-boot-cip` `4eebfbaa4e` with the M9 profile's one patch.

Until M8, the project asked one question: does the board's software run on the model as it runs on the board? M9 asks a different one: does a boot policy do what it promises, on the whole firmware chain? The policy answers four questions:

- **Signatures:** does U-Boot boot only a kernel signed with the right key?
- **Attempts:** does it count each boot attempt before it tries?
- **Commit:** does Linux commit only a slot that works?
- **Interruption:** does an update, interrupted by stopping QEMU, leave the board able to boot?

No register model changed for any of this. Every result comes from the board's firmware, a second U-Boot build, and scripts in the slots' Linux. That is what an emulator can show well: software decisions, run many times, with damaged inputs that are hard to make on a real board.

This page is written for two readers. If you know U-Boot and A/B updates, it shows what the project chose and what the tests prove. If you are new to QEMU, it shows how a machine model becomes a test bench for firmware behaviour.

## 1. Two U-Boot builds

This section explains why M9 needs its own U-Boot build. The vendor build checks no signatures, and it keeps one copy of its environment (`tests/guests/out/fw/u-boot.config`). The board's own product image adds both features ([`../evidence/EVK-2026-10-29-post-firmware.md`](../evidence/EVK-2026-10-29-post-firmware.md)). M9 therefore builds the same pinned source a second time, with a listed fragment (`tests/guests/fw/u-boot-m9.cfg`):

| Option | Why |
|---|---|
| `CONFIG_FIT_SIGNATURE`, `CONFIG_RSA` | U-Boot checks FIT signatures on the board, not only `mkimage` on the host |
| `CONFIG_SYS_REDUNDAND_ENVIRONMENT`, `CONFIG_ENV_OFFSET_REDUND=0x210000` | two environment copies, so one damaged copy has a defined recovery |
| `# CONFIG_LEGACY_IMAGE_FORMAT is not set` | `bootm` takes FIT images only |
| `CONFIG_CMD_PART` | the boot command reads a slot's PARTUUID from the card |
| `CONFIG_USE_DEFAULT_ENV_FILE` | the built-in default environment is the M9 policy (`u-boot-m9.env`), not the vendor's unsigned boot command |
| `CONFIG_LOCALVERSION="-m9"` | the banner names the build: `U-Boot 2024.07-m9` |

The vendor build stays as it was and keeps running the acceptance of M7 and M8. The spec lists the second build as an exception to its rule that firmware is not changed (spec §8, v0.4).

## 2. The trust anchor

This section shows where the public key lives, and what "required" means. A FIT image carries its own signature. U-Boot needs a public key to check it against, in a place an attacker cannot change from the FIT: U-Boot's own control device tree. The build turns the key into a `.dtsi` with U-Boot's `tools/key2dtsi.py` and builds it into every control DTB (`CONFIG_DEVICE_TREE_INCLUDES`):

```
$ fdtget tests/guests/out/m9/smarc-rzv2l.dtb /signature/key-m9-dev required
conf
$ fdtget tests/guests/out/m9/smarc-rzv2l.dtb /signature/key-m9-dev algo
sha256,rsa2048
$ fdtget tests/guests/out/m9/smarc-rzv2l-ecc.dtb /signature/key-m9-dev required
conf
```

`required = "conf"` means that U-Boot boots a configuration only if a signature by this key covers it. Without `required`, a FIT with no signature at all would still boot (U-Boot's `doc/usage/fit/signature.rst`: "Only required keys are" enforced; not tested here).

The vendor build has two control DTBs, one for a board with ECC memory and one without (`CONFIG_MULTI_DTB_FIT`), and U-Boot picks one at run time. The key must be in both, so the build reads it back from each.

The key is a test key, made once by the build and kept with its untracked outputs. Every later build and every test uses the same key, and each run records the key's hash.

## 3. What the signature covers

This section shows the two checks U-Boot makes on a FIT, and why both are needed. The project's FIT holds the vendor kernel and the vendor DTB, unchanged, and one signed configuration:

```
$ tests/guests/out/m9/mkimage -l tests/guests/out/m9/fit/fitImage
 ...
 Image 0 (kernel)
  ...
  Hash algo:    sha256
  Hash value:   0d41afbb43338e1858c398be15401b888e9fec13588235948ae87dbff23269c6
 Image 1 (fdt)
  ...
  Hash algo:    sha256
  Hash value:   13b2efb0e59c705ebee24c9711b23b5a49226b031811019a480cef149dc2ba0b
 Configuration 0 (conf)
  ...
  Kernel:       kernel
  FDT:          fdt
  Sign algo:    sha256,rsa2048:m9-dev
```

The configuration's signature does not cover the images' data. It covers their nodes, including each image's `hash-1` value. U-Boot therefore checks in two steps:

1. The configuration signature, against the required key (`fit_config_verify`, `boot/image-fit.c:2120-2126`).
2. Each image's data, against its hash (`fit_image_verify`, `:1423`).

A FIT with one kernel byte changed passes step 1 and fails step 2 (the run's log, lines 43-59, with the image description shortened):

```
   Verifying Hash Integrity ... sha256,rsa2048:m9-dev+ OK
   Trying 'kernel' kernel subimage
     ...
     Hash value:   0d41afbb43338e1858c398be15401b888e9fec13588235948ae87dbff23269c6
   Verifying Hash Integrity ... sha256 error!
Bad hash value for 'hash-1' hash node in 'kernel' image node
Bad Data Hash
ERROR -2: can't get kernel image!
```

**Which nodes the signature covers.** The signer writes the list into the signature node, as `hashed-nodes`:

```
$ fdtget tests/guests/out/m9/fit/fitImage /configurations/conf/signature-1 hashed-nodes
/ /configurations/conf /images/kernel /images/kernel/hash-1 /images/fdt /images/fdt/hash-1
$ fdtget tests/guests/out/m9/fit/fitImage-kernel-only /configurations/conf/signature-1 hashed-nodes
/ /configurations/conf /images/kernel /images/kernel/hash-1
```

The second FIT is signed with the right key, but its signature leaves out the DTB, so someone could swap the DTB. The pinned U-Boot reads `hashed-nodes` and checks what the list names, and the list is not itself signed. So the pinned U-Boot accepts this FIT. Upstream commit `2092322b31cc` builds the list from the configuration instead (the configuration names the DTB), and refuses it. The M9 build carries that commit, and its build checks both tools on this FIT on every run.

## 4. Spend the attempt, then try

This section shows the boot command, which is plain U-Boot environment script. For the first slot in `BOOT_ORDER` with an attempt left, U-Boot lowers the counter and saves it before it loads anything (a trial boot of the M9 card):

```
Saving Environment to MMC... Writing to redundant MMC(0)... OK
M9: slot A: attempt saved: BOOT_A_LEFT=2 BOOT_B_LEFT=3
26004362 bytes read in 5476 ms (4.5 MiB/s)
## Loading kernel from FIT Image at 58000000 ...
   Using 'conf' configuration
   Verifying Hash Integrity ... sha256,rsa2048:m9-dev+ OK
```

The order of the first two lines is the point. A boot that crashes or hangs has already spent its attempt, and nobody needs to remember it later. If the save fails, U-Boot stops at its prompt. If `bootm` returns, because a check refused the FIT, U-Boot prints the reason and resets, and the next boot sees the lower counter. With no attempt left in any slot, U-Boot stops at the prompt and prints the counters. It never refills them on its own.

Two details matter:
- **Counters are hexadecimal.** U-Boot's `setexpr` and `itest` count in hexadecimal. The counters stay below 10, so the difference never shows.
- **The `verify` variable.** `bootm` checks signatures only while the variable `verify` is unset or starts with `1`, `y` or `t` (`boot/bootm.c:262`, `env_get_yesno` in `env/common.c:334-342`). Any other stored value, `n` or `no` or `0`, turns the checks off. The boot command sets `verify` to `yes` itself, after it saves, so no stored value turns them off on this path.

A person at U-Boot's prompt can still type `booti` and boot anything. Spec §12 does not claim more than the automatic path.

## 5. Two copies of the environment

This section shows how U-Boot keeps its state safe across a damaged write. Each copy is a CRC, a flag byte, then the variables (`include/env_internal.h`). U-Boot uses the valid copy with the higher flag, and a save writes the other copy with the next flag. The tests read the copies with the project's `uboot-env.py`:

```
$ python3 tests/guests/sd/uboot-env.py m9-read <the card after one boot>
copy 1: valid flag 3 BOOT_B_LEFT=3 BOOT_ORDER=A B BOOT_A_LEFT=3 M9_GOOD=A
copy 2: valid flag 2 BOOT_A_LEFT=2 BOOT_B_LEFT=3 BOOT_ORDER=A B
```

Copy 2 (flag 2) is U-Boot's saved attempt. Copy 1 (flag 3) is Linux's commit after the boot, written by `fw_setenv`, which is built from the same U-Boot source.

What happens when a copy is damaged:

| Damaged | What U-Boot prints | What it uses |
|---|---|---|
| copy 1 | `Reading from redundant MMC(0)... OK` | copy 2; the next save rewrites copy 1 |
| copy 2 | `Reading from MMC(0)... OK`, the same as an intact card | copy 1; the next save rewrites copy 2 |
| both | `*** Warning - bad CRC, using default environment` | the built-in default: the M9 policy with fresh counters |

One damaged copy produces no warning: `env_check_redund` picks the valid one and returns success (`env/common.c:447-493`). The test therefore reads the card before the boot to prove that the copy really was damaged.

## 6. Linux commits the slot it runs from

This section shows the other half of the policy. U-Boot cannot know whether Linux came up well, so a service in each slot does that, last in start-up (`/sbin/m9-health`):

1. Read `m9_slot`, the slot U-Boot saved before the boot.
2. Check that `/` is that slot's partition, and that its PARTUUID is the kernel's `root=PARTUUID=`.
3. Run the checks in `/etc/m9-health.d/`.
4. Commit that slot in one `fw_setenv` call.

A failure writes nothing and reboots, so the slot's attempts run down. When a pending update runs out, the other slot boots, commits, and records the rollback:

```
M9-HEALTH: slot B: health check 90-fail failed; not committed; rebooting
M9-HEALTH: slot A committed, / is 525a0003-02: BOOT_A_LEFT 3;M9_GOOD A;M9_ROLLBACK B;M9_PENDING;BOOT_ORDER A B;
M9-HEALTH: rollback: slot B gave up, slot A runs
```

`fw_printenv` keeps a lock file in `/run`. The BusyBox root had no `/run`, so until the slots mounted a tmpfs there, every read failed with `Error opening lock file /run/fw_printenv.lock` (seen in a diagnostic boot during M9-ab).

## 7. Updating a slot, and stopping in the middle

This section shows the update tool, and what a stopped update leaves behind. The payload is a root file system image, version 2, with its SHA-256. It sits on a second card in the carrier slot, which the tool finds by its disk identifier. The tool runs in the slot that is up, and only ever writes the other one (`/sbin/m9-update`):

```
M9-UPDATE: slot A runs from /dev/mmcblk0p2; updating slot B (/dev/mmcblk0p3) from /dev/mmcblk1p1, 41943040 bytes
M9-UPDATE: marking slot B not bootable
M9-UPDATE: writing slot B
M9-UPDATE: verifying slot B
M9-UPDATE: slot B verified 1b8cd21a33e493f6152f0bc4d731d890b9cdc9ecd5be71a7d23828fd22b3295f
M9-UPDATE: saving the selection
M9-UPDATE: slot B selected as a pending update; reboot to try it
```

After `reboot`, slot B prints `M9 slot B, version 2`, and the health service commits it: `M9-HEALTH: the update of slot B is committed`. The order of the steps is what makes a stop safe:
- **Before writing,** the target is made unbootable, so a half-written slot is never tried.
- **Before selecting,** the tool drops Linux's page cache and reads the bytes back from the partition, then checks them. The test also checks the image file on the host after the run: the written slot holds the payload's bytes, and the running slot keeps its version and its signed FIT. A payload with one byte changed stops there: `stopped: slot B holds 91dcf380…, the payload's checksum is 1b8cd21a…; nothing selected`.
- **The selection is one `fw_setenv` call.** It writes the copy that is not in use, then that copy's higher flag makes it the one U-Boot reads.

**Stopping in the middle.** The test stops the QEMU process at a console line, then starts a new QEMU on the same image files, as the stopped one left them. Stopped while writing slot B, the card holds:

```
copy 1: valid flag 3 BOOT_B_LEFT=3 BOOT_ORDER=A B BOOT_A_LEFT=3 M9_GOOD=A
copy 2: valid flag 4 BOOT_ORDER=A B BOOT_A_LEFT=3 M9_GOOD=A BOOT_B_LEFT=0
```

Copy 2, the newer one, says slot B cannot boot. Slot A boots, and the update runs again to completion. Stopped while saving the selection, three runs found the old state twice and the new state once. Each time the next boot followed it: slot A at version 1, or slot B as the pending update.

**What this does not show.** QEMU hands each guest write to the host as a write to the image file, and the host finishes it even when the process is killed (an inference about the host, not something these tests check). So a stopped process is not expected to leave a torn write. A real SD card that loses power during a write can tear it. These tests show the order of the steps and the redundant copies working against a stopped process. They make no claim about a card's behaviour on power loss.

## 8. Pitfalls

- **A signature can cover less than you think.** A FIT signature covers the nodes in its list, and the pinned U-Boot takes that list from the FIT itself. Check `hashed-nodes` with `fdtget`, and test a FIT that signs only part of its configuration (`2092322b31cc`).
- **The signature covers nodes, the hashes cover data.** A changed kernel passes the signature check and fails the hash check. A test that looks only for the signature line misses which check refused the image.
- **`required` decides whether an unsigned FIT boots.** A key node without `required = "conf"` lets a FIT with no signature boot.
- **A stored variable can switch the checks off.** `verify=n` disables `bootm`'s checks (`boot/bootm.c:262`). The boot command sets `verify` itself.
- **A damaged copy can be silent.** U-Boot reads around one bad environment copy without a word. Prove the damage before the boot, or the test passes on an intact card.
- **Assert the copy U-Boot will use.** After two saves, the older copy still holds the older state. A check that searches any copy can match the wrong one; pick the valid copy with the higher flag (0 follows 255).
- **Ordered lines can match across resets.** A boot that resets and tries again prints the same lines again. A check for "accepted" must also check that it all happened in one boot.
- **A damaged copy that U-Boot reads around is still damaged.** Only the next save repairs it, so read the card before trusting either copy.
- **A stopped process is not a power cut.** Killing QEMU loses what the guest had not yet written; what QEMU had already handed to the host is expected to land whole (an inference). A card can tear a write on power loss. Say which one a test shows.
- **Mark a slot unbootable before you write it.** Otherwise a stop during the write leaves a half-written slot that U-Boot may try once the other slot runs out of attempts.
- **Two build systems can disagree about an include path.** `CONFIG_DEVICE_TREE_INCLUDES` must name a file beside the board's `.dts` files: U-Boot's make rules put that directory in front of the path (`dtsi_include_list_deps` in U-Boot's `Makefile.lib`).
