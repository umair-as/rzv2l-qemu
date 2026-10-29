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

/* GIC-600 (device map), register offsets from the Arm GICv3 architecture */
#define GICD                0x11900000UL
#define GICD_CTLR           0x0000
#define GICD_ISENABLER(n)   (0x0100 + 4 * ((n) / 32))
#define GICD_IPRIORITYR(n)  (0x0400 + (n))
#define GICD_IROUTER(n)     (0x6000 + 8 * (n))
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

    /* AC13: SCIF0 TXI reaches the CPU as INTID 415 */
    puts_("-- SCIF0 TXI through the GIC\n");
    gic_enable_spi(SCIF0_TXI_INTID);
    mmio_write16(SCIF0 + SCR, SCR_TE_RE | SCR_TIE);  /* TDFE = 1: TXI rises */
    for (n = 0; !irq_count && n < SPIN_LIMIT; n++) {
        __asm__ volatile("yield");
    }
    check("IRQ taken", irq_count, 1, 1);
    check("IRQ INTID", irq_intid, SCIF0_TXI_INTID, 1);

    puts_(failures ? "RESULT: FAIL (" : "RESULT: PASS (");
    putdec(failures);
    puts_(" failures)\n");
    sh_exit(failures ? 1 : 0);
}
