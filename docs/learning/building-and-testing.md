# Building and testing by hand

How to build the QEMU fork, run its tests, check style and read the code with working IntelliSense. Every command here has been run on this repo; paths are relative to the repository root.

For what the code means, see the companion `qemu-machine-modelling.md`.

Contents:
1. [First build](#1-first-build)
2. [Rebuilding after an edit](#2-rebuilding-after-an-edit)
3. [Running tests](#3-running-tests)
4. [Style check](#4-style-check)
5. [Watching a device at work: trace points and logs](#5-watching-a-device-at-work-trace-points-and-logs)
6. [Editor setup: VS Code with clangd](#6-editor-setup-vs-code-with-clangd)
7. [Gotchas](#7-gotchas)

---

## 1. First build

```bash
git submodule update --init          # qemu/ at the pinned rzv2l-dev commit
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs
ninja qemu-system-aarch64
```

- The build lives in `build/qemu/` (gitignored). Never build inside `qemu/`: the fork stays a clean source tree.
- `--target-list=aarch64-softmmu` builds only the 64-bit Arm system emulator, which is all this project needs, so the build is far quicker than a full QEMU build.
- `configure` also writes `build/qemu/compile_commands.json`, the list of compiler flags per file. The editor setup (§6) reads it.

The build directory used so far was configured with extra options from EXP-001 (`docs/experiments/EXP-001-smc-and-impdef-sysregs.md`):

```bash
../../qemu/configure --target-list=aarch64-softmmu --enable-debug-info --disable-docs \
  --disable-werror --disable-sdl --disable-gtk --disable-vnc --disable-opengl
```

`--enable-debug-info` keeps symbols for gdb; the `--disable-*` UI options drop graphical front-ends a headless board model does not use. To see how an existing build directory was configured: `tail -1 build/qemu/config.status`.

## 2. Rebuilding after an edit

```bash
cd build/qemu
ninja qemu-system-aarch64
```

Ninja recompiles only what changed. Edits to `Kconfig`, `meson.build` or `trace-events` are picked up automatically: ninja re-runs meson first.

A new `.c` file is compiled only when its Kconfig switch is selected. The chain for this project is `RZV2L_SMARC` (board, on by default) → `R9A07G054` (SoC) → `RENESAS_RZG2L_SYSC` and `ARM_GIC`. While a file has no selected switch (as SYSC had during M1-T02), compile-check it by hand: borrow a neighbour's command from `compile_commands.json`, swap the file name, and add `-Werror` (this build directory was configured with `--disable-werror`, so warnings would otherwise pass).

## 3. Running tests

QEMU's device tests are **qtests** (`qemu-machine-modelling.md` §7): a small C program starts QEMU without a guest CPU and reads and writes addresses directly.

One test, directly (fastest, shows every check):

```bash
cd build/qemu
ninja tests/qtest/arm-gicv3-iidr-test
QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/arm-gicv3-iidr-test
```

```
ok 1 /aarch64/arm-gicv3/iidr/default
ok 2 /aarch64/arm-gicv3/iidr/property
```

The same test through meson (builds what it needs first):

```bash
pyvenv/bin/meson test qtest-aarch64/arm-gicv3-iidr-test
```

This machine's test (M1-T04):

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

One test case only: append `-p /aarch64/rzv2l-smarc/gic/layout`.

All Arm qtests (several minutes):

```bash
pyvenv/bin/meson test --suite qtest-aarch64
```

`pyvenv/bin/meson test --suite qtest-aarch64 --list` lists the test names.

**A test that has never failed proves nothing** (AGENTS.md rule 7). The project checks each test by breaking the model on purpose (a *mutation*), rebuilding, and confirming the test goes red, then restoring the model. `docs/units/<unit>/tasks.md` lists the mutation for each task.

A mutation by hand, e.g. "`debugen` on bit 8":

```bash
cd qemu
cp hw/misc/renesas_rzg2l_sysc.c /tmp/sysc.c.orig                 # keep the original
sed -i 's/STAT_DEBUGEN, 9, 1/STAT_DEBUGEN, 8, 1/' hw/misc/renesas_rzg2l_sysc.c
cd ../build/qemu && ninja qemu-system-aarch64
QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-smarc-test
#   not ok /aarch64/rzv2l-smarc/sysc/boot-pins ... (0x00010100 == 0x00010200)
cp /tmp/sysc.c.orig ../../qemu/hw/misc/renesas_rzg2l_sysc.c     # restore
ninja qemu-system-aarch64                                       # rebuild the good model
```

Read the red line, not just the colour: the assertion that fails should be the one written for that mutation. `qemu-machine-modelling.md` §7 has the M1 results, including one that went red for the wrong reason.

## 4. Style check

QEMU's `checkpatch.pl` checks the coding style upstream expects. Run it inside `qemu/`.

Uncommitted changes (new files have to be announced to git first with `git add -N` so the diff includes them):

```bash
cd qemu
git add -N <new files>
git diff | scripts/checkpatch.pl --no-signoff -
```

Commits on the unit branch:

```bash
scripts/checkpatch.pl --no-signoff rzv2l-base..HEAD
```

`--no-signoff` because agent-written commits carry no `Signed-off-by:` (AGENTS.md "Commit style"). A new file triggers "does MAINTAINERS need updating?" until the RZ/V2L section in `MAINTAINERS` lists it.

## 5. Watching a device at work: trace points and logs

**Trace points** print one line each time a device callback runs. They are declared in a directory's `trace-events` file, e.g. `qemu/hw/misc/trace-events`:

```
renesas_rzg2l_sysc_read(uint64_t offset, uint64_t data, unsigned size) "offset 0x%" PRIx64 " data 0x%" PRIx64 " size %u"
```

At build time this line becomes a C function `trace_renesas_rzg2l_sysc_read()` that the device calls. They are off unless enabled with `-trace`:

```bash
./qemu-system-aarch64 -trace help | grep renesas          # list them
./qemu-system-aarch64 ... -trace 'renesas_rzg2l_sysc_*'   # enable by pattern
```

A live example on `virt` (the monitor's `xp` reads memory like a CPU would, so the GIC's callback runs):

```bash
printf 'xp /1wx 0x08000008\nquit\n' | ./qemu-system-aarch64 -M virt,gic-version=3 \
  -cpu cortex-a57 -S -display none -nodefaults -monitor stdio -trace gicv3_dist_read
```

```
gicv3_dist_read GICv3 distributor read: offset 0x8 data 0x43b size 4 secure 0
08000008: 0x0000043b
```

**Log masks** (`-d`) print problems the model reports with `qemu_log_mask()` (names from `qemu/util/log.c:513-532`):

| `-d` name | Reported by | Example in this project |
|---|---|---|
| `guest_errors` | `LOG_GUEST_ERROR`: the guest did something the hardware forbids | write to a read-only SYSC register |
| `unimp` | `LOG_UNIMP`: the guest touched something the model does not implement | read of a SYSC offset other than the three ID registers |
| `invalid_mem` | `LOG_INVALID_MEM`: QEMU's memory core refused an access before any device code ran | an 8- or 16-bit read of SYSC, which accepts only 32-bit accesses (`qemu/system/memory.c:1404`); **any access to an unmapped address** ("reason: rejected") |

Combine them: `-d unimp,guest_errors,invalid_mem`. Without `invalid_mem`, accesses to unmapped addresses are not logged at all. Checked with a qtest read of a hole on `virt`:

```bash
printf 'readl 0x0c000000\n' | ./qemu-system-aarch64 -M virt,gic-version=3 -display none \
  -nodefaults -accel qtest -qtest stdio -d invalid_mem
```

```
Invalid read at addr 0xC000000, size 4, region '(null)', reason: rejected
```

With `-d guest_errors` instead, the same read prints nothing.

## 6. Editor setup: VS Code with clangd

QEMU is too large for an editor to guess its include paths. Feed the editor the real compiler flags from `build/qemu/compile_commands.json` and go-to-definition, hover and find-references work across the fork.

Needs: the **clangd** extension (`llvm-vs-code-extensions.vscode-clangd`) and the `clangd` binary (`apt install clangd`). Open the repository root as the workspace and create `.vscode/settings.json` (`.vscode/` is gitignored, so this stays local):

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

Then run **Developer: Reload Window**. The background index takes a few minutes the first time (progress in the status bar).

- Why it is needed: clangd searches for `compile_commands.json` only in the file's parent directories and their `build/` subfolders. `build/qemu/` is not one of them, so without the setting clangd knows no include paths and every QEMU type is "unknown".
- A file not yet in the build (e.g. SYSC before T03) still works: clangd borrows the flags of a neighbouring file in the same directory.
- Check one file from the command line, without VS Code:

  ```bash
  clangd --compile-commands-dir=build/qemu --check=qemu/hw/misc/renesas_rzg2l_sysc.c 2>&1 | tail -1
  ```

  It ends with `All checks completed, 0 errors`.

Reading QEMU code in the editor:
- **Trace functions** (`trace_…`) jump to a generated header, `build/qemu/trace/trace-hw_misc.h`, not to `trace-events`: the build writes them from it (§5).
- **`REG32` / `FIELD` are macros**: hover over them to see the constants they produce (`qemu-machine-modelling.md` §3.1).
- An empty `~/.config/clangd/config.yaml` makes clangd log "Config should be a dictionary" on every start. It is harmless; delete the file or put `{}` in it.

## 7. Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `meson test` fails: "references functions or classes that don't exist … generated with an old version of meson" | the system `meson` is a different version from the one QEMU configured with | use `build/qemu/pyvenv/bin/meson` |
| a new device file never compiles | its Kconfig switch is not selected by any machine yet | expected until the SoC selects it; compile-check by hand (§2) |
| clangd: every QEMU type "unknown" | clangd cannot find `compile_commands.json` | §6 |
| checkpatch: "does MAINTAINERS need updating?" | new file not listed in `MAINTAINERS` | added once with the board (M1-T04) |
