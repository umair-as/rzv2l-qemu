/*
 * M1 skeleton probe (M1-T05): checks, from inside the guest, what a
 * qtest cannot see. Reports one line per check through semihosting and
 * exits 0 when every check passes, 1 otherwise.
 *
 * Expected values and their sources: docs/units/M1-machine-skeleton/
 * spec.md (AC03-AC06, AC13, AC14) and design.md "Probe payload".
 */
#include <stdint.h>

/* start.S */
uint64_t smc_call(uint64_t fid, uint64_t a1, uint64_t a2, uint64_t a3);
uint64_t semihost(uint64_t op, const void *param);
uint32_t read32(uint64_t addr);
uint64_t read_currentel(void);
void secondary_entry(void);
extern char _head[];

#define IMAGE_BASE          0x48200000UL    /* boot.c: loader_start + 2 MiB */

#define MIDR_A55_R2P0       0x412fd050UL    /* Cortex-A55 r2p0 */
#define CNTFRQ_HZ           24000000UL
#define CPU0_AFF            0x0UL           /* DT cpu@0 */
#define CPU1_AFF            0x100UL         /* DT cpu@100 */
#define MPIDR_AFF_MASK      0xff00ffffffUL  /* Aff3, Aff2, Aff1, Aff0 */
/*
 * ID_AA64PFR0_EL1.EL2, bits [11:8]. The model sets has_el2=false (spec.md
 * "Instantiation"); the A55 itself has EL2 (device-map.md section 4, gap 14).
 * This asserts the model's recorded choice, not a manual value.
 */
#define PFR0_EL2_SHIFT      8
#define PFR0_EL2_MASK       0xfUL

#define PSCI_CPU_ON_64      0xc4000003UL
#define PSCI_SUCCESS        0

#define UNMAPPED_ADDR       0x10000000UL    /* no device in the M1 map */
#define SYSC_NON_ID_ADDR    0x11020000UL    /* SYSC offset 0, not an ID reg */

#define ESR_EC_DABT_CUR     0x25            /* data abort, same EL */
#define DFSC_SEA            0x10            /* synchronous external abort */

#define SH_SYS_WRITE0       0x04
#define SH_SYS_EXIT         0x18
#define ADP_APP_EXIT        0x20026

struct cpu_info {
    uint64_t mpidr, midr, cntfrq, el, pfr0_el2;
};

static volatile struct {
    uint64_t done;
    struct cpu_info info;
} mailbox;

static volatile int expect_abort;
static volatile uint64_t abort_esr;
static int failures;

#define READ_SYSREG(r) ({ uint64_t v_; \
    __asm__ volatile("mrs %0, " #r : "=r"(v_)); v_; })
#define WRITE_SYSREG(r, v) \
    __asm__ volatile("msr " #r ", %0" : : "r"((uint64_t)(v)))

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

static void putdec(uint64_t v)
{
    char buf[21];
    int i = 20;

    buf[i] = 0;
    do {
        buf[--i] = '0' + v % 10;
        v /= 10;
    } while (v);
    puts_(&buf[i]);
}

static void sh_exit(uint64_t status)
{
    static uint64_t block[2];

    block[0] = ADP_APP_EXIT;
    block[1] = status;
    semihost(SH_SYS_EXIT, block);
    for (;;) {
        __asm__ volatile("wfi");
    }
}

/* One check: "PASS name: got" or "FAIL name: got (expected want)" */
static void check(const char *name, uint64_t got, uint64_t want, int dec)
{
    puts_(got == want ? "PASS " : "FAIL ");
    puts_(name);
    puts_(": ");
    dec ? putdec(got) : puthex(got);
    if (got != want) {
        puts_(" (expected ");
        dec ? putdec(want) : puthex(want);
        puts_(")");
        failures++;
    }
    puts_("\n");
}

/* ---------------- exceptions ---------------- */

void exc_handler(void);
void exc_handler(void)
{
    static volatile int in_handler;
    uint64_t esr = READ_SYSREG(esr_el1);

    if (in_handler) {
        /*
         * An exception while reporting one: most likely HLT is UNDEF
         * because semihosting is off. Nothing can be printed; park the
         * CPU so run.sh reports "no result" after its timeout.
         */
        for (;;) {
            __asm__ volatile("wfi");
        }
    }
    if (!expect_abort) {
        in_handler = 1;
        puts_("FAIL unexpected exception: ESR ");
        puthex(esr);
        puts_(" ELR ");
        puthex(READ_SYSREG(elr_el1));
        puts_("\n");
        sh_exit(1);
    }
    abort_esr = esr;
    expect_abort = 0;
    /* Skip the faulting load */
    WRITE_SYSREG(elr_el1, READ_SYSREG(elr_el1) + 4);
}

static void check_aborts(const char *name, uint64_t addr)
{
    uint64_t esr;
    char ec_name[64], dfsc_name[64];
    int i, n;

    abort_esr = 0;
    expect_abort = 1;
    (void)read32(addr);
    if (expect_abort) {
        /* No exception: the read returned data */
        expect_abort = 0;
        puts_("FAIL ");
        puts_(name);
        puts_(": read completed without an abort\n");
        failures++;
        return;
    }
    esr = abort_esr;
    for (n = 0; name[n] && n < 48; n++) {
        ec_name[n] = dfsc_name[n] = name[n];
    }
    for (i = 0; " ESR.EC"[i]; i++) {
        ec_name[n + i] = " ESR.EC"[i];
    }
    ec_name[n + i] = 0;
    for (i = 0; " DFSC"[i]; i++) {
        dfsc_name[n + i] = " DFSC"[i];
    }
    dfsc_name[n + i] = 0;
    check(ec_name, esr >> 26, ESR_EC_DABT_CUR, 0);
    check(dfsc_name, esr & 0x3f, DFSC_SEA, 0);
}

/* ---------------- CPUs ---------------- */

static void read_cpu_info(struct cpu_info *ci)
{
    ci->mpidr = READ_SYSREG(mpidr_el1);
    ci->midr = READ_SYSREG(midr_el1);
    ci->cntfrq = READ_SYSREG(cntfrq_el0);
    ci->el = read_currentel();
    ci->pfr0_el2 = (READ_SYSREG(id_aa64pfr0_el1) >> PFR0_EL2_SHIFT) &
                   PFR0_EL2_MASK;
}

static void check_cpu(const char *cpu, const struct cpu_info *ci,
                      uint64_t aff)
{
    puts_("-- ");
    puts_(cpu);
    puts_("\n");
    check("MPIDR_EL1 affinity", ci->mpidr & MPIDR_AFF_MASK, aff, 0);
    check("MIDR_EL1", ci->midr, MIDR_A55_R2P0, 0);
    check("CNTFRQ_EL0", ci->cntfrq, CNTFRQ_HZ, 1);
    check("CurrentEL", ci->el, 1, 1);
    check("ID_AA64PFR0_EL1.EL2", ci->pfr0_el2, 0, 1);
}

void secondary_main(void);
void secondary_main(void)
{
    struct cpu_info ci;

    read_cpu_info(&ci);
    mailbox.info.mpidr = ci.mpidr;
    mailbox.info.midr = ci.midr;
    mailbox.info.cntfrq = ci.cntfrq;
    mailbox.info.el = ci.el;
    mailbox.info.pfr0_el2 = ci.pfr0_el2;
    __asm__ volatile("dsb sy" ::: "memory");
    mailbox.done = 1;
    __asm__ volatile("dsb sy; sev" ::: "memory");
}

void probe_main(void);
void probe_main(void)
{
    struct cpu_info ci;
    uint64_t ret, spins;

    puts_("M1 skeleton probe\n");
    check("Image load address", (uint64_t)_head, IMAGE_BASE, 0);

    /* AC03, AC05, AC06 */
    read_cpu_info(&ci);
    check_cpu("CPU0", &ci, CPU0_AFF);

    /* AC04: CPU1 is off until PSCI CPU_ON over SMC */
    puts_("-- CPU1 via PSCI CPU_ON(0x100)\n");
    ret = smc_call(PSCI_CPU_ON_64, CPU1_AFF, (uint64_t)secondary_entry, 0);
    check("CPU_ON return", ret, PSCI_SUCCESS, 1);
    for (spins = 0; !mailbox.done && spins < 100000000; spins++) {
        __asm__ volatile("yield");
    }
    check("CPU1 reported", mailbox.done, 1, 1);
    if (mailbox.done) {
        ci.mpidr = mailbox.info.mpidr;
        ci.midr = mailbox.info.midr;
        ci.cntfrq = mailbox.info.cntfrq;
        ci.el = mailbox.info.el;
        ci.pfr0_el2 = mailbox.info.pfr0_el2;
        check_cpu("CPU1", &ci, CPU1_AFF);
    }

    /* AC14, AC13: unmodelled addresses abort instead of reading as zero */
    puts_("-- aborts\n");
    check_aborts("unmapped 0x10000000", UNMAPPED_ADDR);
    check_aborts("SYSC offset 0x0", SYSC_NON_ID_ADDR);

    puts_(failures ? "RESULT: FAIL (" : "RESULT: PASS (");
    putdec(failures);
    puts_(" failures)\n");
    sh_exit(failures ? 1 : 0);
}
