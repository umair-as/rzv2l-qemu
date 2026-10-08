# EXP-001: SMC handling and Cortex-A55 IMPDEF sysregs in stock QEMU

Date: 2026-10-08. Status: complete.

## Question

- **Q1.** What happens to a guest SMC under QEMU's built-in PSCI (no EL3 firmware)? Cases: PSCI_VERSION
  `0x84000000`, the non-PSCI calls `0xBF00FF01` (OP-TEE UID) and `0x82000011` (SiP), and `has_el3` on vs off.
  How is the conduit chosen, and can a machine pick the SMC conduit while entering the guest at EL1?
- **Q2.** On `-cpu cortex-a55`, do `S3_0_C15_C2_7` (CPUPWRCTLR_EL1), `S3_0_C15_C1_0` (CPUACTLR_EL1) and
  `S3_0_C15_C1_4` (CPUECTLR_EL1) UNDEF at EL1 and at EL3? Which IMPDEF sysregs does the real RZ/V2L BL31 touch?
- **Q3.** What are the defaults for CNTFRQ, MPIDR and the kernel entry EL, and which CPU properties override them?

## Setup

- QEMU: submodule `qemu/` at `4fc49f46dc95d4a27de2509e7fceb2931e91faeb` (v11.1.2, clean, unmodified).
- Host: Ubuntu 24.04.5, Linux 6.8.0-139 x86_64. Toolchain: `aarch64-linux-gnu-gcc` 13.3.0 (Ubuntu).
- Build: `cd build/qemu && ../../qemu/configure --target-list=aarch64-softmmu --enable-debug-info
  --disable-docs --disable-werror --disable-sdl --disable-gtk --disable-vnc --disable-opengl && ninja qemu-system-aarch64`.
  No host dependencies were missing.
- Probe: `tests/experiments/exp-001-smc-impdef/{start.S,probe.c,probe.ld,Makefile,run.sh}`. It is linked at
  0x40080000 and built two ways:
  - `out/probe.Image`: raw binary with an arm64 Image header (`ARM\x64` magic, text_offset 0x80000). QEMU treats
    any raw AArch64 binary as Linux (`hw/arm/boot.c:920,950-954`; the header is optional, `boot.c:844-846`).
  - `out/probe.elf`: QEMU treats an ELF as non-Linux and starts it at the highest EL.

  The probe installs a vector table at every EL it can reach and prints `CurrentEL`, MIDR, MPIDR and CNTFRQ. It then
  runs the three SMCs, an HVC, and an MRS and MSR of each IMPDEF register. Next it tries PSCI CPU_ON(0x1). Finally it
  drops to NS EL1 (from EL2 or EL3) and repeats the tests. The exception handler prints ESR/ELR, steps past
  the instruction, and returns `x0=0xdeaddead...`.
- Common flags: `-nographic -m 256 -monitor none -serial stdio -d guest_errors`, wrapped in `timeout 10`.

| test | QEMU args (plus common flags) | has_el3/el2 | entry EL | QEMU PSCI conduit |
|---|---|---|---|---|
| t1 | `-M virt,virtualization=on -cpu cortex-a55 -smp 2 -kernel probe.Image` | 0/1 | 2 | SMC |
| t2 | `-M virt -cpu cortex-a55 -smp 2 -kernel probe.Image` | 0/0 | 1 | HVC |
| t3 | `-M virt,secure=on,virtualization=on -cpu cortex-a55 -smp 2 -kernel probe.Image` | 1/1 | 2 | SMC |
| t4 | `-M virt,secure=on,virtualization=on -cpu cortex-a55 -kernel probe.elf` | 1/1 | 3 | disabled |
| t5 | `-M virt,virtualization=on -cpu cortex-a55,has_el2=off -smp 2 -kernel probe.Image` | 0/0 | 1 | SMC |
| t6 | `-M virt,secure=on,virtualization=on -cpu cortex-a55,has_el2=off -smp 2 -kernel probe.Image` | 1/0 | 1 | SMC |
| t7 | `-M virt -cpu cortex-a55,cntfrq=24000000,mp-affinity=0x100 -kernel probe.Image` | 0/0 | 1 | HVC |
| t8 | `-M virt,secure=on,virtualization=on -cpu neoverse-n1 -kernel probe.elf` (control) | 1/1 | 3 | disabled |

## Observations

The full raw log is in `tests/experiments/exp-001-smc-impdef/run-all.log`. The excerpts below are trimmed: leading
zeros are removed and repeated lines are elided.

```
t1 EL2 (and again after drop to EL1):   MIDR=0x412fd050 MPIDR=0x80000000 CNTFRQ=0x03b9aca0 (62.5 MHz)
  SMC 0x84000000 -> x0=0x00010001          (PSCI 1.1)
  SMC 0xbf00ff01 -> x0=0xffffffffffffffff  (-1 NOT_SUPPORTED)
  SMC 0x82000011 -> x0=0xffffffffffffffff  (-1 NOT_SUPPORTED)
  HVC 0x84000000 -> [EXC to EL2 ESR=0x5a000000 EC=0x16]   (real HVC exception, not PSCI)
  MRS/MSR S3_0_C15_C2_7 / C1_0 / C1_4 -> [EXC ESR=0x02000000 EC=0x00] (UNDEF) at EL2 and EL1
  CPU_ON(0x1) via SMC -> 0; [secondary up: EL=2 MPIDR=0x80000001]
t2 EL1, conduit HVC, no EL2/EL3:
  SMC (all 3 fids) -> [EXC to EL1 ESR=0x02000000 EC=0x00 ELR=<the smc insn>]   (UNDEF)
  HVC 0x84000000 -> x0=0x00010001; CPU_ON via HVC -> 0; secondary EL=1 MPIDR=0x80000001
  IMPDEF MRS/MSR -> UNDEF (ESR 0x02000000)
t3 has_el3=1, EL2 entry, conduit SMC: identical to t1 (PSCI 1.1, -1, -1; IMPDEF UNDEF)
t4 EL3 start (ELF), QEMU PSCI disabled:
  SMC at EL3 (all fids)      -> [EXC to EL3 ESR=0x5e000000 EC=0x17 ELR=<insn after smc>]
  IMPDEF MRS/MSR at EL3      -> [EXC to EL3 ESR=0x02000000 EC=0x00] (UNDEF)
  after drop to NS EL1: SMC  -> [EXC to EL3 ESR=0x5e000000 EC=0x17] (routed to the EL3 vector)
                        HVC  -> UNDEF (SCR_EL3.HCE=0); IMPDEF -> UNDEF at EL1
t5 has_el2=off on virt,virtualization=on: entered EL1, SMC 0x84000000 -> 0x10001,
   0xbf00ff01 -> -1, 0x82000011 -> -1, HVC -> UNDEF, CPU_ON via SMC -> 0, secondary EL=1
t6 same as t5 with has_el3=1: identical results
t7 CNTFRQ_EL0=0x016e3600 (24,000,000).  MPIDR_EL1=0x80000000 (mp-affinity=0x100 overwritten by virt)
t8 neoverse-n1 control: EL3 MRS/MSR of all three regs OK (CPUECTLR reads 0x961563010);
   at EL1, MRS OK, MSR -> [EXC to EL2 ESR=0x623e3c24 EC=0x18] (access_actlr_w trap, not UNDEF)
```

Static analysis of the RZ/V2L BL31 that was actually built (`build/v2l/release/bl31/bl31.elf`, `objdump -d`):

```
IMPDEF accesses: s3_0_c15_c2_7 x2  in <cortex_a55_core_pwr_dwn>      (MRS+MSR, set bit0 CORE_PWRDN_EN)
                 s3_0_c15_c3_1 x2  in <check_errata_dsu_798953/936184> (CLUSTERIDR_EL1)
                 s3_0_c15_c3_0 x1  in <check_errata_dsu_936184>        (CLUSTERCFR_EL1)
bl2.elf:         only the same two DSU check functions (C3_0, C3_1)
print_errata_status = single `ret` (DEBUG=0); no errata-ABI symbols; the DSU checkers are referenced
only from the cortex_a55 errata table (data words at 0x44005c88/0x44005ca0)
```

Effective build flags (`temp/log.do_compile` -> `log.do_compile.798064`): `PLAT=v2l DEBUG=0 SPD=opteed
HW_ASSISTED_COHERENCY=1`, `ERRATA_A55_768277/778703/798797/846532/903758/1221012=0`, `ERRATA_A55_1530923=1`,
`ERRATA_DSU_798953/936184/2313941=0`, and `WORKAROUND_CVE_2017_5715=1 2018_3639=1 2022_23960=1`. Note that
`plat/renesas/rz/common/v2h_common.mk` (and the n2h, t2h and g3s files) set ERRATA_A55_* to 1, but the v2l build
pulls in `rz_common.mk`, which sets only `ERRATA_A55_1530923 := 1` (line 35).

## Source trace (qemu/ @ 4fc49f46dc)

- Conduit selection on virt: `hw/arm/virt.c:2955-2961`. `secure=on` with firmware gives DISABLED,
  `virtualization=on` gives SMC, and anything else gives HVC. The value is passed to the boot code at `virt.c:3260`. virt clears
  `has_el3` unless `secure=on` (`virt.c:3053-3055`) and clears `has_el2` unless `virtualization=on` (`virt.c:3057-3059`).
- Generic boot (`hw/arm/boot.c`):
  - The boot EL is the highest implemented EL (`1238-1245`). For a Linux image it is EL2 if the CPU has EL2, else EL1
    (`1247-1249`).
  - The conduit is disabled if it is HVC with boot_el≥2, or SMC with boot_el==3 (`1251-1254`). Otherwise each CPU gets the
    `psci-conduit` property and secondaries start powered off (`1256-1267`).
  - Per-CPU reset of a Linux image uses `target_el = EL2 ? 2 : 1` (`704`), then `arm_emulate_firmware_reset`
    (`target/arm/cpu.c:686-`). A non-Linux image goes straight to its entry at reset EL (`664-693`).
- SMC path (TCG):
  1. `HELPER(pre_smc)` at `target/arm/tcg/op_helper.c:1323`. With no EL3 and conduit≠SMC, it raises UNDEF (`1377-1392`).
     HCR_EL2.TSC traps to EL2 (`1394-1400`). With no PSCI and (SMD set or no EL3), it raises UNDEF (`1407-1411`).
     Otherwise the SMC exception is taken.
  2. `arm_cpu_do_interrupt_aarch64` path at `target/arm/helper.c:9640-9644`: if `arm_is_psci_call()`, it calls
     `arm_handle_psci_call()` and returns, so no guest exception is visible.
  3. `arm_is_psci_call()` (`target/arm/tcg/psci.c:30-53`) checks **only the conduit type**, not the function ID. When the
     conduit is SMC, every SMC is captured.
  4. `arm_handle_psci_call()` (`psci.c:58-`): PSCI_VERSION returns 1.1 (`95-96`). Unknown IDs reach `default:`, which
     returns `QEMU_PSCI_RET_NOT_SUPPORTED` (`206-210`), and the result is written to x0 (`213-217`).
- HVC: `HELPER(pre_hvc)` (`op_helper.c:1283-`) takes the PSCI shortcut only when the conduit is HVC.
- CPU_ON enters the secondary at EL2 if the CPU has EL2, else EL1 (`psci.c:148-155`).
- Cortex-A55 model (`target/arm/tcg/cpu64.c:203-273`): features include EL2/EL3, `BACKCOMPAT_CNTFRQ` (`212`),
  and `midr = 0x412FD050 /* r2p0 */` (`248`). **No IMPDEF cp regs are defined.** For comparison, `neoverse_n1_cp_reginfo`
  (`555-625`) defines CPUACTLR/2/3, CPUECTLR, CPUPWRCTLR, CPUP*R_EL3 and others as `ARM_CP_CONST`, with
  `access_actlr_w` (`537-553`) trapping EL1 writes to EL2/EL3.
- Timer: `cntfrq` property (`target/arm/cpu.c:1306`). It defaults to 62.5 MHz with `BACKCOMPAT_CNTFRQ`, else 1 GHz
  (`cpu.c:1906-1923`, `internals.h:88-89`). CNTFRQ_EL0 resets to the property (`helper.c:1121-1125`). The real tick
  rate also derives from the property (`gt_cntfrq_period_ns`, `cpu.c:1430-1451`).
- MPIDR:
  - The `mp-affinity` property is in `cpu.c:2490` and is used only if left unset (`cpu.c:2158-2160`). The default is
    `arm_build_mp_affinity(idx, 8)`, i.e. Aff0 = index (`cpu.c:1223-1228`).
  - MPIDR_EL1 = mp_affinity | bit31 (`helper.c:3014-3031`). The MT bit is not set unless it is put in mp-affinity.
  - virt overwrites mp-affinity per CPU (`virt.c:3042`, `2454-2473`).
- `has_el2` and `has_el3` are properties (`cpu.c:1314-1318`). They are applied by clearing the features at realize (`cpu.c:2175-2200`).

## Conclusions

1. **FACT** (t1, t3, t5, t6 plus trace): with the SMC conduit active, every SMC from EL1 or EL2 is consumed by QEMU. PSCI
   IDs are emulated (PSCI_VERSION = 0x10001). Any other ID, including `0xBF00FF01` and `0x82000011`, returns
   **x0 = -1 (NOT_SUPPORTED)** with no guest exception. This holds with `has_el3` true or false.
2. **FACT** (t2): with no EL3 and conduit≠SMC, an SMC is **UNDEF** to the current EL: ESR=0x02000000 (EC=0) and
   ELR = the SMC itself.
3. **FACT** (t4): with EL3 present and QEMU PSCI disabled, an SMC is taken to the guest's own **EL3 vector**:
   ESR=0x5E000000 (EC=0x17, imm16=0) and ELR = the next instruction.
4. **FACT** (t5, t6): a machine gets SMC conduit plus EL1 entry by setting `psci_conduit=SMC` and creating
   CPUs with `has_el2=false`. boot.c keeps SMC unless boot_el==3, and a Linux image never boots at EL3. `has_el3` can be
   true or false.
5. **FACT** (t1-t6): on cortex-a55, MRS and MSR to S3_0_C15_C2_7, S3_0_C15_C1_0 and S3_0_C15_C1_4 **UNDEF at EL1, EL2
   and EL3** (ESR 0x02000000). On neoverse-n1 the same encodings exist (t8).
6. **FACT** (objdump): the shipped v2l BL31 contains exactly three IMPDEF encodings: CPUPWRCTLR_EL1 (reachable via
   PSCI CPU_OFF/suspend power-down in `cortex_a55_core_pwr_dwn`), CLUSTERIDR_EL1 and CLUSTERCFR_EL1.
7. **FACT** (TF-A errata framework, `cpu_macros.S:305-316,575-605`): the reset function runs only erratum
   entries whose build flag is chosen. In this build, no A55 or DSU reset workaround is chosen, and 1530923 has no in-CPU
   workaround (`cortex_a55.S:111-114`). So `cortex_a55_reset_func` touches no IMPDEF register.
8. **INFERENCE**: none of the A55 errata would apply to QEMU's MIDR anyway. QEMU reports r2p0, while 768277 and 798797
   are ≤r0p0, 846532 and 903758 are ≤r0p1, and 1221012 is ≤r1p0 (`cortex_a55.S:44-109`), and 778703 also needs
   ≤r0p0. A build with all errata on would still write no CPUACTLR/CPUECTLR/CPUP*R_EL3 on QEMU.
9. **INFERENCE**: the DSU checkers (CLUSTERIDR/CLUSTERCFR) are unreachable in this release build: chosen=0,
   `print_errata_status` is empty, and there is no errata ABI. A DEBUG/REPORT_ERRATA build would call every checker and
   hit them.
10. **FACT** (t7 and all others): the default CNTFRQ_EL0 for cortex-a55 is **62.5 MHz** (0x03b9aca0), because
    the CPU sets `ARM_FEATURE_BACKCOMPAT_CNTFRQ` (`cpu64.c:212`, `cpu.c:1918-1920`). Setting
    `-cpu cortex-a55,cntfrq=24000000` gives CNTFRQ_EL0 = 0x016e3600 (24 MHz).
11. **FACT** (t1-t7): the default MPIDR is 0x80000000 / 0x80000001 (Aff0 numbering). `mp-affinity` is honoured only if
    the machine does not overwrite it. virt does overwrite it (t7), but a custom machine can set 0x0 and 0x100.
12. **FACT**: a Linux image enters at EL2 if the CPU has EL2, else at EL1, regardless of has_el3. A non-Linux ELF or bios
    starts at the highest EL. QEMU PSCI stays available with has_el3=false and has_el2=false (t2 via HVC, t5 via SMC).

## Implications for the rzv2l machine

- **Direct-kernel mode** (QEMU PSCI, no TF-A): create both A55s with `has_el2=false` and set
  `arm_boot_info.psci_conduit = QEMU_PSCI_CONDUIT_SMC`. The guest enters at NS EL1, which matches the real board and the
  stock DT `method="smc"`. **No extra SMCCC NOT_SUPPORTED responder is needed**, because QEMU already returns -1 for
  OP-TEE (`0xBF00FF01`, `0xB200xxxx`) and SiP (`0x82000010/11`) calls. U-Boot and Linux treat that as "no OP-TEE".
  If a SiP call needs a real answer later, it would need a hook in `arm_handle_psci_call`'s default path; stock QEMU has
  none. Keep `has_el3` false here, or true (t6 behaves the same).
- **Real TF-A mode** (BL2/BL31 as firmware): use `has_el3=true` and `has_el2=true`, `psci_conduit = DISABLED`, and start
  at EL3. SMCs then reach BL31's vector (t4).
- **Sysregs to add** for cortex-a55 in the rzv2l machine. This is board-local reginfo; `qemu/` itself is not modified.
  - Required: `CPUPWRCTLR_EL1` S3_0_C15_C2_7, PL1_RW, RAZ/WI or a stored value (needed for PSCI CPU_OFF and suspend).
  - Recommended defensively, to cover DEBUG builds and other TF-A configs: CLUSTERIDR_EL1 S3_0_C15_C3_1 (RO, 0 is fine)
    and CLUSTERCFR_EL1 S3_0_C15_C3_0 (RO; real DSU encodes the core count).
  - Optional: CPUACTLR_EL1 S3_0_C15_C1_0 and CPUECTLR_EL1 S3_0_C15_C1_4 (`cpu_reg_dump` for crash reports), plus
    CPUPSELR/CPUPCR/CPUPOR/CPUPMR_EL3 S3_6_C15_C8_0..3 (only for 1221012 on ≤r1p0).
  - Use `ARM_CP_CONST` or plain storage. Do **not** copy N1's `access_actlr_w` blindly. BL31 accesses these at EL3, so
    it is harmless there, but it changes behaviour for EL1 writers.
- **CPU properties**: `cntfrq=24000000` on both CPUs; `mp-affinity` 0x0 and 0x100. TF-A rz uses Aff1 as the core id
  (`plat/renesas/rz/common/plat_topology.c:23-33`), and Linux DT `reg` uses 0x0/0x100. The MT bit is left clear,
  which is a known fidelity gap versus silicon (INFERENCE: harmless for TF-A and Linux, which mask it).
- The machine must set the `cntfrq` property, not rely on BL31 writing CNTFRQ_EL0. QEMU's tick rate follows the
  property (`cpu.c:1430-1451`).

## Reproduce

```
cd tests/experiments/exp-001-smc-impdef
./run.sh all            # all tests; output equals run-all.log
./run.sh t1-virt-el2-smc        ./run.sh t2-virt-el1-hvc      ./run.sh t3-virt-el3-el2-smc
./run.sh t4-virt-el3-elf        ./run.sh t5-virt-el1-smc      ./run.sh t6-virt-el1-smc-el3
./run.sh t7-cntfrq-mpaff        ./run.sh t8-n1-el3-elf
# BL31 IMPDEF scan:
aarch64-linux-gnu-objdump -d <tfa-workdir>/build/v2l/release/bl31/bl31.elf | grep -iE 'msr|mrs' | grep -io 's3_[0-9]_c15_c[0-9]*_[0-9]'
```
