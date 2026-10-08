# Requirements catalogue

The format and states are defined in `project.md` §15. Evidence paths are relative to `docs/`.

**Status key:** P = PROPOSED, A = ACCEPTED, I = IMPLEMENTING, D = IMPLEMENTED, V = VERIFIED.

## Guest integrity

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-GUEST-001 | Acceptance runs SHALL use the tier's stock DTB, unmodified before loader fixups. | spec §8 | DTB SHA256 recorded in the run log | M3 | P |
| REQ-GUEST-002 | Guest drivers SHALL NOT be patched for the emulator. | spec §8 | kernel source pinned; patch list = vendor's own | M3 | P |
| REQ-GUEST-003 | Firmware SHALL contain no QEMU-specific code. Build-config changes for closed, unemulatable IP are allowed and SHALL be listed as fidelity gaps. | spec §8, research/boot-chain-firmware.md | firmware recipe/config diff recorded | M7 | P |
| REQ-GUEST-004 | Every boot argument, injected DT node or loader fixup in an acceptance run SHALL be listed as a fidelity gap. | spec §8 | gap list reviewed per milestone | M3 | P |
| REQ-GUEST-005 | In direct mode the QEMU loader SHALL apply the G1 loader fixup contract, or list each omission. | research/boot-chain-firmware.md §5 | live-DT diff vs EVK | M4 | P |

## Machine

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-MACH-001 | QEMU SHALL provide machine `rzv2l-smarc` built from SoC object `TYPE_R9A07G054` + board. | spec §10 | `-M help` | M1 | P |
| REQ-MACH-002 | The machine SHALL instantiate 2× cortex-a55 with `mp-affinity` 0x0/0x100; CPU1 SHALL start powered off. | DTSI `cpu@0`/`cpu@100`; research/boot-chain-firmware.md | qtest/monitor: MPIDR values; Linux brings up CPU1 via PSCI | M1 | P |
| REQ-MACH-003 | `CNTFRQ_EL0` SHALL read 24 000 000 (QEMU cortex-a55 default is 62.5 MHz, per EXP-001; set the `cntfrq` property) in direct mode, and SYC `CNTFID0` SHALL read 24 000 000. | research/boot-chain-firmware.md | qtest + guest read | M1 | P |
| REQ-MACH-004 | In direct mode the kernel SHALL be entered at NS-EL1, with PSCI over SMC (implementation: `has_el2=false`, `psci_conduit=SMC`, per EXP-001). | EVK logs `started at EL1`; boot-chain-firmware.md (`RCAR_BL33_EXECUTION_EL`) | guest dmesg | M3 | P |
| REQ-MACH-005 | The CPU SHALL implement the A55 IMPDEF sysregs accessed by the G1 TF-A (`CPUPWRCTLR_EL1` required; `CLUSTERIDR_EL1`/`CLUSTERCFR_EL1` precautionary). | boot-chain-firmware.md; EXP-001 (all three UNDEF on QEMU 11.1.2 cortex-a55) | BL31 CPU_OFF path runs without UNDEF | M7 | P |
| REQ-MACH-006 | DDR SHALL appear at 0x40000000 (2 GiB on the EVK), and `/memory` passed to Linux SHALL equal 0x48000000 + 0x78000000. | boot-chain-firmware.md; DTB-V | guest `/proc/iomem` vs EVK | M1 | P |
| REQ-MACH-007 | GIC-600 distributor and redistributors SHALL be at the stock DTB addresses, with no ITS. | DTSI `gic@11900000` | `info mtree`; qtest `GICD_IIDR` vs EVK | M1 | P |

## SoC blocks

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-SYSC-001 | `SYS_LSI_DEVID` SHALL read the EVK value (low 28 bits 0x8447447). | boot-chain-firmware.md | qtest vs EVK capture | M1 | P |
| REQ-SYSC-002 | `SYS_LSI_MODE` @ 0x11020A00 SHALL report the configured boot source (board property). | boot-chain-firmware.md, boot-chain-firmware.md | qtest; U-Boot boot-source output | M7 | P |
| REQ-CPG-001 | Each CPG `CLK_MON_*` SHALL reflect the corresponding `CLK_ON_*`, and each `RSTMON_*` the corresponding `RST_*`. | boot-chain-firmware.md (SDHI probe poll) | qtest: write enable → read monitor | M3 | P |
| REQ-PFC-001 | The PFC SHALL accept the `rzg2l-pinctrl` probe and SCIF0 pin configuration. | DTSI `pinctrl@11030000`; spec §11 | M3b console via sh-sci | M3 | P |
| REQ-SCIF-001 | SCIF0 @ 0x1004B800 SHALL implement the RZ/SCIFA register layout to the depth sh-sci, U-Boot and TF-A use (TX/RX FIFO, FSR.TEND, interrupts on SPI per DTB). | DTSI `serial@1004b800`; boot-chain-firmware.md; HW manual SCIFA chapter | qtest vs manual reset values; M2 hello; M3 | M2 | P |
| REQ-WDT-001 | WDT0 SHALL either model expiry reset faithfully or be listed as honest-fault STUB. `SYSTEM_RESET` via the parity-error force register SHALL reset the machine. | boot-chain-firmware.md, boot-chain-firmware.md | qtest; PSCI reset from guest | M4 | P |
| REQ-TSIP-001 | TSIP SHALL be UNSUPPORTED/honest-fault: the production OP-TEE SHALL fail with its documented panic, not hang or succeed silently. | boot-chain-firmware.md | Stage N negative test | M7 | P |

## Tests and process

| ID | Statement | Evidence | Verification | M | Status |
|---|---|---|---|---|---|
| REQ-TEST-001 | `tests/hello-rzv2l` (ELF) SHALL print `Hello from RZ/V2L` via SCIF0 in direct mode. | spec §17 | scripted run, exact-match output | M2 | P |
| REQ-TEST-002 | Every device model SHALL have a kernel-free qtest asserting manual reset and ID values; each test SHALL be mutation-checked. | spec §13 | CI + mutation record | M1+ | P |
| REQ-TEST-003 | Acceptance runs SHALL use `-d unimp,guest_errors`; every logged access SHALL be modelled or listed. | spec §13 | log review per milestone | M3+ | P |
