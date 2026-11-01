# 🚶 Walkthrough: run each milestone yourself

This page takes you from a fresh clone to every milestone the model has reached, in order. Each step gives the command, what you should see, and where to read how it works. Run the commands from the repository root. A step takes a few seconds unless it says otherwise.

The words used here: **M1, M2, …** are the milestones ([milestones page](milestones.md)). **G0** is the plain mainline Linux kernel, and **G1** is Renesas's own kernel for the board. The **EVK** is the physical RZ/V2L board this model copies.

## 0. Build QEMU and the guests (once)

**Host tools.** The scripts call these programs (package names for Ubuntu 24.04):

```bash
sudo apt install git build-essential ninja-build python3-venv pkg-config \
    libglib2.0-dev libpixman-1-dev flex bison bc libssl-dev cpio \
    gcc-aarch64-linux-gnu device-tree-compiler e2fsprogs fdisk fakeroot \
    libslirp-dev ccache
```

**QEMU** (the fork is the `qemu/` submodule; a few minutes):

```bash
git clone --recurse-submodules https://github.com/umair-as/rzv2l-qemu.git
cd rzv2l-qemu
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs --cc="ccache cc"
ninja qemu-system-aarch64
cd ../..
```

Configure should report `slirp support: YES`. ccache caches repeated compilation;
inspect its counters with `ccache --show-stats`. Different source and debug paths
can prevent reuse between worktrees. New eval builds
also use it when installed. For an existing build, add `--cc="ccache cc"` to
its original configure options when no build is running; preserve the other
options from `build/qemu/config.status`. Review builds stay separate so their
mutations cannot affect your working build.

**The guests** (the kernels take a while: each is a full kernel build):

```bash
tests/guests/g0/build-kernel.sh       # G0: mainline Linux v6.12.59
tests/guests/g0/build-dtb.sh          # G0's device tree for the board
tests/guests/g0/build-initramfs.sh    # BusyBox shell, used by both kernels
tests/guests/g1/build-kernel.sh       # G1: Renesas's kernel and its device tree
tests/guests/sd/build-image.sh        # a 64 MiB SD card: ext4 data and root
```

Everything they produce goes to `tests/guests/out/` (not tracked by git).

## M1: the machine exists

The board is a QEMU machine called `rzv2l-smarc`: two Cortex-A55 CPUs, the GIC interrupt controller, 2 GiB of RAM and the timer.

```bash
build/qemu/qemu-system-aarch64 -M help | grep rzv2l
tests/probes/m1-skeleton/run.sh
```

You should see:

```
rzv2l-smarc          Renesas RZ/V2L SMARC EVK (2x Cortex-A55)
M1 skeleton probe
PASS Image load address: 0x0000000048200000
PASS MIDR_EL1: 0x00000000412fd050
PASS CNTFRQ_EL0: 24000000
PASS CPU_ON return: 0
...
RESULT: PASS (0 failures)
```

The probe is a small bare-metal program that runs on the emulated CPUs. It checks what Linux will later rely on: the CPU type, the 24 MHz timer, the start of the second CPU through PSCI. To look around the machine yourself, start it with `scripts/run.sh` and press Ctrl-A C for the QEMU monitor, then type `info mtree -f` (the memory map) or `info qtree` (the devices). Read more: [`learning/m1-machine-tour.md`](learning/m1-machine-tour.md).

## M2: the first character on the serial port

The serial port SCIF0 is the board's console. This probe writes to it:

```bash
tests/probes/hello-rzv2l/run.sh          # builds and runs the probe
build/qemu/qemu-system-aarch64 -M rzv2l-smarc -display none -nodefaults \
    -kernel tests/probes/hello-rzv2l/out/probe.Image \
    -semihosting-config enable=on,target=native -serial mon:stdio
```

The second command shows the serial output on your terminal:

```
Hello from RZ/V2L
RESULT: PASS (0 failures)
```

Read more: [`learning/m2-first-character.md`](learning/m2-first-character.md).

## M3: mainline Linux to a shell

```bash
scripts/run.sh -t g0
```

After about 20 seconds you get a banner and a shell:

```
  machine   Renesas SMARC EVK based on r9a07g054l2
  kernel    6.12.59
  cpus      0-1 (2 online)
rzv2l:~#
```

Try `cat /proc/cpuinfo`, `cat /proc/interrupts`, `sleep 5; cat /proc/uptime`. Ctrl-A X stops QEMU. The kernel and its device tree are the stock upstream ones, unmodified. To boot, it needed four device models: the clock controller, the OS timer, the pin controller and the interrupt controller. Read more: [`learning/m3-linux-shell.md`](learning/m3-linux-shell.md).

## M4: Renesas's kernel, the watchdog, U-Boot's device-tree edit

```bash
scripts/run.sh                 # G1 is the default
```

At the shell, start the watchdog and let it expire:

```bash
watchdog -T 3 -t 1000 /dev/watchdog; sleep 1; killall -9 watchdog
```

About 3 seconds later the board resets and boots again. After the second boot, `devmem 0x11010b10` prints `0x00000001`: the clock controller recorded that watchdog 0 caused the reset.

QEMU also makes the device-tree edit the board's U-Boot makes when it boots from the SD card. To see the device tree as Linux receives it:

```bash
scripts/run.sh --dumpdtb
fdtget -t x build/run/g1/qemu.dtb /soc/mmc@11c00000 vqmmc-supply    # 74
```

Read more: [`learning/m4-vendor-kernel.md`](learning/m4-vendor-kernel.md).

## M5: an SD card with ext4

The guest writes to the card image, so start from a copy:

```bash
cp tests/guests/out/sd/sd.img build/sd-try.img
scripts/run.sh --sd build/sd-try.img          # add -t g0 for mainline
```

At the shell:

```bash
dmesg | grep mmc0                    # mmc0: new high speed SD card ...
mkdir -p /mnt; mount /dev/mmcblk0p1 /mnt; ls /mnt
dd if=/dev/urandom of=/mnt/f.bin bs=1k count=2048; md5sum /mnt/f.bin
sync; umount /mnt
```

Stop QEMU (Ctrl-A X) and read the file back from the host. The MD5 matches the one the guest printed:

```bash
dd if=build/sd-try.img of=build/p1.img bs=512 skip=2048 count=32768 status=none
debugfs -R "dump /f.bin build/f.bin" build/p1.img; md5sum build/f.bin
```

Boot again with the same image, and the file is still there. Add `-- -trace 'renesas_sdhi_*' -D build/sdhi-trace.log` to the `run.sh` line to log every access to the SD host. Read more: [`learning/m5-storage.md`](learning/m5-storage.md).

### User space from the card

The card's second partition holds a root file system with the same BusyBox. Boot it without the initramfs, with the command line the board's U-Boot passes:

```bash
scripts/run.sh --sd build/sd-try.img -n -a "rw rootwait earlycon root=/dev/mmcblk0p2"
```

The kernel mounts the card and runs its init:

```
VFS: Mounted root (ext4 filesystem) on device 179:2.
Run /sbin/init as init process
  root file system on /dev/mmcblk0p2, boot 1 from this card
SD-ROOT: ready, root /dev/mmcblk0p2, boot 1
```

Write something, then restart the board from inside: `reboot` resets it in the same QEMU, and the card counts boot 2. `poweroff` remounts the root read-only, powers the board down and ends QEMU. Start `run.sh` again with the same image and the count and your file are still there. On the host, the journal needs no recovery and `e2fsck` finds the root clean:

```bash
dd if=build/sd-try.img of=build/p2.img bs=512 skip=34816 status=none
dumpe2fs -h build/p2.img | grep features   # no needs_recovery
e2fsck -fn build/p2.img
```

## M6: Ethernet

`scripts/run.sh` puts ETH0 on QEMU's user-mode network (slirp, from `libslirp-dev` in step 0): a private network inside QEMU, with a DHCP server and the host reachable as `10.0.2.2`. It touches no host interface and needs no root. It is the cable on the board's ETH0; without it (`--no-net`), the board's boot arguments (`ip=on`) make Linux wait two minutes for a link at every boot. A `build/qemu` configured before `libslirp-dev` was installed has no user networking (QEMU stops with "network backend 'user' is not compiled"): run step 0's `configure` and `ninja` again.

In a second terminal, serve a file from the host: `python3 -m http.server -b 127.0.0.1 8000 -d docs`. Then boot:

```bash
scripts/run.sh -t g0         # or -t g1
```

At the shell:

```bash
dmesg | grep -e ravb -e KSZ9131 -e 'Link is Up'   # both channels, PHY at address 7, 1Gbps/Full
dmesg | grep -A1 'IP-Config: Complete'            # the kernel's own DHCP (ip=on in the boot arguments)
udhcpc -i eth0 -n -q -s /dev/null      # BusyBox: lease of 10.0.2.15 obtained from 10.0.2.2
wget -O /tmp/w.md http://10.0.2.2:8000/walkthrough.md; sha256sum /tmp/w.md
```

The hash matches `sha256sum docs/walkthrough.md` on the host. To pull the cable, open the QEMU monitor (Ctrl-A C), type `set_link net0 off`, and return with Ctrl-A C: the guest prints `eth0: Link is Down`; `set_link net0 on` brings it back at 1 Gb/s. ETH1 has no backend, so it has no cable. Read more: [`learning/m6-network.md`](learning/m6-network.md).

## Run every check at once

```bash
tests/acceptance/m6/run.sh       # several minutes: it boots both kernels several times
```

It runs the acceptance checks of M1 to M6 in turn and ends with `M6 ACCEPTANCE: PASS`. The qtests (register-level tests of each device) run with `cd build/qemu && QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-sdhi-test`, and the same for the other `rzv2l-*-test` files ([`learning/building-and-testing.md`](learning/building-and-testing.md) §3).

## Options of `scripts/run.sh`

| Option | Effect |
|---|---|
| `-t g0` / `-t g1` | mainline or Renesas kernel (default `g1`) |
| `--sd IMAGE` | an SD card in the module slot (`/dev/mmcblk0`) |
| `--no-net` | no network on ETH0 (by default ETH0 is on QEMU user networking, `net0`) |
| `-b N` | boot mode pins 0-5 (0: SD card, the default; 1: eMMC) |
| `-a "ARGS"` | kernel command line instead of the device tree's |
| `--dumpdtb` | write the device tree QEMU gives Linux, then stop |
| `-g` | wait for gdb on port 1234 |
| `--dry-run` | print the QEMU command |
| `-- …` | pass the rest to QEMU |

`scripts/run.sh --help` lists them all.
