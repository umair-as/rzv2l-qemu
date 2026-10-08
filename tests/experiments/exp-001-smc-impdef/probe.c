/* EXP-001 probe: SMC/HVC outcomes, IMPDEF sysregs, CNTFRQ/MPIDR. */
#include <stdint.h>

#define UART_DR  ((volatile uint32_t *)0x09000000)
#define UART_FR  ((volatile uint32_t *)0x09000018)

uint64_t do_smc(uint64_t fid, uint64_t a1, uint64_t a2, uint64_t a3);
uint64_t do_hvc(uint64_t fid, uint64_t a1, uint64_t a2, uint64_t a3);
uint64_t read_currentel(void);
void drop_to_el1(void (*entry)(void));
void secondary_entry(void);
uint64_t rd_cpupwrctlr(void), rd_cpuactlr(void), rd_cpuectlr(void);
uint64_t wr_cpupwrctlr(uint64_t), wr_cpuactlr(uint64_t), wr_cpuectlr(uint64_t);

#define TRAPPED 0xDEADDEADDEADDEADull
static volatile int trap_count;
static volatile int sec_flag;

static void putc_(char c)
{
    while (*UART_FR & (1 << 5)) { }
    *UART_DR = (uint32_t)c;
}
static void puts_(const char *s) { while (*s) { if (*s == '\n') putc_('\r'); putc_(*s++); } }
static void hex(uint64_t v)
{
    puts_("0x");
    for (int i = 60; i >= 0; i -= 4) putc_("0123456789abcdef"[(v >> i) & 0xf]);
}
#define SYSREG(name) ({ uint64_t _v; __asm__ volatile("mrs %0, " #name : "=r"(_v)); _v; })

/* Called from the vector stub. Fixes ELR so execution continues after the
 * faulting instruction and returns TRAPPED to be placed in x0. */
uint64_t exc_handler(void)
{
    uint64_t el = read_currentel(), esr, elr;
    if (el == 3) { esr = SYSREG(esr_el3); elr = SYSREG(elr_el3); }
    else if (el == 2) { esr = SYSREG(esr_el2); elr = SYSREG(elr_el2); }
    else { esr = SYSREG(esr_el1); elr = SYSREG(elr_el1); }
    uint32_t ec = (esr >> 26) & 0x3f;
    puts_("    [EXC taken to EL"); putc_('0' + el);
    puts_(" ESR="); hex(esr); puts_(" EC="); hex(ec); puts_(" ELR="); hex(elr); puts_("]\n");
    trap_count++;
    /* SMC/HVC exceptions (EC 0x17/0x16) already have ELR = next insn. */
    if (ec != 0x17 && ec != 0x16) elr += 4;
    if (el == 3) __asm__ volatile("msr elr_el3, %0" :: "r"(elr));
    else if (el == 2) __asm__ volatile("msr elr_el2, %0" :: "r"(elr));
    else __asm__ volatile("msr elr_el1, %0" :: "r"(elr));
    return TRAPPED;
}

static void call(const char *what, uint64_t (*fn)(uint64_t, uint64_t, uint64_t, uint64_t),
                 uint64_t fid)
{
    puts_("  "); puts_(what); puts_(" "); hex(fid);
    puts_("\n");
    uint64_t r = fn(fid, 0, 0, 0);
    puts_("    -> x0="); hex(r);
    puts_(r == TRAPPED ? " (trapped)\n" : (r == ~0ull ? " (=-1 NOT_SUPPORTED)\n" : "\n"));
}

static void reg(const char *name, uint64_t (*rd)(void), uint64_t (*wr)(uint64_t))
{
    puts_("  MRS "); puts_(name); puts_("\n");
    uint64_t v = rd();
    puts_("    -> "); hex(v); puts_(v == TRAPPED ? " (UNDEF)\n" : " (OK)\n");
    puts_("  MSR "); puts_(name); puts_("\n");
    v = wr(v == TRAPPED ? 0 : v);
    puts_("    -> "); puts_(v == TRAPPED ? "UNDEF\n" : "OK\n");
}

static void ident(void)
{
    puts_("  CurrentEL="); hex(read_currentel());
    puts_("\n  MIDR_EL1="); hex(SYSREG(midr_el1));
    puts_("\n  MPIDR_EL1="); hex(SYSREG(mpidr_el1));
    puts_("\n  CNTFRQ_EL0="); hex(SYSREG(cntfrq_el0));
    puts_("\n  ID_AA64PFR0_EL1="); hex(SYSREG(id_aa64pfr0_el1));
    puts_("\n");
}

static void tests(void)
{
    ident();
    call("SMC PSCI_VERSION", do_smc, 0x84000000);
    call("SMC OPTEE_CALLS_UID", do_smc, 0xBF00FF01);
    call("SMC SiP", do_smc, 0x82000011);
    call("HVC PSCI_VERSION", do_hvc, 0x84000000);
    reg("S3_0_C15_C2_7 (CPUPWRCTLR_EL1)", rd_cpupwrctlr, wr_cpupwrctlr);
    reg("S3_0_C15_C1_0 (CPUACTLR_EL1)", rd_cpuactlr, wr_cpuactlr);
    reg("S3_0_C15_C1_4 (CPUECTLR_EL1)", rd_cpuectlr, wr_cpuectlr);
}

void secondary_main(uint64_t ctx, uint64_t el)
{
    puts_("  [secondary up: ctx="); hex(ctx); puts_(" EL="); hex(el);
    puts_(" MPIDR="); hex(SYSREG(mpidr_el1)); puts_("]\n");
    sec_flag = 1;
}

static void smp_test(void)
{
    uint64_t r;
    puts_("  PSCI CPU_ON(target=0x1) via SMC then HVC\n");
    r = do_smc(0xC4000003, 0x1, (uint64_t)secondary_entry, 0x5ec);
    puts_("    smc -> "); hex(r); puts_("\n");
    if (r != 0) {
        r = do_hvc(0xC4000003, 0x1, (uint64_t)secondary_entry, 0x5ec);
        puts_("    hvc -> "); hex(r); puts_("\n");
    }
    for (volatile long i = 0; i < 20000000 && !sec_flag; i++) { }
    if (!sec_flag) puts_("    secondary did not report\n");
}

static void finish(void)
{
    puts_("=== DONE (traps=");
    hex(trap_count); puts_(") ===\n");
    do_smc(0x84000008, 0, 0, 0);  /* SYSTEM_OFF, whichever conduit works */
    do_hvc(0x84000008, 0, 0, 0);
    for (;;) __asm__ volatile("wfi");
}

static void el1_main(void)
{
    puts_("--- after drop to EL1 ---\n");
    tests();
    finish();
}

void main(uint64_t el)
{
    puts_("\n=== EXP-001 probe, entered at EL"); putc_('0' + el); puts_(" ===\n");
    tests();
    smp_test();
    if (el > 1)
        drop_to_el1(el1_main);
    finish();
}
