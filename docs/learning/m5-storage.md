# M5: storage

> **Context.** Milestone M5 (spec [§17](../spec/project.md#17-milestones)): an SD card with an ext4 file system, used by the unchanged Linux driver. Unit M5-sdhi: [spec](../units/M5-sdhi/spec.md), [tasks](../units/M5-sdhi/tasks.md), register evidence [`../research/sdhi.md`](../research/sdhi.md). Unit M5-sd-rootfs (user space from the card, §9): [spec](../units/M5-sd-rootfs/spec.md), [tasks](../units/M5-sd-rootfs/tasks.md). The manual chapter is §40 (SD/MMC host interface). Linux paths are under linux v6.12.59 `drivers/mmc/`.

This page follows one SD card read from the card up to the block layer, and shows where the hardware, the Linux driver and the QEMU model each do their part. It is written for two readers. If you know embedded Linux, it shows how an SD host driver is built and what its DMA engine needs. If you are new to QEMU, it shows how a storage controller is modelled. Sections 5 and 6 end with what to take away for a driver of your own, and section 7 for a model.

## 1. Four layers

An SD read passes through four layers. Each layer has one job and talks only to its neighbours.

```
  ext4, page cache          files and pages
        |
  block layer, mmcblk       requests of sectors     drivers/mmc/core/block.c, queue.c
        |
  MMC core                  the SD protocol          drivers/mmc/core/core.c, sd.c
        |  struct mmc_request: cmd, data, stop
  host driver               the controller           drivers/mmc/host/tmio_mmc_core.c,
        |  registers, DMA                             renesas_sdhi_core.c,
  SD host (SDHI)                                      renesas_sdhi_internal_dmac.c
        |  CMD line, DAT0-3, CLK
  SD card                   flash and its controller
```

- **The card** has its own controller. It answers commands on the CMD line and moves data on the DAT lines. It does not know Linux.
- **The SD host** (SDHI on this SoC) turns register writes into command sequences on the bus, and moves the data between the bus and memory.
- **The MMC core** knows the SD protocol: which commands identify a card, how to switch it to 4 bits and high speed, how to read blocks. It hands the host driver one `struct mmc_request` at a time (`core/core.c:335` `mmc_start_request`).
- **The host driver** knows the registers. It runs the request on the hardware and reports the result (`core/core.c:139` `mmc_request_done`).

The protocol knowledge lives in the core, and the register knowledge lives in the host driver. That split is what makes a new host driver small.

## 2. The SD protocol in one boot

The MMC core finds the card with a fixed sequence of commands (`core/sd.c:1415` `mmc_sd_init_card`). Each command is 48 bits on the CMD line: a 6-bit index and a 32-bit argument. Most commands get a 48-bit response. CMD2 and CMD9 get a 136-bit response (the "R2" type).

| Step | Command | Response | What it does |
|---|---|---|---|
| reset | CMD0 | none | every card goes to the idle state |
| voltage | CMD8, argument `0x1AA` | R7 | "can you run at 2.7-3.6 V?" An old card does not answer |
| power up | CMD55 + ACMD41, repeated | R3 (the OCR) | the card powers up; bit 31 says "ready", bit 30 "high capacity" |
| identity | CMD2 | R2 (CID) | manufacturer, product name, serial number |
| address | CMD3 | R6 | the card proposes a relative card address (RCA) |
| select | CMD7 with the RCA | R1b | the card moves to the "transfer" state |
| configure | ACMD51 (SCR), CMD6, ACMD6 | R1 + data | bus width 4, high-speed timing |
| read | CMD17 (one block), CMD18 (many) | R1 + data | the data follows on DAT0-3 |
| stop | CMD12 | R1b | ends a multi-block read or write |

The card has a state machine. CMD18 is accepted in the "transfer" state (4) and moves the card to "data" (5); CMD12 brings it back. The R1 response carries the state in bits 12:9, which you can see in the trace in §4.

Linux shows what it negotiated. On the model:

```
$ cat /sys/kernel/debug/mmc0/ios
clock:          50000000 Hz
bus width:      2 (4 bits)
timing spec:    2 (sd high-speed)
signal voltage: 0 (3.30 V)
$ cat /sys/class/mmc_host/mmc0/mmc0:*/cid
aa585951454d552101deadbeef006200
```

The CID begins with the manufacturer ID `0xaa`, the OEM ID "XY" and the product name "QEMU!" (`58 59` and `51 45 4d 55 21` in ASCII). The EVK shows the same clock, width, timing and voltage for its 128 GB card ([EVK evidence §8](../evidence/EVK-2026-10-30-linux.md)). So the model and the board run the same mode.

Note: the QEMU card here is 64 MiB, a standard-capacity (SDSC) card: its CSD starts with `00`, CSD version 1. An SDSC card takes byte addresses, so CMD18 for sector `0x338` has the argument `0x00067000`. The EVK's card is SDXC and takes sector numbers. The MMC core handles this difference, not the host driver.

## 3. What the SD host does

The SD host sits between the CPU and the card. It does two jobs: it sends commands to the card, and it moves the data. This section explains both jobs in plain terms. The register names come from the manual (§40), but you need only a few of them.

### 3.1 Sending one command

To send a command, the driver writes two registers:

1. the 32-bit argument into `SD_ARG`;
2. the command number and its type into `SD_CMD`.

The write to `SD_CMD` starts the work. The host sends the command on the CMD line and waits for the card's answer. While it works, a "busy" bit (`CBSY`) reads 1. When the answer has arrived, the host puts it in a response register (`SD_RSP10`) and sets a flag, "response end".

The driver does not poll that flag. It enables an interrupt for it, and goes to do other work. When the flag sets, the interrupt fires and the driver reads the response.

If no card answers, the host waits a short time and then sets two flags instead: "response end" and "response timeout". That is how "no card in the slot" looks to the driver.

One detail surprises most people. To clear a flag on this host, you write **0** to its bit and **1** to all the other bits. Writing 1 leaves a flag as it is. Most devices work the other way round ("write 1 to clear"). So to clear only "response end" (bit 0), the driver writes `0xfffe`.

### 3.2 Moving the data: two ways

A command such as "read 8 blocks" (CMD18) is followed by data: 8 × 512 bytes from the card. The host keeps the data in a small internal buffer. From there it can go to memory in two ways.

- **The CPU copies it.** The driver reads the buffer through one register, the data port `SD_BUF0`, 2 or 8 bytes at a time. A flag tells it when a block is ready. This is simple, but the CPU spends its time copying, and it gets one interrupt per block.
- **The DMA engine copies it.** DMA means "direct memory access": a small engine in the SD host copies the data into memory itself. The CPU only says where to put the data, and gets one interrupt at the end.

Linux uses the DMA engine for almost every request on this SoC. It uses the data port only for buffers that the DMA engine cannot reach (§5).

### 3.3 The DMA engine

The SD host has its own DMA engine, built in. The driver gives it three things:

1. **where** the data goes in memory: a physical address (`DM_DTRAN_ADDR`);
2. **which way** it goes: from the card to memory, or the reverse (`DM_CM_DTRAN_MODE`);
3. **go**: one bit (`DM_START`).

The engine does not need a length. The command already says how many blocks of which size. When the last byte is in memory, the engine sets its own "done" flag (`DTRANEND`) and raises the same interrupt.

So one read ends with two "done" flags: the host's "access end" (the data and the final stop command are over) and the DMA engine's "done". The driver waits for both. Section 4 shows why.

## 4. Following one read

The model can log every register access (`-trace 'renesas_sdhi_*'`). This is a shortened log of Linux reading 4 KiB, which is 8 blocks, from the card:

```
SD_SIZE          = 512             block size
SD_SECCNT        = 8               number of blocks
CC_EXT_MODE      = DMA on          the buffer goes to the DMA engine
DM_CM_DTRAN_MODE = card -> memory
DM_DTRAN_ADDR    = 0x50129000      where in memory
SD_ARG           = 0x00067000      which block on the card
SD_CMD           = CMD18           "read multiple blocks"
      ... interrupt: response end
SD_INFO1         = clear "response end"
SD_RSP10         = 0x0900          the card's answer: "transfer state, ready"
DM_START         = 1               now the DMA engine runs
      ... the host reads 8 blocks, the engine writes them to memory,
      ... the host sends CMD12 ("stop")
      ... interrupt: access end, and DMA done
SD_INFO1         = clear "access end"
DM_CM_INFO1      = clear "DMA done"
```

Read it as a story in four steps:

1. **Prepare.** The driver writes the block size, the number of blocks, and the DMA engine's address and direction. Nothing happens yet.
2. **Send the command.** Writing `SD_CMD` sends CMD18. The card answers, and the interrupt for "response end" fires.
3. **Start the DMA.** Only now does the driver write `DM_START`. It waits for the response first: if the card had refused the command, there would be no data to move, and the DMA engine must not run.
4. **Finish.** The host reads the 8 blocks and sends CMD12 to stop the card. The DMA engine writes the blocks to memory. Then both "access end" and "DMA done" are set. The interrupt handler clears both and tells the MMC core that the request is complete.

Why two "done" flags? The host and the DMA engine are two machines that finish at slightly different times, and either can be first. The driver therefore records each event as it comes, and completes the request when it has seen both. This pattern fits any device that has a protocol engine and a separate DMA engine.

A second log shows a limit of this DMA engine. One `dd` read of 64 KiB (`bs=64k iflag=direct`) became 16 separate CMD18 commands of 8 blocks each, and each went to a different place in memory: `0x5021e000`, `0x4a8f8000`, `0xbb8c0000`, and so on. The 64 KiB buffer is contiguous for the program, but its 4 KiB pages are scattered in physical memory. The DMA engine accepts one address per request, not a list of pieces (a "scatter-gather list"). So Linux sends one request per page.

## 5. DMA and the kernel

A DMA engine works with physical memory. It does not see the CPU's virtual addresses, and it does not see the CPU's caches. Three things follow, and the Linux DMA API handles all three for a driver.

**Addresses.** The driver never gives the engine a pointer. It calls `dma_map_sg()` with the request's pages and gets "bus addresses" back. On this SoC there is no IOMMU in front of the SD host, so a bus address is simply the physical address, for example `0x50129000` in §4.

**Caches.** The CPU keeps copies of memory in its caches, and the DMA engine does not know about them. On this SoC the two are not kept in step by hardware: the device tree does not mark the SD host as "dma-coherent". So before a write to the card, the CPU's cached data must be written out to memory. After a read from the card, the CPU's old cached copy must be thrown away, or the CPU reads stale data. `dma_map_sg()` and `dma_unmap_sg()` do both.

**Buffers the engine cannot use.** Some buffers do not suit the engine, for example because they are small and not aligned. The DMA API can then copy the data through a "bounce buffer" that does suit it. On this kernel, small `kmalloc` buffers such as the card's 8-byte SCR register go that way.

The SD host adds one rule of its own: the DMA engine needs buffers aligned to 128 bytes. The driver checks the address after mapping. If it is not aligned, the driver uses the data port for that request instead. Normal file reads and writes use whole pages, which are always aligned, so this fallback is rare.

What to take away for your own driver:

- Map every buffer with the DMA API before the engine touches it, and unmap it after. Never compute a physical address yourself.
- Tell the MMC core what the engine can do: how many separate pieces of memory it takes per request (`max_segs`, here 1), the largest piece, and the largest number of blocks. The core then only sends requests the engine can handle.
- If the engine has an alignment rule, check it after mapping, and keep a CPU path for the rest.
- If a request ends with two hardware events, record each and complete on the second.

## 6. Writing an SD host driver

The MMC core does the hard part: it knows the SD protocol, finds the card, picks the bus width and speed, and turns block reads into commands. A host driver only has to make the controller run one request at a time. That is a small, well-defined job.

### 6.1 What the MMC core asks of you

The core calls the driver through a table of functions, `struct mmc_host_ops`. Three of them matter most:

- **`request`**: run one `struct mmc_request`. It holds a command, and for data the buffer and an optional stop command. The driver starts the work and returns at once. When the work is done, usually in the interrupt handler, it calls `mmc_request_done()`.
- **`set_ios`**: set the bus clock, the bus width (1, 4 or 8 bits), the power and the signal voltage. The core calls it as the card's identification goes on, for example 400 kHz at first and 50 MHz later.
- **`get_cd`**: "is a card in the slot?", for a slot where cards come and go.

This is the shape of a minimal host driver, in outline (not code from the kernel):

```c
static void my_request(struct mmc_host *mmc, struct mmc_request *mrq)
{
	struct my_host *h = mmc_priv(mmc);

	h->mrq = mrq;
	if (mrq->data)
		my_setup_dma(h, mrq->data);	/* dma_map_sg, address, direction */
	writel(mrq->cmd->arg, h->base + MY_ARG);
	writel(my_cmd_bits(mrq->cmd), h->base + MY_CMD);	/* starts the work */
}

static irqreturn_t my_irq(int irq, void *data)
{
	struct my_host *h = data;
	u32 status = readl(h->base + MY_STATUS);

	my_ack(h, status);
	if (status & MY_RESPONSE_END)
		my_read_response(h, h->mrq->cmd);	/* into cmd->resp[] */
	if (status & MY_TIMEOUT)
		h->mrq->cmd->error = -ETIMEDOUT;
	if (my_request_finished(h, status)) {
		my_unmap_dma(h);			/* dma_unmap_sg */
		mmc_request_done(h->mmc, h->mrq);
	}
	return IRQ_HANDLED;
}
```

### 6.2 What probe does

At probe, the driver prepares the controller and tells the core what it can do:

1. **Get the resources** from the device tree: the registers, the interrupts, the clocks, the reset line and the pin settings.
2. **Get the supplies.** `mmc_regulator_get_supply()` finds `vmmc`, the card's power, and `vqmmc`, the voltage of the signal lines.
3. **Describe the host.** `mmc_of_parse()` reads the device tree's `bus-width`, `non-removable`, `max-frequency` and the speed modes. The driver adds what only it knows, such as the limits of its DMA engine (§5).
4. **Register.** `mmc_add_host()` hands the host to the core. The core then looks for a card by itself and, when it finds one, creates `/dev/mmcblk0`.

### 6.3 How the Renesas driver is split

The Renesas driver puts these pieces in three files. The same split is a good plan for a driver of your own:

| File | What it holds |
|---|---|
| `tmio_mmc_core.c` | the parts every TMIO-family host shares: the command sequence, the data port, the interrupt handler, the `mmc_host_ops` |
| `renesas_sdhi_core.c` | what Renesas added: clocks and reset, the registers that depend on the hardware version, the bus tuning for the fastest modes |
| `renesas_sdhi_internal_dmac.c` | the built-in DMA engine, and the table that matches each SoC (`renesas,rzg2l-sdhi` for this one) |

So a new SoC with the same controller needs only an entry in the match table. A controller with a different DMA engine needs a new third file.

## 7. Modelling the SD host in QEMU

### 7.1 The card is already there

QEMU has a complete SD card model (`hw/sd/sd.c`): its state machine, its registers (CID, CSD, SCR), and a disk image behind it. So a new SD host model needs only the controller. The controller talks to the card through an `SDBus`, with a few calls:

| QEMU call | What the real host does |
|---|---|
| `sdbus_do_command()` | send a command on the CMD line; the result is the length of the answer, 0 for none |
| `sdbus_read_data()`, `sdbus_write_data()` | move data bytes on the DAT lines |
| `sdbus_data_ready()` | ask "does the card have data to send?" |
| `sdbus_get_inserted()` | read the card detect switch |

### 7.2 The controller model

The model of the SD host is `hw/sd/renesas_sdhi.c`. In outline, a write to `SD_CMD` does this (simplified from the model):

```c
static void start_command(RenesasSDHIState *s)
{
    SDRequest req = { .cmd = s->sd_cmd & 0x3f, .arg = s->sd_arg };
    uint8_t rsp[16];
    size_t len = sdbus_do_command(&s->sdbus, &req, rsp, sizeof(rsp));

    if (len == 0) {
        s->sd_info2 |= ERR6;                 /* the card did not answer */
    } else {
        s->sd_rsp10 = ldl_be_p(rsp);         /* a 48-bit response */
    }
    s->sd_info1 |= INFO0;                    /* response end */
    update_irq(s);
}
```

The DMA engine is a loop. On `DM_START`, it reads each block from the card and writes it to guest memory with `dma_memory_write()` (or the reverse for a write). These calls go through an address space, which is QEMU's view of memory as the device sees it. So the model does not need to know anything about the guest's pages or caches.

Three more parts complete the model:

- **The interrupt.** One function computes the interrupt line from all the flags and masks. The model calls it after every register access, so the line can never be stale.
- **Partial accesses.** The driver writes a 32-bit value as two 16-bit halves at offsets 8 bytes apart. The model therefore lets each access read or write part of an 8-byte register.
- **The pins.** The card detect and write protect bits come from switches in the card slot. On the board, SDHI0's switches are not connected to the SD host (see §10). The model has a property for each, set by the SoC.

### 7.3 Two design choices

**No timing.** On the board, sending a command and moving the data takes microseconds to milliseconds. The model does it all within the register write that starts it, and raises the interrupt before the write returns. Linux does not depend on time passing here, so this works. The cost is that the host's own timeout counter never fires. The spec records that.

**Both orders for DMA.** Linux switches the buffer to the DMA engine before it sends the command. The manual's own example does it after the response. The model accepts both: in the second case, the first block is already waiting in the buffer when `DM_START` comes, and the DMA engine takes it from there.

What to take away for your own model:

- Reuse QEMU's card model. Write the controller, and talk to the card only through the `SDBus` calls.
- Write the DMA engine with `dma_memory_read()` and `dma_memory_write()` on an address space that the SoC gives the device.
- Compute the interrupt line in one place, from all flags and masks.
- Test with a real card image: drive the controller from a qtest, then check the written blocks in the image file on the host.

## 8. Try it

You need the guests (`docs/learning/building-and-testing.md` §8) and the SD image (`tests/guests/sd/build-image.sh`).

1. Copy the image, because the guest can write to it:

   ```
   cp tests/guests/out/sd/sd.img build/sd-try.img
   ```

2. Boot with the card and trace the SDHI:

   ```
   scripts/run.sh -t g0 -d none --sd build/sd-try.img \
       -- -trace 'renesas_sdhi_*' -D build/sdhi-trace.log
   ```

3. At the prompt, look at the card and read four blocks without the page cache:

   ```
   mount -t debugfs none /sys/kernel/debug
   cat /sys/kernel/debug/mmc0/ios
   cat /sys/class/mmc_host/mmc0/mmc0:*/cid /sys/class/mmc_host/mmc0/mmc0:*/scr
   dd if=/dev/mmcblk0 of=/dev/null bs=4k count=4 skip=100 iflag=direct
   ```

4. Stop QEMU with Ctrl-A X. Find the requests with `grep -n CMD18 build/sdhi-trace.log`, and compare one with §4.

## 9. User space from the card

Until now the shell came from an initramfs: an archive that QEMU loads into RAM next to the kernel. On the board, Linux instead mounts its root file system from the SD card. This section shows that boot, and how QEMU handles the power-off and the reset that end it.

### 9.1 The root on a block device

The board's U-Boot passes `rw rootwait earlycon root=/dev/mmcblk0p2` (EVK capture, [unit spec](../units/M5-sd-rootfs/spec.md#evidence)). QEMU passes the same line with `-append` and no `-initrd`:

```
[    6.527289] VFS: Mounted root (ext4 filesystem) on device 179:2.
[    6.582336] Run /sbin/init as init process
```

- **`root=/dev/mmcblk0p2`** names partition 2 of the card on SDHI0. The name is stable only because of the `mmc0` alias (§11).
- **`rootwait`** makes the kernel wait for the device (`wait_for_root`, linux `init/do_mounts.c:413`). The SD card appears only when its probe finishes, after the kernel is ready to mount.
- **`rw`** mounts the root read-write at once. Nothing in this image checks the file system at boot.
- With no initramfs, the kernel mounts `devtmpfs` on the card's `/dev` (`init/do_mounts.c:493`, `CONFIG_DEVTMPFS_MOUNT=y`). Then it runs `/sbin/init` from the card (`init/main.c:1537`).

The card's `/sbin/init` is BusyBox `init`. It reads `/etc/inittab`, runs `/etc/init.d/rcS` once, and keeps a shell on the console. The image script writes these files ([`build-image.sh`](../../tests/guests/sd/build-image.sh)).

### 9.2 Power-off and reset

A clean shutdown has two halves: the guest leaves the file system consistent, then the firmware turns the board off. In direct mode, QEMU's built-in PSCI is the firmware.

1. `poweroff` sends a signal to BusyBox `init`. `init` runs the `shutdown` lines of `inittab` first (`init/init.c:763` in BusyBox 1.36.1). Here that line is `umount -a -r`. The root is busy, so `umount` remounts it read-only.
2. `init` stops all processes, calls `sync()` and then `reboot()` (`init/init.c:746`).
3. The kernel prints `reboot: Power down` and calls PSCI `SYSTEM_OFF`. QEMU requests a shutdown, and the process exits (`qemu/target/arm/tcg/psci.c:131`).

`reboot` takes the same path to PSCI `SYSTEM_RESET`. QEMU then resets the machine instead of exiting (`psci.c:123`). The reset does not start a boot loader: QEMU writes the kernel and the DTB into RAM again, because it registered them as ROM images (`qemu/hw/arm/boot.c:636`, `rom_reset` in `qemu/hw/core/loader.c:1242`). The primary CPU then restarts at the kernel's entry (`do_cpu_reset`, `boot.c:655`); the second CPU waits again for PSCI `CPU_ON`. The card image keeps what the guest wrote, so the new kernel mounts the same file system.

The image counts its boots in `/var/boot-count`. The acceptance check `tests/acceptance/m5/rootfs.py` uses the count to see each boot: boot 1, `poweroff`, boot 2 in a new QEMU, `reboot`, boot 3 in the same QEMU.

### 9.3 How the host sees a clean shutdown

After QEMU exits, the root partition in the image must be consistent without help. Look at the superblock:

```
$ dumpe2fs -h p2.img | grep features
Filesystem features:      has_journal ext_attr resize_inode dir_index filetype extent 64bit flex_bg sparse_super large_file huge_file dir_nlink extra_isize metadata_csum
```

If the file system was still mounted read-write at power-off, the list also has `needs_recovery`: the journal holds work that is not yet in place. `e2fsck -fn` does not see this. It skips the journal in a read-only check and exits 0. The acceptance check therefore reads the superblock too. A mutation proved the difference: without `umount -a -r` in `inittab`, `e2fsck -fn` passed and the superblock check failed ([tasks](../units/M5-sd-rootfs/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)).

## 10. How we know it works

Four kinds of test cover the two units, from the smallest to the largest.

1. **Register tests (qtest).** A qtest drives the SD host directly, without Linux, the way a driver would: it identifies a card, reads and writes blocks through the data port and through the DMA engine, and checks every value against the manual. The card behind it is a disk image that the test writes first. After the test, the written blocks are read back from the image file, so the check does not depend on the model at all. The test file is `qemu/tests/qtest/rzv2l-sdhi-test.c`.
2. **Mutations.** Each check was seen to fail once. We broke the model on purpose, one plausible mistake at a time: the wrong version number, flags that clear on 1 instead of 0, the DMA engine reporting the wrong direction, no stop command after a multi-block read. Each break must turn a check red; nineteen did ([tasks](../units/M5-sdhi/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)).
3. **Linux end to end.** `tests/acceptance/m5/run.sh` boots both kernels with a fresh SD image. In the guest, it writes files of awkward sizes (1, 513, 4097 bytes and a little over 1 MiB), syncs and unmounts. On the host, `e2fsck` checks the file system in the image and `debugfs` reads each file back, and every MD5 must match the guest's. A second boot then reads the files again.
4. **User space from the card.** The same script boots both kernels from the card's root partition, powers off, boots again, resets and powers off again (§9). It checks the root device, the boot count and the files in the guest, and the superblock, `e2fsck` and the files on the host. Four mutations turned it red ([tasks](../units/M5-sd-rootfs/tasks.md#proofs-each-mutation-the-exact-change--the-red-line)).

Finally, the board itself was checked. At the EVK's U-Boot prompt, the SD host's version register, its DMA engine and its other registers read the values the model uses ([EVK evidence §9](../evidence/EVK-2026-10-30-linux.md)).

## 11. Pitfalls

- **The fallback may be the rare path.** The Linux driver can move data without DMA, but it does so only for unaligned buffers. A model of the data port alone would look complete and would still fail almost every request. Before you trust a fallback, read the condition that selects it.
- **Start the DMA after the response.** The driver starts the DMA engine only when the card has accepted the command. A model that moves the data as soon as the command is written reports "done" before the driver expects it.
- **QEMU has no caches to get wrong.** The model's DMA writes go straight into guest memory, and QEMU does not model the CPU's data cache. A driver that forgets the cache maintenance of §5 therefore works in QEMU and fails on the board. Test cache handling on the board.
- **"Write 0 to clear".** Most devices clear a flag when you write 1 to it. This one clears it on 0 and keeps it on 1. The Linux interrupt handler writes 1s to the flags it still needs, so a model with the usual rule would lose them.
- **The register spacing belongs to the SoC.** The same family of SD host has its registers 2 or 4 bytes apart on other Renesas chips and 8 bytes apart on this one. The driver learns the spacing from its match table.
- **One address per request.** A DMA engine without scatter-gather turns large reads into many small commands (§4). That costs speed on the board, not correctness.
- **The device tree does not say what is in the slot.** The board's device tree describes SDHI0 as an 8-bit eMMC. The EVK boots from an SD card in that slot, and Linux finds whatever card answers. So the model presents an SD card, as the board has.
- **Card detect is a pin, and the board decides where it goes.** On the EVK, with a card in the SDHI0 slot, the SD host's "card present" and "writable" bits read 0. The module connects the slot's card-detect switch to the SD host only in a pin setting the board's device tree does not use, and the write-protect pin carries I2C. Linux does not ask, because the slot is marked non-removable. The model copies the board.
- **Byte or block addresses.** A card up to 2 GB (SDSC) takes byte addresses; larger cards (SDHC, SDXC) take block numbers. The MMC core handles this. A test that drives a card by hand must do the same.
- **Without `mmc` aliases, the card's name changes.** The two SD hosts start in parallel, so without aliases the card is `mmcblk0` in one boot and `mmcblk1` in the next. QEMU adds `mmc0` and `mmc1` aliases when the device tree has none, as the board's own product image does in its device tree.
- **A console nobody reads can stop the guest.** QEMU's serial model waits until its chardev accepts each byte, as a UART with flow control does (`qemu/hw/char/renesas_rz_scifa.c:403`). In a test run with the console socket unread, QEMU had not exited 90 s after `poweroff`; with the socket read, it exited at once. The likely cause is that QEMU writes the socket one byte at a time, and each byte takes a whole socket buffer entry, so an unread socket fills soon (an inference, not measured). A test script must read the console until QEMU exits.
- **`e2fsck -n` does not prove a clean shutdown.** A file system left mounted read-write keeps `needs_recovery` in its superblock, and a read-only `e2fsck` skips the journal and passes. Read the superblock (§9.3).
