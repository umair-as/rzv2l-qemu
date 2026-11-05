# Requirements catalogue

The format and states are defined in `project.md` §15. Evidence paths are relative to `docs/`.

**Status key:** P = PROPOSED, A = ACCEPTED, I = IMPLEMENTING, D = IMPLEMENTED, V = VERIFIED.

## Guest integrity

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-GUEST-001 | Acceptance runs SHALL use the tier's stock DTB, unmodified before loader fixups. Exception: the M7 TEE run, whose DTB adds `/firmware/optee` by overlay (DR-0006, device map gap 24). | spec §8; decisions/DR-0006 | DTB SHA256 recorded in the run log | M3 | V |
| REQ-GUEST-002 | Guest drivers SHALL NOT be patched for the emulator. | spec §8 | kernel source pinned; patch list = vendor's own | M3 | V |
| REQ-GUEST-003 | Firmware SHALL contain no QEMU-specific code. Build-config changes for closed, unemulatable IP are allowed and SHALL be listed as fidelity gaps. | spec §8, research/boot-chain-firmware.md | firmware recipe/config diff recorded | M7 | V |
| REQ-GUEST-004 | Every boot argument, injected DT node or loader fixup in an acceptance run SHALL be listed as a fidelity gap. | spec §8 | gap list reviewed per milestone | M3 | V |
| REQ-GUEST-005 | In direct mode the QEMU loader SHALL apply the G1 loader fixup contract, or list each omission. | research/boot-chain-firmware.md §5 | live-DT diff vs EVK | M4 | V |
| REQ-GUEST-006 | When U-Boot boots Linux in an acceptance run, the project's boot configuration SHALL name the boot source and the Linux root separately and SHALL name the root by `root=PARTUUID=`, so that Linux's device enumeration order does not choose it; attached project images SHALL have distinct partition identifiers; a PARTUUID no attached partition has SHALL stop the boot visibly. The vendor's default boot SHALL run as a compatibility check with its own verdict. | decisions/DR-0007; device map gap 22; evidence/EVK-2026-11-02-vendor-kernel-on-board.md | M7 acceptance (`rootsel.py`, `bootloader.py`, `tee.py`); `compat.py` verdict | M7 | V |

## Machine

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-MACH-001 | QEMU SHALL provide machine `rzv2l-smarc` built from SoC object `TYPE_R9A07G054` + board. | spec §10 | `-M help` | M1 | V |
| REQ-MACH-002 | The machine SHALL instantiate 2× cortex-a55 (MIDR Cortex-A55 r2p0) with `mp-affinity` 0x0/0x100; CPU1 SHALL start powered off. | DTSI `cpu@0`/`cpu@100`; research/boot-chain-firmware.md | qtest/monitor: MPIDR values; Linux brings up CPU1 via PSCI | M1 | V |
| REQ-MACH-003 | `CNTFRQ_EL0` SHALL read 24 000 000 (QEMU cortex-a55 defaults to 62.5 MHz per EXP-001; set the `cntfrq` property). | research/cpu-gic.md; EVK boot log (`arch_timer … 24.00MHz`) | guest read in a test ELF; Linux `arch_timer` line | M1 | V |
| REQ-MACH-004 | In direct mode the kernel SHALL be entered at NS-EL1, with PSCI over SMC (implementation: `has_el2=false`, `psci_conduit=SMC`, per EXP-001). | EVK logs `started at EL1`; boot-chain-firmware.md (`RCAR_BL33_EXECUTION_EL`) | guest dmesg | M3 | V |
| REQ-MACH-005 | The CPU SHALL implement the A55 IMPDEF sysregs accessed by the G1 TF-A (`CPUPWRCTLR_EL1` required; `CLUSTERIDR_EL1`/`CLUSTERCFR_EL1` precautionary). | boot-chain-firmware.md; EXP-001 (all three UNDEF on QEMU 11.1.2 cortex-a55) | BL31 CPU_OFF path runs without UNDEF | M7 | V |
| REQ-MACH-006 | DDR SHALL appear at 0x40000000 (2 GiB on the EVK), and `/memory` passed to Linux SHALL equal 0x48000000 + 0x78000000. | boot-chain-firmware.md; DTB-V | guest `/proc/iomem` vs EVK | M1 | V |
| REQ-MACH-007 | GIC-600 distributor and redistributors SHALL be at the stock DTB addresses, with no ITS. | DTSI `gic@11900000` | `info mtree`; qtest `GICD_IIDR` vs EVK | M1 | V |
| REQ-MACH-008 | Modelled MMIO devices and interrupts SHALL sit at the addresses and SPI numbers of the stock DTB and firmware. | device-map.md; r9a07g054.dtsi | `info mtree` / `info qtree` vs device-map.md | M1+ | V |

## SoC blocks

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-SYSC-001 | `SYS_LSI_DEVID` SHALL read the EVK value (low 28 bits 0x8447447). | boot-chain-firmware.md | qtest vs EVK capture | M1 | V |
| REQ-SYSC-002 | `SYS_LSI_MODE` @ 0x11020A00 SHALL report the configured boot source (board property). | boot-chain-firmware.md, boot-chain-firmware.md | qtest; U-Boot boot-source output | M7 | D |
| REQ-SYC-001 | The SYC (`0x11000000`, separate from SYSC; a CoreSight SoC-400 timestamp generator, manual §15.3) SHALL keep the frequency firmware writes to `CNTFID0` and return it, so BL31 can copy it into `CNTFRQ_EL0`. | research/el3-platform.md §2; boot-chain-firmware.md | qtest + BL31 boot (Stage B) | M7 | V |
| REQ-CPUPWR-001 | In firmware mode, the PSCI firmware SHALL start and stop each Cortex-A55 through the SoC's own registers (SYSC reset vectors and sleep flags, CPG `RST_CA55` and P-Channels), so that BL31's `CPU_ON`, `CPU_OFF` and `SYSTEM_RESET` bring CPU1 up, take it down and back, and restart the board. | units/M7-el3-platform/spec.md; research/el3-platform.md | qtest (manual reset values, flag rules, core run lines); firmware-mode acceptance (CPU1 online, hotplug, reboot) | M7 | V |
| REQ-TZC-001 | TZC0-3 SHALL answer the boot firmware's programming with the manual's region and filter counts, store it, and not enforce it (the board as built leaves memory open, spec §12). | units/M7-el3-platform/spec.md; manual §13 | qtest; BL31 boot | M7 | V |
| REQ-CPG-001 | Each CPG `CLK_MON_*` SHALL read the same-polarity value of its `CLK_ON_*` bits, and each `RSTMON_*` SHALL read `~RST_* & implemented_mask` (1 = held in reset), computed on read; writes SHALL honour the `*_WEN` upper-half write enables. | research/cpg-reset.md; HW manual p.327/368/409/450; linux v6.12.59 rzg2l-cpg.c | qtest: per register, assert both polarities (enable→monitor 1, release reset→monitor 0) and the WEN masking; mutation check (a same-polarity RSTMON must fail) | M3b | V |
| REQ-PFC-001 | The PFC SHALL accept the `rzg2l-pinctrl` probe and SCIF0 pin configuration. | DTSI `pinctrl@11030000`; spec §11 | M3b console via sh-sci | M3b | V |
| REQ-SCIF-001 | SCIF0 @ 0x1004B800 SHALL implement the RZ/SCIFA register layout to the depth sh-sci, U-Boot and TF-A use (TX/RX FIFO, FSR.TEND, interrupts on SPI per DTB). | DTSI `serial@1004b800`; boot-chain-firmware.md; HW manual SCIFA chapter | qtest vs manual reset values; M2 hello; M3 | M2 | V |
| REQ-WDT-001 | WDT0 SHALL either model expiry reset faithfully or be listed as honest-fault STUB. `SYSTEM_RESET` via the parity-error force register SHALL reset the machine. | boot-chain-firmware.md, boot-chain-firmware.md | qtest; PSCI reset from guest | M4 | V |
| REQ-SDHI-001 | SDHI0/1 SHALL run the unchanged `renesas_sdhi` driver through its internal-DMAC path and its PIO fallback, with an SD card from a QEMU drive behind SDHI0; an access the model does not implement (SCC tuning, UHS signalling) SHALL fail visibly, never succeed silently. | units/M5-sdhi/spec.md; evidence/EVK-2026-10-30-linux.md §8 | qtest (manual reset values, flag rules); G0/G1 boot with the card | M5 | V |
| REQ-SDHI-002 | Data written by the guest to the SD card (ext4, sync, clean unmount) SHALL be in the disk image after QEMU exits, as read by a host tool, and SHALL read back in a new QEMU run. | units/M5-sdhi/spec.md | acceptance: hashes in guest, on host, after restart | M5 | V |
| REQ-SDHI-003 | With the board's SD-root command line and no initramfs, G0 and G1 SHALL mount an ext4 root file system from the SD card on SDHI0 and run its init; a guest power-off SHALL leave that file system clean in the image (no journal recovery needed), and its files SHALL persist across power-off and a guest-initiated reset. | units/M5-sd-rootfs/spec.md | acceptance: root device, PID 1, host superblock and hashes, boot count across power-off and reset | M5 | V |
| REQ-ETH-001 | ETH0/1 SHALL run the unchanged `ravb` driver (gbeth) with the board's KSZ9131 PHY through its MDIO pins and its interrupt through the IRQC; an access the model does not implement (MDIO controller, EEE, TOE filters, flow control) SHALL fail visibly, never succeed silently. | units/M6-ravb/spec.md; research/ravb.md | qtest (manual and IEEE 802.3 values, descriptor and interrupt rules) | M6 | V |
| REQ-ETH-002 | With a QEMU network backend on ETH0, both kernels SHALL obtain a DHCP lease and move data in both directions with equal hashes, beyond one turn of each descriptor ring, and SHALL recover after a link down/up, an interface down/up and a machine reset. | units/M6-ravb/spec.md | acceptance `tests/acceptance/m6/` on user networking | M6 | V |
| REQ-RPC-001 | The SPI multi I/O bus controller SHALL run the unchanged U-Boot `rpc_spi` and Linux `rpc-if`/`spi-rpc-if` drivers with the module's MT25QU512A flash (its JEDEC ID and SFDP tables as on the EVK), whose contents come from a QEMU drive; data the guest writes SHALL be in the image after QEMU exits; a mode the model does not support (HyperFlash, Octal-SPI, two flashes, the write buffer) or a transfer the manual prohibits SHALL fail visibly, never succeed silently. | units/M7-rpc-spinor/spec.md; research/rpc.md; evidence/EVK-2026-11-04-spi-flash.md | qtest (manual reset values, transfers against flash content); M7 acceptance `flash.py` | M7 | V |
| REQ-TSIP-001 | TSIP SHALL be UNSUPPORTED/honest-fault: the production OP-TEE SHALL fail with its documented panic, not hang or succeed silently. | boot-chain-firmware.md | Stage N negative test | M7 | P |
| REQ-TEE-001 | With the project's TEE-enabled kernel (vendor source, `CONFIG_TEE`/`CONFIG_OPTEE`, a `/firmware/optee` node by overlay; DR-0006), Linux SHALL probe the OP-TEE driver, create `/dev/tee0` and `/dev/teepriv0`, and a user-space client SHALL invoke a trusted application through `tee-supplicant` and get its answer. | decisions/DR-0006; evidence/EVK-2026-11-02-optee-driver.md | M7 TEE acceptance | M7 | V |
| REQ-TEE-002 | Features the emulated OP-TEE build lacks (hardware crypto and RNG through TSIP, RPMB storage) SHALL be reported separately from the REQ-TEE-001 result, each with how its absence shows. | decisions/DR-0006 | TEE acceptance report | M7 | V |
| REQ-OSTM-001 | OSTM0-2 SHALL count at the P0 rate (100 MHz on the EVK) and SHALL clear TE when TT is written. | boot-dependency-graph.md §1(b); HW manual §20.2.2.3/§20.2.2.5; EVK boot log (sched_clock 100 MHz) | qtest; M3b `sched_clock` line | M3b | V |
| REQ-IRQC-001 | The IRQC (IA55) window SHALL be mapped so the `rzg2l-irqc` driver probes. | boot-dependency-graph.md §1(b) | M3b probe log | M3b | V |
| REQ-MAP-001 | Every register window enabled in DTB-U SHALL have a per-window classification in `device-map.md` (model / honest-fault stub / read-as-zero stub with evidence that zero is faithful or harmless / unmapped) and the milestone at which it becomes a model or an honest failure. Mapping a window is **not** a fidelity claim: a stub must not cause a hang, a false success or a frozen clock (e.g. OSTM). | research/boot-dependency-graph.md §4; device-map.md | per-window review + `-d unimp` log review at M3b | M3b | V |

## Boot policy (M9)

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-BOOT-001 | On the automatic boot path of the M9 profile, U-Boot SHALL boot a FIT configuration only if a signature by the profile's required key covers it and every image hash in it matches. | decisions/DR-0008; spec §12 | M9 acceptance (`fit.py`): the signed FIT reaches the shell | M9 | P |
| REQ-BOOT-002 | A FIT with a changed kernel, a changed DTB, no configuration signature, a signature by another key, a signature that covers only some of the configuration's images, or one of upstream U-Boot's crafted layouts (`fakeroot`, `kernel@`) SHALL be refused before kernel entry, also with `verify=n` stored; each refusal SHALL spend one attempt of the slot, and no other boot route SHALL run. | decisions/DR-0008 | M9 acceptance (`fit.py`): each case to the prompt with its counter at 0 | M9 | P |
| REQ-BOOT-003 | U-Boot SHALL boot the first slot in `BOOT_ORDER` with an attempt left, after saving that attempt; the counters SHALL survive resets and a new QEMU process on the same card. | decisions/DR-0008 | M9 acceptance (`ab.py`): selection, rollback with a restart | M9 | P |
| REQ-BOOT-004 | Linux SHALL commit only the slot it runs from, and only after its root PARTUUID and health checks pass; a pending update SHALL be committed by its first healthy boot. | decisions/DR-0008 | M9 acceptance (`ab.py`): selection, good update | M9 | P |
| REQ-BOOT-005 | A pending slot that exhausts its attempts SHALL give way to the other slot, which records the rollback; when both slots are exhausted, U-Boot SHALL stop at its prompt with the counters printed and SHALL NOT replenish them. | decisions/DR-0008 | M9 acceptance (`ab.py`): bad update, both exhausted | M9 | P |
| REQ-BOOT-006 | With one environment copy damaged, U-Boot SHALL use the other and the next save SHALL repair it; with both damaged, U-Boot SHALL warn and run the M9 policy from its default environment, never the vendor's unsigned boot command. | decisions/DR-0008 | M9 acceptance (`ab.py`): damaged copies | M9 | P |

## Tests and process

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-TEST-001 | `tests/probes/hello-rzv2l/` (an arm64 Image built from an ELF) SHALL print `Hello from RZ/V2L` via SCIF0 in direct mode. | spec §17 | scripted run, exact-match output | M2 | V |
| REQ-TEST-002 | Every device model SHALL have a kernel-free qtest asserting manual reset and ID values; each test SHALL be mutation-checked. | spec §13 | CI + mutation record | M1+ | V |
| REQ-TEST-003 | Acceptance runs SHALL use `-d unimp,guest_errors,invalid_mem`; every logged access SHALL be modelled or listed. | spec §13 | log review per milestone | M3+ | V |
