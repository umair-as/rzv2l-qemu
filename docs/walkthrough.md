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
tests/guests/fw/build-tf-a.sh         # the board's TF-A BL31 (firmware mode, M7)
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
dd if=build/sd-try.img of=build/p1.img bs=512 skip=8192 count=32768 status=none
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
SD-ROOT: ready, root /dev/mmcblk0p2, boot 1, partuuid 525a0001-02, card sd
```

Write something, then restart the board from inside: `reboot` resets it in the same QEMU, and the card counts boot 2. `poweroff` remounts the root read-only, powers the board down and ends QEMU. Start `run.sh` again with the same image and the count and your file are still there. On the host, the journal needs no recovery and `e2fsck` finds the root clean:

```bash
dd if=build/sd-try.img of=build/p2.img bs=512 skip=40960 status=none
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

## M7: the board's own firmware

In firmware mode the board's TF-A BL31 runs at EL3 and is the PSCI firmware, as on the board: QEMU's built-in PSCI is off. QEMU does BL2's job before it (loads BL31 and the kernel, leaves BL2's parameters), so the boot ROM, BL2 and U-Boot do not run. There is no initramfs, so boot from the card's root:

```bash
cp tests/guests/out/sd/sd.img build/sd-try.img
scripts/run.sh -f --sd build/sd-try.img -a "rw rootwait earlycon root=/dev/mmcblk0p2"
```

BL31 prints first, and the kernel finds it:

```
NOTICE:  BL31: v2.10.5(release):2.10.5/rz_1.1.0
ERROR:   Error initializing runtime service opteed_fast
[    0.000000] psci: PSCIv1.1 detected in firmware.
[    0.000000] psci: SMC Calling Convention v1.4
[    0.099643] smp: Brought up 1 node, 2 CPUs
```

The OP-TEE line is expected: there is no OP-TEE yet. In direct mode the kernel reports SMC Calling Convention v1.0 (QEMU's PSCI); v1.4 is BL31's, as on the board. At the shell, take CPU1 down and up again; BL31 drives the SoC's reset and power registers to do it:

```bash
echo 0 > /sys/devices/system/cpu/cpu1/online   # psci: CPU1 killed
echo 1 > /sys/devices/system/cpu/cpu1/online   # CPU1: Booted secondary processor
reboot                                         # BL31 resets the board through WDT0
```

After `reboot` the BL31 banner comes again in the same QEMU. `poweroff` stops the kernel but not QEMU: this BL31 does not implement PSCI `SYSTEM_OFF`, and the board is not powered off either. Quit with Ctrl-A X.

### OP-TEE and U-Boot after BL31

The rest of the board's boot chain after BL2: BL31 starts OP-TEE (rebuilt from the vendor sources without the closed crypto engine) in the secure world, then the vendor U-Boot, which loads the kernel and its device tree from `/boot` on the card and starts it. QEMU stands in for BL2 only. Build the two images once:

```bash
tests/guests/fw/build-optee.sh
tests/guests/fw/build-u-boot.sh
tests/guests/sd/build-image.sh           # the card gets /boot/Image, the DTB and U-Boot's saved environment
cp tests/guests/out/sd/sd.img build/sd-try.img
scripts/run.sh -u --sd build/sd-try.img
```

On the console, in order: the BL31 banner; `I/TC: Primary CPU switching to normal world boot` (OP-TEE); `U-Boot 2024.07-g4eebfbaa4e`, `DRAM:  1.9 GiB` and `SF: Detected mt25qu512a with page size 256 Bytes, erase size 4 KiB, total 64 MiB` (the module's QSPI flash, the same line as on the board); `Loading Environment from MMC... Reading from MMC(0)... OK`: the card carries the project's boot configuration in U-Boot's environment block (`tests/guests/sd/boot.env`); after a 2-second countdown `25963008 bytes read`; then Linux with `psci: Trusted OS migration not required` (BL31 answers through OP-TEE, as on the board) and both CPUs. The configuration names the root by the partition's identifier, `root=PARTUUID=525a0001-02`, not by its Linux name, so the shell comes up whichever name Linux gives the card; the prompt line says both, e.g. `SD-ROOT: ready, root /dev/mmcblk1p2, boot 1, partuuid 525a0001-02, card sd`. U-Boot leaves the watchdog running with 60 s, but Linux stops its clock when no program uses it, so the board does not reset, as on the real board. At the shell try CPU1 off and on and `reboot` as above. To see the vendor's own boot instead, clear the card's saved environment: `python3 tests/guests/sd/uboot-env.py clear build/sd-try.img`. U-Boot then says `bad CRC, using default environment` and passes `root=/dev/mmcblk0p2`; about half such boots get the card as `mmcblk1` (the vendor device tree does not fix the names) and stop at `Waiting for root device /dev/mmcblk0p2...` for ever, so quit (Ctrl-A X). One thing can go wrong under emulation either way: a boot that hangs right after OP-TEE's last line, or in the middle of a U-Boot line, lost a console race; quit and start again. That race is more frequent when the host is busy, so run on an otherwise idle machine; this makes a hang rarer, it does not rule it out. Read more: [`units/M7-optee-uboot/spec.md`](units/M7-optee-uboot/spec.md).

### Linux and OP-TEE

The vendor kernel cannot talk to OP-TEE: it is built without the driver, and its device tree has no `/firmware/optee` node. The project's TEE kernel adds both (the vendor source, unchanged, with two config options and a small device-tree overlay), and the TEE card carries it with the OP-TEE client and an example trusted application:

```bash
tests/guests/g1-tee/build-kernel.sh
tests/guests/g1-tee/build-optee-user.sh
tests/guests/sd/build-image.sh --tee
cp tests/guests/out/sd/sd-tee.img build/sd-try.img
scripts/run.sh -u --sd build/sd-try.img
```

The firmware is the same as above. At the shell:

```bash
dmesg | grep optee:                # probing, revision 4.8 (82a5cd3b...), initialized driver
ls /dev/tee*                       # /dev/tee0 /dev/teepriv0
tee-supplicant -d                  # loads trusted applications from /lib/optee_armtz
optee_example_hello_world          # Invoking TA to increment 42 ... TA incremented value to 43
```

The trusted application runs in OP-TEE, in the secure world, and logs `I/TA: Hello World!` on the console itself. OP-TEE warns `Failed to get monotonic counter for REE FS`: there is no RPMB, so its secure storage has no rollback counter. There is no hardware crypto or random number generator either: the board's TSIP is closed, and OP-TEE is built without it. Read more: [`units/M7-optee-linux/spec.md`](units/M7-optee-linux/spec.md).

### The QSPI flash

The SMARC module carries a 64 MiB QSPI NOR flash on the SoC's SPI multi I/O bus controller. U-Boot finds it at every start (the `SF: Detected` line above), and the vendor kernel registers the three partitions of its device tree. Give it an image to keep what is written; without one it starts erased and forgets at exit. Start erased, then stop U-Boot within its 2-second countdown (any key):

```bash
head -c 64M /dev/zero | tr '\000' '\377' > build/qspi.img
cp tests/guests/out/sd/sd.img build/sd-try.img
scripts/run.sh -u --sd build/sd-try.img -- -drive if=mtd,format=raw,file=build/qspi.img
```

At the U-Boot prompt and then in Linux:

```bash
sf probe                           # SF: Detected mt25qu512a ... total 64 MiB
sf read 0x48000000 0 0x100; md.b 0x48000000 0x10    # ff ff ...: erased
boot                               # on to Linux
cat /proc/mtd                      # mtd0 "bl2", mtd1 "fip", mtd2 "user"
cat /sys/bus/spi/devices/spi1.0/spi-nor/partname     # mt25qu512a
echo hello-flash | dd of=/dev/mtdblock2 conv=fsync
```

Quit (Ctrl-A X) and look at the image: `dd if=build/qspi.img bs=1 skip=$((0x2000000)) count=12` prints `hello-flash`, and a new start reads it back from `/dev/mtdblock2`. Read more: [`units/M7-rpc-spinor/spec.md`](units/M7-rpc-spinor/spec.md).

## Run every check at once

```bash
tests/acceptance/m7/run.sh       # several minutes: it boots both kernels several times
```

It runs the acceptance checks of M1 to M6 in turn, then the firmware-mode boot, the boot through OP-TEE and U-Boot, Linux calling a trusted application, the root chosen by PARTUUID (kernel from one card, root from the other; a missing PARTUUID stops the boot visibly), and the QSPI flash under U-Boot and Linux (reads of a random image, a write across a reboot and a QEMU restart), and prints `M7 ACCEPTANCE: PASS`. Then it boots the vendor's unchanged U-Boot command twice and prints a separate line, `VENDOR-DEFAULT COMPATIBILITY: PASS` or `FAIL (n of 2 boots lost their root ...)`: that line does not change the acceptance result, and it can fail on the SD name race above. The qtests (register-level tests of each device) run with `cd build/qemu && QTEST_QEMU_BINARY=./qemu-system-aarch64 ./tests/qtest/rzv2l-sdhi-test`, and the same for the other `rzv2l-*-test` files ([`learning/building-and-testing.md`](learning/building-and-testing.md) §3).


## Options of `scripts/run.sh`

| Option | Effect |
|---|---|
| `-t g0` / `-t g1` | mainline or Renesas kernel (default `g1`) |
| `--sd IMAGE` | an SD card in the module slot (`/dev/mmcblk0`) |
| `--no-net` | no network on ETH0 (by default ETH0 is on QEMU user networking, `net0`) |
| `-b N` | boot mode pins 0-5 (0: SD card, the default; 1: eMMC) |
| `-f` | firmware mode: the board's TF-A BL31 is the PSCI firmware; no initramfs |
| `-u` | the boot chain after BL2: BL31, OP-TEE and U-Boot, which loads the kernel from the card; needs `--sd` |
| `-a "ARGS"` | kernel command line instead of the device tree's |
| `--dumpdtb` | write the device tree QEMU gives Linux, then stop |
| `-g` | wait for gdb on port 1234 |
| `--dry-run` | print the QEMU command |
| `-- …` | pass the rest to QEMU |

`scripts/run.sh --help` lists them all.
