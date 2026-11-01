/*
 * EL3 secure-access probe: checks, from a real CPU, the two registers
 * whose behaviour depends on the security of the access, which a qtest
 * (accesses without attributes) cannot see:
 *   - GIC-600 GICR_PWRR (GIC-600 r1p6 TRM 4.4.5, p.4-132): the field
 *     layout and the RDPD, RDGPD/RDGPO and RDAG rules from EL3; RAZ/WI
 *     from Non-secure EL1 (Secure-only while GICD_CTLR.DS is 0).
 *   - TZC0 and TZC3 BUILD_CONFIG: filter and region counts from EL3
 *     (manual 13.1); a Non-secure read or write ends in a synchronous
 *     external abort, as U-Boot's read does on the board (EVK-R79).
 *   - MPIDR_EL1 of core 0: MT (bit 24) = 1, the core number in Aff1. The
 *     board's OP-TEE (82a5cd3b, get_core_pos_mpidr()) finds core 1's
 *     tables only this way, and brings core 1 up on the board (EVK-L07).
 * Order: EL3 checks; drop to Non-secure EL1; Non-secure checks; SMC back
 * to EL3; the final EL3 check; exit through semihosting.
 * Exit status: 0 every check passed, 1 a check failed.
 */
#include <stdint.h>

/* start.S */
uint64_t semihost(uint64_t op, const void *param);
uint32_t read32(uint64_t addr);
void write32(uint64_t addr, uint32_t value);
void drop_to_ns_el1(void (*entry)(void));
void smc0(void);

/* GIC-600 (device map): Redistributor n at GICR0 + n * 0x20000 */
#define GICR(n)             (0x11940000UL + (n) * 0x20000UL)
#define GICR_WAKER          0x0014
#define GICR_PWRR           0x0024
#define WAKER_PSLEEP        (1u << 1)
/* GICR_PWRR fields (TRM Table 4-26) */
#define PWRR_RDPD           (1u << 0)
#define PWRR_RDAG           (1u << 1)
#define PWRR_RDGPD          (1u << 2)
#define PWRR_RDGPO          (1u << 3)
#define PWRR_STATE          0xfu        /* RDGPO, RDGPD, RDAG (WO), RDPD */
#define PWRR_IDS            0x00ffff00u /* RDG [23:16], RDGO [15:8] */

/* TZC-400 BUILD_CONFIG: filters - 1 [25:24], regions - 1 [4:0] */
#define TZC(n)              (0x11040000UL + (n) * 0x10000UL)
#define BUILD_CONFIG        0x000
#define ACTION              0x004
#define BC_COUNTS           0x0300001fu

#define EC_SMC64            0x17
#define EC_DABT_CUR         0x25
#define DFSC_SEA            0x10

#define SH_SYS_WRITE0       0x04
#define SH_SYS_EXIT         0x18
#define ADP_APP_EXIT        0x20026

#define READ_SYSREG(r) ({ uint64_t v_; \
    __asm__ volatile("mrs %0, " #r : "=r"(v_)); v_; })
#define WRITE_SYSREG(r, v) \
    __asm__ volatile("msr " #r ", %0" : : "r"((uint64_t)(v)))

static volatile int expect_abort;
static volatile uint64_t abort_esr;
static int failures;

/* ---------------- output through semihosting ---------------- */

static void puts_(const char *s)
{
    semihost(SH_SYS_WRITE0, s);
}

static void puthex(uint64_t v)
{
    char buf[19];
    int i;

    buf[0] = '0';
    buf[1] = 'x';
    for (i = 0; i < 16; i++) {
        buf[2 + i] = "0123456789abcdef"[(v >> (60 - 4 * i)) & 0xf];
    }
    buf[18] = 0;
    puts_(buf);
}

static void __attribute__((noreturn)) sh_exit(uint64_t status)
{
    static uint64_t block[2];

    block[0] = ADP_APP_EXIT;
    block[1] = status;
    semihost(SH_SYS_EXIT, block);
    for (;;) {
        __asm__ volatile("wfi");
    }
}

static void check(const char *name, uint64_t got, uint64_t want)
{
    puts_(got == want ? "PASS " : "FAIL ");
    puts_(name);
    puts_(": ");
    puthex(got);
    if (got != want) {
        puts_(" (expected ");
        puthex(want);
        puts_(")");
        failures++;
    }
    puts_("\n");
}

static void __attribute__((noreturn)) finish(void)
{
    puts_(failures ? "RESULT: FAIL\n" : "RESULT: PASS\n");
    sh_exit(failures ? 1 : 0);
}

/* ---------------- exceptions ---------------- */

static void __attribute__((noreturn)) unexpected(uint64_t esr, uint64_t elr)
{
    puts_("FAIL unexpected exception: ESR ");
    puthex(esr);
    puts_(" ELR ");
    puthex(elr);
    puts_("\n");
    sh_exit(1);
}

static void el3_final(void);

/* EL3: only the SMC from Non-secure EL1 is expected */
void el3_exc(void);
void el3_exc(void)
{
    uint64_t esr = READ_SYSREG(esr_el3);

    if ((esr >> 26) != EC_SMC64) {
        unexpected(esr, READ_SYSREG(elr_el3));
    }
    el3_final();
    finish();
}

/* Non-secure EL1: an expected abort is recorded and its access skipped */
void el1_exc(void);
void el1_exc(void)
{
    uint64_t esr = READ_SYSREG(esr_el1);

    if (!expect_abort) {
        unexpected(esr, READ_SYSREG(elr_el1));
    }
    abort_esr = esr;
    expect_abort = 0;
    WRITE_SYSREG(elr_el1, READ_SYSREG(elr_el1) + 4);
}

/* A synchronous external abort on a data access at the current EL */
static uint64_t sea(uint64_t esr)
{
    return (esr >> 26) == EC_DABT_CUR && (esr & 0x3f) == DFSC_SEA;
}

/* ---------------- checks ---------------- */

static uint32_t pwrr(int n)
{
    return read32(GICR(n) + GICR_PWRR);
}

static void el3_checks(void)
{
    puts_("-- EL3 (Secure)\n");

    /* MPIDR_EL1: bit 31 RES1, MT (bit 24) = 1, core 0 at Aff1 = 0 */
    check("MPIDR_EL1 of core 0", READ_SYSREG(mpidr_el1) & 0xffffffffull,
          0x81000000);

    /* Both cores in Redistributor group 0, at offsets 0 and 1 */
    check("GICR0_PWRR RDG/RDGO", pwrr(0) & PWRR_IDS, 0x000);
    check("GICR1_PWRR RDG/RDGO", pwrr(1) & PWRR_IDS, 0x100);

    /* RDPD = 0: both powered up, the group reaches its state at once */
    write32(GICR(0) + GICR_PWRR, 0);
    write32(GICR(1) + GICR_PWRR, 0);
    check("RDPD 0 on both: GICR0_PWRR state", pwrr(0) & PWRR_STATE, 0);

    /* "Writes to 1 ignored if GICR_WAKER.ProcessorSleep != 1" */
    write32(GICR(0) + GICR_WAKER, 0);
    write32(GICR(0) + GICR_PWRR, PWRR_RDPD);
    check("RDPD 1 without ProcessorSleep: ignored", pwrr(0) & PWRR_STATE, 0);

    /* With ProcessorSleep the write sticks; core 1 still holds the group */
    write32(GICR(0) + GICR_WAKER, WAKER_PSLEEP);
    write32(GICR(0) + GICR_PWRR, PWRR_RDPD);
    check("RDPD 1 with ProcessorSleep, core 1 up: GICR0 state",
          pwrr(0) & PWRR_STATE, PWRR_RDPD);

    /* "If all other cores ... have RDPD == 1, ... also sets RDGPD = 1" */
    write32(GICR(1) + GICR_WAKER, WAKER_PSLEEP);
    write32(GICR(1) + GICR_PWRR, PWRR_RDPD);
    check("RDPD 1 on both: GICR0 state", pwrr(0) & PWRR_STATE,
          PWRR_RDPD | PWRR_RDGPD | PWRR_RDGPO);
    check("RDPD 1 on both: GICR1 state", pwrr(1) & PWRR_STATE,
          PWRR_RDPD | PWRR_RDGPD | PWRR_RDGPO);

    /* RDAG applies RDPD = 0 to the whole group */
    write32(GICR(0) + GICR_PWRR, PWRR_RDAG);
    check("RDAG with RDPD 0 from core 0: GICR1 state",
          pwrr(1) & PWRR_STATE, 0);

    /* TZC: 1 filter on TZC0, 4 on TZC3, 9 regions each (manual 13.1) */
    check("TZC0 BUILD_CONFIG filters/regions",
          read32(TZC(0) + BUILD_CONFIG) & BC_COUNTS, 0x00000008);
    check("TZC3 BUILD_CONFIG filters/regions",
          read32(TZC(3) + BUILD_CONFIG) & BC_COUNTS, 0x03000008);
    write32(TZC(0) + ACTION, 1);
    check("TZC0 ACTION written from EL3", read32(TZC(0) + ACTION), 1);
}

static void __attribute__((noreturn)) ns_main(void)
{
    uint32_t v;

    puts_("-- Non-secure EL1\n");

    /* Secure-only: RAZ (the Secure view of GICR1_PWRR has RDGO = 1) */
    check("GICR1_PWRR from Non-secure: RAZ", pwrr(1), 0);
    /* WI: core 1 has ProcessorSleep, so a Secure write would stick */
    write32(GICR(1) + GICR_PWRR, PWRR_RDPD);

    expect_abort = 1;
    abort_esr = 0;
    v = read32(TZC(0) + BUILD_CONFIG);
    check("TZC0 BUILD_CONFIG read from Non-secure: external abort",
          sea(abort_esr), 1);
    expect_abort = 1;
    abort_esr = 0;
    write32(TZC(0) + ACTION, 0);
    check("TZC0 ACTION write from Non-secure: external abort",
          sea(abort_esr), 1);
    (void)v;

    smc0();
    unexpected(0, 0);
}

static void el3_final(void)
{
    puts_("-- EL3 (Secure), after the Non-secure accesses\n");
    check("GICR1_PWRR Non-secure write ignored: GICR1 state",
          pwrr(1) & PWRR_STATE, 0);
    check("TZC0 ACTION Non-secure write ignored", read32(TZC(0) + ACTION), 1);
}

void el3_main(void);
void el3_main(void)
{
    el3_checks();
    drop_to_ns_el1(ns_main);
}
