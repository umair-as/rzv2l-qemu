/*
 * M2 hello probe (M2-T08): prints "Hello from RZ/V2L" on SCIF0 the way
 * the board's TF-A does, without setting the UART up, and checks from the
 * CPU what a qtest cannot see. Results go through semihosting; the
 * greeting goes only to the serial line.
 *
 * Exit status: 0 every check passed, 1 a check failed, 2 the console
 * flush timed out (TEND never rose), so no meaningful result.
 *
 * Expected values and their sources: docs/units/M2-first-character/
 * spec.md (AC10, AC12, AC13) and design.md sections 2 to 5.
 */
#include <stdint.h>

/* start.S */
uint64_t semihost(uint64_t op, const void *param);
uint16_t read16(uint64_t addr);
uint32_t read32(uint64_t addr);
void write16(uint64_t addr, uint16_t value);

/* SCIF0 (device map; manual Table 22.3) */
#define SCIF0               0x1004b800UL
#define SMR                 0x00
#define SCR                 0x04
#define FTDR                0x06
#define FSR                 0x08
#define FDR                 0x0e
#define UNDEFINED           0x18
#define SMR_CM              0x0080
#define SCR_TE_RE           0x0030      /* as the firmware leaves it */
#define SCR_TIE             0x0080
#define FSR_TEND            0x0040
#define FDR_T_SHIFT         8
#define FDR_T_MASK          0x1f
#define FIFO_SIZE           16          /* Table 22.1 */

/*
 * CPG (manual section 7): 0x510 is an offset Table 7.5 does not list;
 * 0xb30 is CPG_CLUSTER_PCHMON, listed but not modelled. Both must fail
 * with a bus error rather than read as zero.
 */
#define CPG                 0x11010000UL
#define IRQC                0x110a0000UL
#define CPG_UNLISTED        0x510
#define CPG_CLUSTER_PCHMON  0xb30

/* GIC-600 (device map), register offsets from the Arm GICv3 architecture */
#define GICD                0x11900000UL
#define GICD_CTLR           0x0000
#define GICD_ISENABLER(n)   (0x0100 + 4 * ((n) / 32))
#define GICD_IPRIORITYR(n)  (0x0400 + (n))
#define GICD_IROUTER(n)     (0x6000 + 8 * (n))
#define GICD_ICFGR(n)       (0x0c00 + 4 * ((n) / 16))
#define GICD_CTLR_RWP       (1u << 31)
#define GICD_CTLR_ARE_NS    (1u << 4)
#define GICD_CTLR_ENGRP1A   (1u << 1)
#define GICR0               0x11940000UL
#define GICR_WAKER          0x0014
#define WAKER_PSLEEP        (1u << 1)
#define WAKER_CHILDREN      (1u << 2)
#define ICC_SRE_SRE         1

/* SCIF0 TXI is SPI 383 (device map, DTB-U interrupts), INTID 32 + 383 */
#define SCIF0_TXI_INTID     415

/*
 * OSTM2 (manual section 20): base Table 20.2, interrupt SPI 48 = INTID
 * 80, edge-rising (DT). Count clock P0 = 100 MHz; the generic timer
 * counts at 24 MHz.
 */
#define OSTM2               0x12801800UL
#define OSTM_CMP            0x00
#define OSTM_CNT            0x04
#define OSTM_TE             0x10
#define OSTM_TS             0x14
#define OSTM_TT             0x18
#define OSTM_CTL            0x20
#define OSTM_CTL_FREERUN    0x02
#define OSTM2_INTID         80
#define OSTM_ONESHOT_CMP    99999       /* (CMP + 1) / 100 MHz = 1 ms */
#define CNTFRQ_HZ           24000000UL
#define P0_HZ               100000000UL
#define SPURIOUS_INTID      1023

#define ESR_EC_DABT_CUR     0x25        /* data abort, same EL */
#define DFSC_SEA            0x10        /* synchronous external abort */

#define SH_SYS_WRITE0       0x04
#define SH_SYS_EXIT         0x18
#define ADP_APP_EXIT        0x20026

/* Polls give up after this many iterations instead of hanging */
#define SPIN_LIMIT          50000000UL

static volatile int expect_abort;
static volatile uint64_t abort_esr;
static volatile uint64_t irq_intid = SPURIOUS_INTID;
static volatile uint64_t irq_count;
static volatile uint64_t ostm_irq_count;
static volatile uint32_t ostm_cnt_at_irq;
static volatile int ostm_oneshot;
static volatile uint64_t cntvct_at_irq;
static int failures;

#define READ_SYSREG(r) ({ uint64_t v_; \
    __asm__ volatile("mrs %0, " #r : "=r"(v_)); v_; })
#define WRITE_SYSREG(r, v) \
    __asm__ volatile("msr " #r ", %0" : : "r"((uint64_t)(v)))

/* GICv3 CPU interface, by encoding */
#define ICC_SRE_EL1         S3_0_C12_C12_5
#define ICC_PMR_EL1         S3_0_C4_C6_0
#define ICC_IGRPEN1_EL1     S3_0_C12_C12_7
#define ICC_IAR1_EL1        S3_0_C12_C12_0
#define ICC_EOIR1_EL1       S3_0_C12_C12_1
#define READ_ICC(r)         READ_SYSREG(r)
#define WRITE_ICC(r, v)     WRITE_SYSREG(r, v)

static inline uint8_t mmio_read8(uint64_t a) { return *(volatile uint8_t *)a; }
static inline uint16_t mmio_read16(uint64_t a)
{
    return *(volatile uint16_t *)a;
}
static inline uint32_t mmio_read32(uint64_t a)
{
    return *(volatile uint32_t *)a;
}
static inline void mmio_write8(uint64_t a, uint8_t v)
{
    *(volatile uint8_t *)a = v;
}
static inline void mmio_write16(uint64_t a, uint16_t v)
{
    *(volatile uint16_t *)a = v;
}
static inline void mmio_write32(uint64_t a, uint32_t v)
{
    *(volatile uint32_t *)a = v;
}
static inline void mmio_write64(uint64_t a, uint64_t v)
{
    *(volatile uint64_t *)a = v;
}

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
        /* an exception while reporting one: park, run.sh reports no result */
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
    /* skip the faulting load or store */
    WRITE_SYSREG(elr_el1, READ_SYSREG(elr_el1) + 4);
}

void irq_handler(void);
void irq_handler(void)
{
    uint64_t intid = READ_ICC(ICC_IAR1_EL1) & 0xffffff;

    if (intid == SCIF0_TXI_INTID) {
        /* TIE off: the level line drops before the end of interrupt */
        mmio_write16(SCIF0 + SCR, SCR_TE_RE);
    }
    if (intid == OSTM2_INTID) {
        cntvct_at_irq = READ_SYSREG(cntvct_el0);
        ostm_irq_count++;
        ostm_cnt_at_irq = mmio_read32(OSTM2 + OSTM_CNT);
        if (ostm_oneshot) {
            /* As Linux ends a one-shot event: stop the counter */
            mmio_write8(OSTM2 + OSTM_TT, 1);
        }
    }
    irq_intid = intid;
    irq_count++;
    if (intid != SPURIOUS_INTID) {
        WRITE_ICC(ICC_EOIR1_EL1, intid);
    }
}

/* ---------------- the console, as TF-A drives it ---------------- */

/* Wait until the TX FIFO has room (ldrh FDR, FDR.T < 16); bounded here */
static int tfa_wait_fifo(void)
{
    for (uint64_t n = 0;
         ((mmio_read16(SCIF0 + FDR) >> FDR_T_SHIFT) & FDR_T_MASK) >= FIFO_SIZE;
         n++) {
        if (n == SPIN_LIMIT) {
            return -1;
        }
    }
    return 0;
}

/*
 * TF-A console_rz_putc (plat/renesas/rz/common/drivers/scifa.S:188-222
 * @ f59ed5a31), with the same accesses in the same order and widths:
 * for '\n' wait and store '\r' to FTDR (strb) first; wait and store the
 * byte; then, once per call, read FSR (ldrh) and write it back with
 * TEND cleared (strh). A '\n' thus clears TEND once, after both bytes.
 */
static int tfa_putc(char c)
{
    uint16_t fsr;

    if (c == '\n') {
        if (tfa_wait_fifo()) {
            return -1;
        }
        mmio_write8(SCIF0 + FTDR, '\r');
    }
    if (tfa_wait_fifo()) {
        return -1;
    }
    mmio_write8(SCIF0 + FTDR, c);
    fsr = mmio_read16(SCIF0 + FSR);
    mmio_write16(SCIF0 + FSR, fsr & ~FSR_TEND);
    return 0;
}

/* TF-A console_rz_flush (scifa.S:237-256): poll FSR until TEND = 1 */
static int tfa_flush(void)
{
    for (uint64_t n = 0; !(mmio_read16(SCIF0 + FSR) & FSR_TEND); n++) {
        if (n == SPIN_LIMIT) {
            return -1;
        }
    }
    return 0;
}

/* ---------------- checks ---------------- */

/* An access that must complete: report what it read */
static void check_reads(const char *name, uint64_t addr, uint16_t want)
{
    uint16_t v;

    expect_abort = 1;
    abort_esr = 0;
    v = read16(addr);
    if (!expect_abort) {
        puts_("FAIL ");
        puts_(name);
        puts_(": aborted, ESR ");
        puthex(abort_esr);
        puts_("\n");
        failures++;
        return;
    }
    expect_abort = 0;
    check(name, v, want, 0);
}

/* A 16-bit store that must take a synchronous external abort */
static void check_write_aborts(const char *name, uint64_t addr, uint16_t v)
{
    expect_abort = 1;
    abort_esr = 0;
    write16(addr, v);
    if (expect_abort) {
        expect_abort = 0;
        puts_("FAIL ");
        puts_(name);
        puts_(": write completed without an abort\n");
        failures++;
        return;
    }
    check("  ESR.EC", abort_esr >> 26, ESR_EC_DABT_CUR, 0);
    check("  ESR.DFSC", abort_esr & 0x3f, DFSC_SEA, 0);
}

/* A 32-bit load that must take a synchronous external abort */
static void check_read_aborts(const char *name, uint64_t addr)
{
    expect_abort = 1;
    abort_esr = 0;
    (void)read32(addr);
    if (expect_abort) {
        expect_abort = 0;
        puts_("FAIL ");
        puts_(name);
        puts_(": read completed without an abort\n");
        failures++;
        return;
    }
    check("  ESR.EC", abort_esr >> 26, ESR_EC_DABT_CUR, 0);
    check("  ESR.DFSC", abort_esr & 0x3f, DFSC_SEA, 0);
}

/* Bring the GIC up as a kernel does, for one SPI routed to this CPU */
static void gic_enable_spi(unsigned intid)
{
    uint64_t n;

    mmio_write32(GICD + GICD_CTLR, GICD_CTLR_ARE_NS | GICD_CTLR_ENGRP1A);
    for (n = 0; mmio_read32(GICD + GICD_CTLR) & GICD_CTLR_RWP; n++) {
        if (n == SPIN_LIMIT) {
            break;
        }
    }
    mmio_write32(GICR0 + GICR_WAKER,
                 mmio_read32(GICR0 + GICR_WAKER) & ~WAKER_PSLEEP);
    for (n = 0; mmio_read32(GICR0 + GICR_WAKER) & WAKER_CHILDREN; n++) {
        if (n == SPIN_LIMIT) {
            break;
        }
    }
    *(volatile uint8_t *)(GICD + GICD_IPRIORITYR(intid)) = 0xa0;
    mmio_write64(GICD + GICD_IROUTER(intid), 0);     /* Aff 0.0.0.0, CPU0 */
    mmio_write32(GICD + GICD_ISENABLER(intid), 1u << (intid % 32));

    check("ICC_SRE_EL1.SRE", READ_ICC(ICC_SRE_EL1) & ICC_SRE_SRE, 1, 1);
    WRITE_ICC(ICC_PMR_EL1, 0xf0);
    WRITE_ICC(ICC_IGRPEN1_EL1, 1);
    __asm__ volatile("isb; msr daifclr, #2" ::: "memory");
}

void probe_main(void);
void probe_main(void)
{
    static const char hello[] = "Hello from RZ/V2L\n";
    uint64_t n;

    puts_("M2 hello probe\n");

    /* AC12: the greeting, with no UART set-up of its own */
    for (const char *c = hello; *c; c++) {
        if (tfa_putc(*c)) {
            puts_("FAIL putc: FDR.T stayed at 16\nRESULT: FAIL (flush)\n");
            sh_exit(2);
        }
    }
    if (tfa_flush()) {
        puts_("FAIL flush: TEND did not rise\nRESULT: FAIL (flush)\n");
        sh_exit(2);
    }
    puts_("PASS greeting sent, TEND rose\n");

    /* S10 from the CPU: an undefined offset reads 0 without an abort */
    check_reads("SCIF0 +0x18 reads", SCIF0 + UNDEFINED, 0);

    /* AC10, decision (c) B: selecting clock synchronous mode aborts */
    puts_("-- SMR write with CM = 1\n");
    check_write_aborts("SMR CM = 1", SCIF0 + SMR, SMR_CM);
    check("SMR after the refused write", mmio_read16(SCIF0 + SMR), 0, 0);

    /* CPG registers the model does not implement fail visibly */
    puts_("-- CPG reads outside the model\n");
    check_read_aborts("CPG +0x510 (unlisted)", CPG + CPG_UNLISTED);
    check_read_aborts("CPG +0xb30 (PCHMON)", CPG + CPG_CLUSTER_PCHMON);

    /* AC13: SCIF0 TXI reaches the CPU as INTID 415 */
    puts_("-- SCIF0 TXI through the GIC\n");
    gic_enable_spi(SCIF0_TXI_INTID);
    mmio_write16(SCIF0 + SCR, SCR_TE_RE | SCR_TIE);  /* TDFE = 1: TXI rises */
    for (n = 0; !irq_count && n < SPIN_LIMIT; n++) {
        __asm__ volatile("yield");
    }
    check("IRQ taken", irq_count, 1, 1);
    check("IRQ INTID", irq_intid, SCIF0_TXI_INTID, 1);

    /*
     * OSTM2 one-shot as Linux arms it (renesas-ostm.c:85-97): the
     * interrupt arrives as INTID 80, no earlier than (CMP + 1) count
     * clocks after the start (Table 20.5), and only once.
     */
    puts_("-- OSTM2 one-shot interrupt\n");
    {
        uint32_t cfg = mmio_read32(GICD + GICD_ICFGR(OSTM2_INTID));
        uint64_t t0, min_ticks;

        /* Edge-triggered, as the DT says: bit 1 of the INTID's field */
        mmio_write32(GICD + GICD_ICFGR(OSTM2_INTID),
                     cfg | 2u << (2 * (OSTM2_INTID % 16)));
        gic_enable_spi(OSTM2_INTID);
        irq_count = 0;
        irq_intid = SPURIOUS_INTID;
        ostm_oneshot = 1;
        mmio_write32(OSTM2 + OSTM_CMP, OSTM_ONESHOT_CMP);
        mmio_write8(OSTM2 + OSTM_CTL, OSTM_CTL_FREERUN);
        t0 = READ_SYSREG(cntvct_el0);
        mmio_write8(OSTM2 + OSTM_TS, 1);
        for (n = 0; !irq_count && n < SPIN_LIMIT; n++) {
            __asm__ volatile("yield");
        }
        check("OSTM2 IRQ taken", irq_count, 1, 1);
        check("OSTM2 IRQ INTID", irq_intid, OSTM2_INTID, 1);
        check("OSTM2 CNT at IRQ >= CMP + 1",
              ostm_cnt_at_irq >= OSTM_ONESHOT_CMP + 1, 1, 0);
        min_ticks = (OSTM_ONESHOT_CMP + 1) * (CNTFRQ_HZ / 1000) /
                    (P0_HZ / 1000);
        check("generic timer ticks to IRQ >= 1 ms",
              cntvct_at_irq - t0 >= min_ticks, 1, 0);
        check("OSTM2 TE after the handler", mmio_read8(OSTM2 + OSTM_TE), 0, 0);
        /* Stopped: no second interrupt in another 2 ms */
        t0 = READ_SYSREG(cntvct_el0);
        while (READ_SYSREG(cntvct_el0) - t0 < 2 * min_ticks) {
            __asm__ volatile("yield");
        }
        check("OSTM2 IRQs in all", irq_count, 1, 0);

        /*
         * A compare value rewritten while free-running takes effect at
         * once (Table 20.5 rows c, d): start with a match 43 s away,
         * then move it 10 ms past the current count; the interrupt must
         * come no earlier than 10 ms after the count was read, and
         * within 500 ms. The margin keeps a stalled host from moving
         * the count past the new value first (row d would then wait for
         * the counter to wrap). The upper bounds below are wide: on a
         * loaded host QEMU's timer callbacks can run late while the
         * guest's generic counter keeps advancing. Callbacks never run
         * early, so the lower bounds are exact (less one generic timer
         * tick for rounding).
         */
        puts_("-- OSTM2 compare rewritten while free-running\n");
        irq_count = 0;
        mmio_write32(OSTM2 + OSTM_CMP, 0xfffffff0);
        mmio_write8(OSTM2 + OSTM_TS, 1);
        t0 = READ_SYSREG(cntvct_el0);
        mmio_write32(OSTM2 + OSTM_CMP,
                     mmio_read32(OSTM2 + OSTM_CNT) + 10 * (OSTM_ONESHOT_CMP + 1));
        while (!irq_count && READ_SYSREG(cntvct_el0) - t0 < 500 * min_ticks) {
            __asm__ volatile("yield");
        }
        check("OSTM2 IRQ after the rewrite", irq_count, 1, 1);
        check("generic timer ticks to the rewritten match >= 10 ms",
              cntvct_at_irq - t0 >= 10 * min_ticks - 1, 1, 0);

        /*
         * Interval mode as Linux's periodic event (renesas-ostm.c:107-119):
         * CMP = period - 1, an interrupt every period, the timer keeps
         * running. The n-th interrupt comes no earlier than n periods
         * after the start, and 50 interrupts come within 250 periods.
         */
        puts_("-- OSTM2 interval (periodic) interrupts\n");
        {
            uint64_t n_irq, t_last;

            ostm_oneshot = 0;
            ostm_irq_count = 0;
            mmio_write8(OSTM2 + OSTM_TT, 1);
            mmio_write32(OSTM2 + OSTM_CMP, OSTM_ONESHOT_CMP);
            mmio_write8(OSTM2 + OSTM_CTL, 0);
            t0 = READ_SYSREG(cntvct_el0);
            mmio_write8(OSTM2 + OSTM_TS, 1);
            while (ostm_irq_count < 50 &&
                   READ_SYSREG(cntvct_el0) - t0 < 250 * min_ticks) {
                __asm__ volatile("yield");
            }
            /* Count first: the handler stores the tick before counting */
            n_irq = ostm_irq_count;
            t_last = cntvct_at_irq;
            mmio_write8(OSTM2 + OSTM_TT, 1);
            check("OSTM2 interval IRQs within 250 periods >= 50",
                  n_irq >= 50, 1, 0);
            check("generic timer ticks to the n-th IRQ >= n periods",
                  t_last - t0 >= n_irq * min_ticks - 1, 1, 0);
            check("OSTM2 interval IRQ INTID", irq_intid, OSTM2_INTID, 1);
        }
    }

    /* Each OSTM register takes only its own access size (20.2.1) */
    puts_("-- OSTM2 accesses of the wrong size\n");
    check_read_aborts("OSTM2 TE as 32-bit", OSTM2 + OSTM_TE);
    check_read_aborts("OSTM2 +0x08 (unlisted)", OSTM2 + 0x08);

    /* The IRQC (Table 8.3) has no register at +0x08 */
    puts_("-- IRQC read outside Table 8.3\n");
    check_read_aborts("IRQC +0x08 (unlisted)", IRQC + 0x08);

    puts_(failures ? "RESULT: FAIL (" : "RESULT: PASS (");
    putdec(failures);
    puts_(" failures)\n");
    sh_exit(failures ? 1 : 0);
}
