# M9-update-failure — spec

**Milestone:** M9 (platform behaviour; third and last unit). **Requirements:** REQ-BOOT-007, REQ-BOOT-008 (proposed here). Statuses change at release closure. **Status:** implemented.

One page. Facts carry their source; inferences and assumptions are labelled (I) / (A). The contracts are [DR-0008](../../decisions/DR-0008-m9-boot-policy-profile.md) decisions 8 and 10. M9-fit and M9-ab built the rest of the policy.

## Scope

**No new block, and no QEMU change expected.** This unit adds the update tool to the slots' Linux and checks a successful update, a refused payload and three interruptions, on the chain from the QSPI flash.

- **The payload.** It is an ext4 image of a slot's root file system (`m9-payload.img`, 40 MiB, version 2; the card's slots are version 1), with its SHA-256 beside it. It is slot-independent: the same image can go to A or B.
- **The update medium.** A second card in the carrier slot (`-drive if=sd,index=1`). Its disk identifier is `0x525a0004`, and its partition 1 is ext4, holding the payload and its checksum. The tool finds the card by that identifier, not by the name Linux gives it (gap 22: the vendor device tree has no `mmc` aliases, so the names follow probe order). This is the project's update medium, standing in for a USB stick or a download. It is not an OTA framework.
- **The update tool** `/sbin/m9-update`, run by hand (or by the test) in the running slot:
  1. **Protect the active slot.** The target is the slot whose partition is not `/`. The tool stops if the target partition is `/` or is mounted.
  2. **Mark the target not bootable** before writing to it: one `fw_setenv` call sets `BOOT_<target>_LEFT=0` and clears `M9_PENDING` and `M9_ROLLBACK`. M9-ab left `M9_ROLLBACK` for the next update to clear.
  3. **Write** the payload to the target partition (`dd`, `conv=fsync`).
  4. **Verify** the bytes read back from the partition, after dropping Linux's page cache, against the payload's SHA-256 file. If they differ, the tool stops: the target stays not bootable, and nothing is selected.
  5. **Select** in one `fw_setenv` call: `M9_PENDING=<target>`, `BOOT_<target>_LEFT=3`, `BOOT_ORDER=<target> <running>`.

  It prints one `M9-UPDATE:` line before each step. A reboot then boots the target as a pending update, and M9-ab's health service commits it or lets it roll back.
- **Slot identity.** A slot-independent payload cannot carry its slot's name. The health service therefore drops M9-ab's `/etc/m9-slot` check, and keeps the two checks that identify the slot from outside the image: `/` is the partition of the slot U-Boot booted, and its PARTUUID is the kernel's `root=PARTUUID=`. `rcS` names the slot from the partition. M9-ab's proof of the dropped check is removed with it.
- **Interruptions (DR-0008 decision 10).** The test stops the QEMU process at a declared point, then starts a new QEMU on the same image files. These are the media as QEMU left them; nothing repairs or rewrites them in between.
  - **What this models:** a process interruption. the guest's own cache is lost with the process, and what QEMU has already handed to the host file is expected to land whole (I: the host's write path, not tested here).
  - **What it does not model:** an SD card tearing a write, or physical power loss. Those are not claimed.
  - **Timing:** the stop follows a console line, so the exact point within a step is approximate. For the environment write, the test asserts an invariant, not a moment, and records which state each run found.
- **Not in this unit:** a network update, an OTA framework, anti-rollback, dm-verity, power-loss guarantees, U-Boot writing the QSPI flash.

## What the guest needs

U-Boot: M9-fit's boot command, unchanged. Linux:
- both SD hosts (the module card and the carrier card, as in M7's two-card runs);
- write access to the whole module card for `dd` and `fw_setenv`.

BusyBox: `dd`, `sha256sum`, `mount`, `sync` (its build configuration).

## Exit criterion

New acceptance script `tests/acceptance/m9/update.py`, on the chain from the QSPI flash, with fresh copies of the M9 card and the update card per case:

1. **A successful update.**
   - Slot A (version 1) runs the tool, which writes, verifies and selects slot B.
   - After `reboot`, U-Boot boots B as a pending update. Linux runs version 2 from partition 3, and the health service commits the update.
   - Afterwards, the active environment copy holds `M9_GOOD=B`, `BOOT_ORDER=B A`, `BOOT_B_LEFT=3`, and neither `M9_PENDING` nor `M9_ROLLBACK`.
   Then, from the media that run left, slot B (version 2) runs the tool, which updates slot A, and A boots version 2. Each time, QEMU is stopped right after the tool, before the updated slot ever boots. On the host, the image file must then show the written slot holding the payload's bytes, the running slot keeping its version and its signed FIT, and the pending selection saved. A new QEMU on that media boots the update. Once a slot has booted, its ext4 file system has changed, so the byte check comes first.
2. **A refused payload.** The payload has one byte changed, and its checksum file is the original. The tool reports the mismatch and selects nothing: `BOOT_B_LEFT=0`, no `M9_PENDING`. After `reboot`, slot A boots.
3. **Interrupted during the payload write** (QEMU stopped a moment after `M9-UPDATE: writing slot B`).
   - The stopped card holds `BOOT_B_LEFT=0` and no pending update.
   - A new QEMU on the same media boots A, which commits.
   - The tool then runs again to completion, and B boots version 2: the update can be retried.
4. **Interrupted after verification, before the selection** (stopped at `M9-UPDATE: slot B verified`). The same outcome as case 3: A boots and nothing is pending.
5. **Interrupted during the environment write** (stopped at `M9-UPDATE: saving the selection`, four runs: 0, 0.05, 0.3 and 1.0 s after the line). Which state the three short stops find depends on timing (in the retained run: old, old, new). At 1.0 s the save has finished, so that stop always reaches the new state, and every run checks both paths.
   - Each time, the active copy is either the whole old state or the whole new state.
   - The boot follows it: A with version 1, or B pending, then committed.
   - Each run's outcome is recorded.
6. In every case slot A, the active slot during the update, still boots.
7. M9-fit's and M9-ab's checks run unchanged, apart from the dropped `/etc/m9-slot` check.

## Evidence

DR-0008 decisions 8 and 10; the M9-ab unit page; U-Boot `tools/env/fw_env.c` at the pinned commit (how the redundant copy is written).

## Next blocker (fork `176d418966`)

None: with this unit M9 is complete, with no model change in any of its three units. Limits kept: the interruptions are process stops on the image files QEMU left, not power loss of a card, and the exact stop point within a step is approximate; the update medium is a card, not a network; there is no anti-rollback, so an older validly signed payload would be accepted.
