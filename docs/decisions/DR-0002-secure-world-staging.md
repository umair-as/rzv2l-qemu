# DR-0002: Secure-world staging

- **Status:** Proposed; needs operator review. The Stage A technical question was answered by EXP-001 (2026-10-08).
- **Date:** 2026-10-08

## Context

On the board, TF-A BL31 provides PSCI and the OP-TEE dispatcher, and Linux and U-Boot issue SMCs. The production OP-TEE depends on TSIP, a closed crypto IP.

## Evidence

All in `docs/research/boot-chain-firmware.md`:
- **OP-TEE needs TSIP** (`boot-chain-firmware.md`). It opens TSIP eagerly at boot. TSIP is a closed library with an undocumented register protocol, and the HW manual lists it as "Reserved". If it is absent, OP-TEE panics and BL31 stalls before U-Boot.
- **A rebuilt OP-TEE is easy to run** (`boot-chain-firmware.md`). Built with `CFG_RZ_SCE=n`, it touches only SCIF0 and OTP at boot.
- **BL31 needs specific hardware** (`boot-chain-firmware.md`):
  - SYSC `RVAL/RVAH` and the `LP_CTL5` acknowledge bit
  - the CPG CA55 reset/power handshake
  - WDT0 for reset
  - `CNTFID0`
  - A55 IMPDEF sysregs
  - the BL2→BL31 parameter block at `0x2F000`
- **BL2 needs DDR training and a boot source** (`boot-chain-firmware.md`). A DDR stub is estimated at 150–250 lines. SPI boot needs only `TEND` plus a flash window.
- **OP-TEE's absence is soft** (`boot-chain-firmware.md`). U-Boot skips `kaslr-seed`. The SMC instruction itself is the hard requirement.

## Alternatives

1. QEMU built-in PSCI only, for all milestones.
2. Built-in PSCI plus an SMCCC `NOT_SUPPORTED` responder.
3. Real BL31+BL32 from the start.
4. **Staged:** A (built-in PSCI) → B (real BL31 + rebuilt OP-TEE) → C (real BL2 + DDR stub), plus N (the production OP-TEE as a negative test).

## Decision (proposed)

Option 4.

Stage A needs **no** custom SMCCC responder. EXP-001 (`docs/experiments/EXP-001-smc-and-impdef-sysregs.md`) shows that with `psci_conduit = SMC`, QEMU's PSCI handler catches **every** SMC:
- unknown function IDs return `NOT_SUPPORTED` (-1) with no guest exception (`qemu/target/arm/tcg/psci.c:30-53`, `:206-217`)
- examples: OP-TEE `0xBF00FF01`, SiP `0x82000011`

A machine gets both SMC conduit and EL1 entry by setting `has_el2=false` (`boot.c:1247-1254`). TSIP is UNSUPPORTED and honest-fault. TZC-400 is not enforced, matching the TBB=0 board.

## Consequences

- Linux bring-up (M3–M6) is not blocked on firmware modelling.
- Stage B adds SYSC/CPG power-handshake and IMPDEF sysreg work at M7.
- The OP-TEE build-config change is a declared fidelity gap (REQ-GUEST-003).

## Unknowns

- Resolved by EXP-001: the IMPDEF sysregs. `CPUPWRCTLR_EL1` is required (BL31 CPU_OFF). `CLUSTERIDR_EL1` and `CLUSTERCFR_EL1` appear only in DSU errata checks, which are unreachable in the release build; add them as a precaution.
- The exact BL2→BL31 parameter layout needed for direct BL31 entry.

## Revisit condition

- A G1 build enabling `TRUSTED_BOARD_BOOT`.
- A need to run the production OP-TEE.
