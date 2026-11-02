# Building and testing by hand

This file gives the commands to build the QEMU fork, run its tests, check its style and read its code in an editor. All commands here were run on this repo. Paths are relative to the repository root.

For what the code means, see the other learning docs ([`README.md`](README.md)).

Contents:
1. [First build](#1-first-build)
2. [Rebuilding after an edit](#2-rebuilding-after-an-edit)
3. [Running tests](#3-running-tests)
4. [Style check](#4-style-check)
5. [Watching a device at work: trace points and logs](#5-watching-a-device-at-work-trace-points-and-logs)
6. [Editor setup: VS Code with clangd](#6-editor-setup-vs-code-with-clangd)
7. [Gotchas](#7-gotchas)
8. [Booting Linux by hand](#8-booting-linux-by-hand)

---

## 1. First build

```bash
git submodule update --init          # qemu/ at the pinned rzv2l-dev commit
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs
ninja qemu-system-aarch64
```

- The build is in `build/qemu/` (gitignored). Never build inside `qemu/`. The fork must stay a clean source tree.
- `--target-list=aarch64-softmmu` builds only the 64-bit Arm system emulator. This project needs nothing more, so the build is much faster than a full QEMU build.
- `configure` also writes `build/qemu/compile_commands.json`, the compiler flags for each file. The editor setup ([§6](#6-editor-setup-vs-code-with-clangd)) reads this file.

The build directory used up to now has extra options from EXP-001 ([`docs/experiments/EXP-001-smc-and-impdef-sysregs.md`](../experiments/EXP-001-smc-and-impdef-sysregs.md)):

```bash
../../qemu/configure --target-list=aarch64-softmmu --enable-debug-info --disable-docs \
  --disable-werror --disable-sdl --disable-gtk --disable-vnc --disable-opengl
```

- `--enable-debug-info` keeps the symbols for gdb.
- The `--disable-*` options remove graphical front-ends. A board model without a display does not use them.

To see the options of an existing build directory, run `tail -1 build/qemu/config.status`.

## 2. Rebuilding after an edit

```bash
cd build/qemu
ninja qemu-system-aarch64
```

Ninja compiles again only what changed. Ninja also sees changes to `Kconfig`, `meson.build` or `trace-events`: it runs meson again first.

A new `.c` file compiles only when a machine selects its Kconfig switch. For this project the chain is `RZV2L_SMARC` (board, on by default) → `R9A07G054` (SoC) → `ARM_GIC`, `RENESAS_RZG2L_SYSC`, `RENESAS_RZV2L_CPG` and `RENESAS_RZ_SCIFA`.

If no machine selects the switch of a file yet (as for SYSC during M1-T02), compile-check the file by hand:
1. Copy the command of a file in the same directory from `compile_commands.json`.
2. Change the file name in the command.
3. Add `-Werror`. This build directory was configured with `--disable-werror`, so without this flag a warning does not stop the build.

## 3. Running tests

This section gives the commands for the qtests, the guest probe and the acceptance run. [`testing.md`](testing.md) explains what each one checks.

QEMU's device tests are **qtests** ([`testing.md` §1](testing.md#1-qtest-and-guest-probes)). A qtest is a small C program. It starts QEMU without a guest CPU, and it reads and writes addresses directly.

One test, run directly (the fastest method; it shows each check):

```bash
cd build/qemu
ninja tests/qtest/arm-gicv3-iidr-test
QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/arm-gicv3-iidr-test
```

```
ok 1 /aarch64/arm-gicv3/iidr/default
ok 2 /aarch64/arm-gicv3/iidr/property
```

The same test through meson. Meson first builds what the test needs:

```bash
pyvenv/bin/meson test qtest-aarch64/arm-gicv3-iidr-test
```

The test of this machine (M1-T04):

```bash
ninja qemu-system-aarch64 tests/qtest/rzv2l-smarc-test
QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-smarc-test
```

```
ok 1 /aarch64/rzv2l-smarc/sysc/id
ok 2 /aarch64/rzv2l-smarc/sysc/boot-pins
ok 3 /aarch64/rzv2l-smarc/sysc/boot-mode-reserved
ok 4 /aarch64/rzv2l-smarc/gic/layout
ok 5 /aarch64/rzv2l-smarc/gic/identity
```

To run one test case only, add `-p /aarch64/rzv2l-smarc/gic/layout`.

The guest probe (M1-T05) runs inside the machine ([`testing.md` §2](testing.md#2-a-program-inside-the-machine-the-m1-probe)). It needs the cross compiler `aarch64-linux-gnu-gcc` (`apt install gcc-aarch64-linux-gnu`):

```bash
tests/probes/m1-skeleton/run.sh          # builds the probe, runs it, exit 0 = all checks pass
echo $?
cat tests/probes/m1-skeleton/out/qemu.log    # the -d unimp,guest_errors,invalid_mem lines
```

Extra arguments to the probe's `run.sh` go to QEMU. For example, `run.sh -semihosting-config enable=off` shows the failure when the probe has no output channel.

The exit status of `run.sh`:
- 0: all checks pass
- 1: a check fails
- 2: the probe gave no result

The M1 acceptance run (M1-T06) combines the probe with the monitor checks and the log gate ([`testing.md` §3](testing.md#3-the-acceptance-run-is-m1-done)):

```bash
tests/acceptance/m1/run.sh       # ends with "M1 ACCEPTANCE: PASS", exit 0
ls tests/acceptance/m1/out/      # the captured mtree, qtree, roms, DTB and probe output
```

- Since M1-T07, the acceptance run also needs `dtc` and a host `cc` (`apt install device-tree-compiler gcc`).
- The first run gets the device-tree sources of the pinned kernel into `tests/guests/dl/` (gitignored). This needs the network and takes approximately a minute.

All Arm qtests (several minutes):

```bash
pyvenv/bin/meson test --suite qtest-aarch64
```

`pyvenv/bin/meson test --suite qtest-aarch64 --list` lists the test names.

**A test that never failed proves nothing** (AGENTS.md rule 7). The project checks each test with a *mutation*:
1. Change the model on purpose.
2. Build again.
3. Make sure that the test becomes red.
4. Restore the model.

`docs/units/<unit>/tasks.md` gives the mutation for each task.

A mutation by hand, for example "`debugen` on bit 8":

```bash
cd qemu
sed -i 's/STAT_DEBUGEN, 9, 1/STAT_DEBUGEN, 8, 1/' hw/misc/renesas_rzg2l_sysc.c
cd ../build/qemu && ninja qemu-system-aarch64
QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-smarc-test
#   not ok /aarch64/rzv2l-smarc/sysc/boot-pins ... (0x00010100 == 0x00010200)
git -C ../../qemu checkout -- hw/misc/renesas_rzg2l_sysc.c      # restore from git
ninja qemu-system-aarch64                                       # rebuild the good model
```

Read the red line, not only the colour. The assertion that fails must be the one written for that mutation. [`testing.md` §1](testing.md#1-qtest-and-guest-probes) has the M1 results, with one test that became red for the wrong reason.

## 4. Style check

QEMU's `checkpatch.pl` checks the coding style that upstream QEMU expects. Run it inside `qemu/`.

For changes that are not committed: first announce new files to git with `git add -N`, so that the diff includes them:

```bash
cd qemu
git add -N <new files>
git diff | scripts/checkpatch.pl --no-signoff -
```

For the commits on the unit branch:

```bash
scripts/checkpatch.pl --no-signoff rzv2l-base..HEAD
```

- Use `--no-signoff`, because commits written by an agent have no `Signed-off-by:` (AGENTS.md "Commit style").
- A new file causes the message "does MAINTAINERS need updating?" until the RZ/V2L section in `MAINTAINERS` lists the file.

## 5. Watching a device at work: trace points and logs

Trace points and log masks show what a device does while the guest runs. This section shows both.

**Trace points** print one line each time a device callback runs. The `trace-events` file of a directory declares them, for example `qemu/hw/misc/trace-events`:

```
renesas_rzg2l_sysc_read(uint64_t offset, uint64_t data, unsigned size) "offset 0x%" PRIx64 " data 0x%" PRIx64 " size %u"
```

At build time, this line becomes a C function `trace_renesas_rzg2l_sysc_read()`, and the device calls it. Trace points are off unless you enable them with `-trace`:

```bash
./qemu-system-aarch64 -trace help | grep renesas          # list them
./qemu-system-aarch64 ... -trace 'renesas_rzg2l_sysc_*'   # enable by pattern
```

An example on `virt`. The monitor command `xp` reads memory as a CPU does, so the callback of the GIC runs:

```bash
printf 'xp /1wx 0x08000008\nquit\n' | ./qemu-system-aarch64 -M virt,gic-version=3 \
  -cpu cortex-a57 -S -display none -nodefaults -monitor stdio -trace gicv3_dist_read
```

```
gicv3_dist_read GICv3 distributor read: offset 0x8 data 0x43b size 4 secure 0
08000008: 0x0000043b
```

**Log masks** (`-d`) print the problems that the model reports with `qemu_log_mask()` (names from `qemu/util/log.c:513-532`):

| `-d` name | Reported by | Example in this project |
|---|---|---|
| `guest_errors` | `LOG_GUEST_ERROR`: the guest did something the hardware forbids | write to a read-only SYSC register |
| `unimp` | `LOG_UNIMP`: the guest touched something the model does not implement | read of a SYSC offset other than the three ID registers |
| `invalid_mem` | `LOG_INVALID_MEM`: QEMU's memory core refused an access before any device code ran | an 8- or 16-bit read of SYSC, which accepts only 32-bit accesses (`qemu/system/memory.c:1404`); **any access to an unmapped address** ("reason: rejected") |

Use them together: `-d unimp,guest_errors,invalid_mem`. Without `invalid_mem`, QEMU does not log accesses to unmapped addresses. This qtest read of a hole on `virt` shows it:

```bash
printf 'readl 0x0c000000\n' | ./qemu-system-aarch64 -M virt,gic-version=3 -display none \
  -nodefaults -accel qtest -qtest stdio -d invalid_mem
```

```
Invalid read at addr 0xC000000, size 4, region '(null)', reason: rejected
```

With `-d guest_errors` in its place, the same read prints nothing.

## 6. Editor setup: VS Code with clangd

QEMU is too large for an editor to find its include paths without help. Give the editor the real compiler flags from `build/qemu/compile_commands.json`. Then go-to-definition, hover and find-references work across the fork.

You need:
- the **clangd** extension (`llvm-vs-code-extensions.vscode-clangd`)
- the `clangd` binary (`apt install clangd`)

Open the repository root as the workspace. Create `.vscode/settings.json` (`.vscode/` is gitignored, so this file stays local):

```jsonc
{
    // clangd gives IntelliSense from the real QEMU build flags.
    "clangd.arguments": [
        "--compile-commands-dir=${workspaceFolder}/build/qemu",
        "--query-driver=/usr/bin/cc,/usr/bin/gcc,/usr/bin/aarch64-linux-gnu-gcc",
        "--header-insertion=never",
        "--background-index"
    ],
    // Microsoft C/C++ IntelliSense would fight clangd; keep its debugger only.
    "C_Cpp.intelliSenseEngine": "disabled",
    "files.associations": {
        "trace-events": "plaintext",
        "Kconfig": "kconfig"
    }
}
```

Then run **Developer: Reload Window**. The first background index takes a few minutes. The status bar shows the progress.

- Why the setting is necessary: clangd looks for `compile_commands.json` only in the parent directories of the file and in their `build/` subdirectories. `build/qemu/` is not one of them. Without the setting, clangd knows no include paths, and each QEMU type is "unknown".
- A file that is not in the build yet also works (for example SYSC before T03). clangd uses the flags of a file in the same directory.
- To check one file from the command line, without VS Code:

  ```bash
  clangd --compile-commands-dir=build/qemu --check=qemu/hw/misc/renesas_rzg2l_sysc.c 2>&1 | tail -1
  ```

  The output ends with `All checks completed, 0 errors`.

Reading QEMU code in the editor:
- **Trace functions** (`trace_…`) go to a generated header, `build/qemu/trace/trace-hw_misc.h`, not to `trace-events`. The build writes the header from `trace-events` ([§5](#5-watching-a-device-at-work-trace-points-and-logs)).
- **`REG32` / `FIELD` are macros.** Hover over them to see the constants that they make ([`qemu-basics.md` §3.1](qemu-basics.md#31-reading-a-real-device-sysc)).
- An empty `~/.config/clangd/config.yaml` makes clangd log "Config should be a dictionary" at each start. This message causes no problem. Delete the file, or put `{}` in it.

## 7. Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `meson test` fails: "references functions or classes that don't exist … generated with an old version of meson" | the system `meson` is a different version from the one QEMU configured with | use `build/qemu/pyvenv/bin/meson` |
| a new device file never compiles | its Kconfig switch is not selected by any machine yet | expected until the SoC selects it; compile-check by hand ([§2](#2-rebuilding-after-an-edit)) |
| clangd: every QEMU type "unknown" | clangd cannot find `compile_commands.json` | [§6](#6-editor-setup-vs-code-with-clangd) |
| checkpatch: "does MAINTAINERS need updating?" | new file not listed in `MAINTAINERS` | added once with the board (M1-T04) |
| `-d unimp,guest_errors,invalid_mem` prints the list of log items and QEMU exits; or `-M rzv2l-smarc` is unknown | the shell ran the distribution QEMU (`/usr/bin/qemu-system-aarch64`, 8.2.2 on Ubuntu 24.04), which has no `invalid_mem` mask and no RZ/V2L machine | run `build/qemu/qemu-system-aarch64` ([§8](#8-booting-linux-by-hand)) |

## 8. Booting Linux by hand

`scripts/run.sh` boots a guest kernel with the BusyBox initramfs and puts the serial console (SCIF0) on the terminal. Two kernels are available, each with its own unmodified device tree:

- **G0:** mainline Linux v6.12.59, arm64 `defconfig`.
- **G1:** the Renesas vendor kernel, with its own `defconfig`.

Build the guests once:

```bash
tests/guests/g0/build-kernel.sh       # G0 kernel
tests/guests/g0/build-dtb.sh          # G0 device tree
tests/guests/g0/build-initramfs.sh    # BusyBox initramfs (both kernels use it)
tests/guests/g1/build-kernel.sh       # G1 kernel and device tree
```

Then boot. The script uses the project's QEMU (`build/qemu/qemu-system-aarch64`, or `$QEMU`), not the one on your `PATH` ([§7](#7-gotchas)).

```bash
scripts/run.sh                  # G1, eSD boot mode, the DTB's own boot arguments
scripts/run.sh -t g0            # G0
scripts/run.sh -b 1             # eMMC boot mode
scripts/run.sh --dumpdtb        # write the DTB that QEMU gives the kernel, then stop
scripts/run.sh --dry-run        # print the QEMU command
scripts/run.sh --help           # all options; QEMU arguments go after --
```

- After about 20 s the shell prompt `rzv2l:~#` comes, after a banner with the machine, the CPUs, the memory and the watchdog.
- Ctrl-A X stops QEMU. Ctrl-A C switches between the console and the QEMU monitor.
- `build/run/<tier>/qemu.log` gets one line for each access that the model does not implement. Set the mask with `-d` (`-d none` turns the log off).
- The SD hosts are stubs until M5. Thus the kernel prints `timeout waiting for hardware interrupt` for `mmc0` and `mmc1` while you work. These lines are expected.
- `-g` stops QEMU before the first instruction and waits for gdb on port 1234.

Checks to try at the prompt:

| Command | Expected | What it shows |
|---|---|---|
| `cat /sys/devices/system/cpu/online` | `0-1` | both CPUs started through PSCI |
| `hexdump -C /proc/device-tree/soc/mmc@11c00000/vqmmc-supply` | `00 00 00 74` (eSD); `00 00 00 18` with `-b 1` | the loader's U-Boot edit for an SD-card boot ([M4-loader-fixups](../units/M4-loader-fixups/spec.md)) |
| `devmem 0x11020a00` | `0x00010000` in eSD mode; bits 2:0 are the boot mode (`-b`) | `SYS_LSI_MODE`, the boot mode pins. The EVK reads `0x00010200`: its DEBUGEN pin is high (`-M rzv2l-smarc,debugen=on`) |
| `watchdog -T 3 -t 1000 /dev/watchdog`, then `killall -9 watchdog` | the board resets about 3 s later; after the new boot, `devmem 0x11010b10` reads 1 | WDT0 and the CPG reset flag ([M4-vendor-kernel](../units/M4-vendor-kernel/spec.md)) |

## CI and independent review

The fork's `.github/workflows/rzv2l.yml` runs on pull requests to `rzv2l-dev`,
pushes to that integration branch, and manual dispatch. Opening or updating a
PR starts a hosted build and tests; it does not deploy or merge anything.
The implementer still builds and tests locally before pushing.

CI makes baseline verification visible on the PR and repeatable on a hosted
runner. Local checks already provide useful evidence, but their logs must be
collected and matched to the final revision manually. CI repeats the checks
after each PR update and attaches the revision and results to that update.

A green **Build and qtests** result means the Arm system emulator built and
the RZ/V2L register tests and the Arm GIC identity test passed; PR runs also check each proposed commit's
patch style. The run uploads logs and a binary archive, and saves a compiler
cache for later runs. It does not run the project's guest boot acceptance or
prove that the model implements the hardware correctly. This first workflow
lives in the QEMU fork; it does not test project-only changes or the project's
exact submodule selection.

For review, open the PR's check and inspect its revision records and logs.
PR runs test GitHub's proposed merge revision; the artifact records that SHA
alongside the PR head and base. Match those revisions to the review target
before treating the results as baseline evidence. A successful check supports
starting independent review; it is not an independent review verdict or merge
approval. Required-check enforcement is a separate repository setting.

The implementer still prepares an isolated local review build. The reviewer
changes the model deliberately and rebuilds to see whether the tests detect
the error, so the downloaded executable cannot replace this build. Compiler
caching helps repeated compilation, but different worktree and debug paths
can prevent reuse between builds. Follow the
[review prompt](../units/templates/review-prompt.md) for the review checks and
mutation budget; CI does not replace them. After fixes, apply the remaining
acceptance and regression gates in `AGENTS.md`, then merge on the operator's
word.
