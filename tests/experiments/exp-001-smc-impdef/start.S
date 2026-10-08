/*
 * EXP-001 bare-metal probe: entry, vectors, SMC/HVC/sysreg wrappers.
 * Linked at 0x40080000. Same code is emitted as a raw arm64 "Image"
 * (QEMU treats it as Linux) and as an ELF (QEMU treats it as non-Linux).
 */
#define STACK_TOP   0x4F000000
#define STACK_SZ    0x10000

    .section .text.head, "ax"
    .globl _head
_head:
    /* arm64 Linux Image header (Documentation/arch/arm64/booting.rst) */
    b       _start                  /* code0 */
    .word   0                       /* code1 */
    .quad   0x80000                 /* text_offset */
    .quad   _image_end - _head      /* image_size */
    .quad   0xa                     /* flags: LE, 4K pages, anywhere */
    .quad   0, 0, 0
    .ascii  "ARM\x64"               /* magic at offset 0x38 */
    .word   0

    .text
    .globl _start
_start:
    mrs     x9, mpidr_el1
    and     x9, x9, #0xffff
    cbz     x9, 1f
2:  wfe                             /* non-boot CPUs spin (no-PSCI case) */
    b       2b
1:  ldr     x9, =STACK_TOP
    mov     sp, x9
    adr     x10, vectors
    mrs     x11, CurrentEL
    lsr     x11, x11, #2
    cmp     x11, #3
    b.ne    3f
    msr     vbar_el3, x10
    msr     vbar_el2, x10
    msr     vbar_el1, x10
    b       5f
3:  cmp     x11, #2
    b.ne    4f
    msr     vbar_el2, x10
    msr     vbar_el1, x10
    b       5f
4:  msr     vbar_el1, x10
5:  isb
    mov     x0, x11
    bl      main
6:  wfi
    b       6b

    /* secondary entry from PSCI CPU_ON; x0 = context_id */
    .globl secondary_entry
secondary_entry:
    ldr     x9, =(STACK_TOP - STACK_SZ)
    mov     sp, x9
    adr     x10, vectors
    mrs     x11, CurrentEL
    lsr     x11, x11, #2
    cmp     x11, #2
    b.ne    1f
    msr     vbar_el2, x10
1:  msr     vbar_el1, x10
    isb
    mov     x1, x11
    bl      secondary_main
2:  wfi
    b       2b

    /* drop_to_el1(entry): from EL2 or EL3 to NS EL1h, new stack */
    .globl drop_to_el1
drop_to_el1:
    mrs     x11, CurrentEL
    lsr     x11, x11, #2
    mov     x12, #(1 << 31)         /* HCR_EL2.RW = 1 */
    mov     x13, #0x3c5             /* SPSR: DAIF masked, EL1h */
    ldr     x14, =(STACK_TOP - 2*STACK_SZ)
    msr     sp_el1, x14
    adr     x10, vectors
    msr     vbar_el1, x10
    cmp     x11, #3
    b.ne    1f
    ldr     x15, =(STACK_TOP - 3*STACK_SZ)
    msr     sp_el2, x15             /* EL2 traps (e.g. N1 ACTLR) need a stack */
    msr     hcr_el2, x12
    mov     x12, #0x431             /* SCR_EL3: NS | RES1(5:4) | RW; SMD=0 HCE=0 */
    msr     scr_el3, x12
    msr     spsr_el3, x13
    msr     elr_el3, x0
    isb
    eret
1:  msr     hcr_el2, x12
    msr     spsr_el2, x13
    msr     elr_el2, x0
    isb
    eret

    .globl do_smc
do_smc:  smc #0
    ret
    .globl do_hvc
do_hvc:  hvc #0
    ret
    .globl read_currentel
read_currentel:
    mrs x0, CurrentEL
    lsr x0, x0, #2
    ret

/* IMPDEF register probes; on UNDEF the handler skips the insn and sets x0 */
    .globl rd_cpupwrctlr, wr_cpupwrctlr, rd_cpuactlr, wr_cpuactlr, rd_cpuectlr, wr_cpuectlr
rd_cpupwrctlr: mrs x0, S3_0_C15_C2_7
    ret
wr_cpupwrctlr: mov x1, x0
    mov x0, #0
    msr S3_0_C15_C2_7, x1
    ret
rd_cpuactlr:   mrs x0, S3_0_C15_C1_0
    ret
wr_cpuactlr:   mov x1, x0
    mov x0, #0
    msr S3_0_C15_C1_0, x1
    ret
rd_cpuectlr:   mrs x0, S3_0_C15_C1_4
    ret
wr_cpuectlr:   mov x1, x0
    mov x0, #0
    msr S3_0_C15_C1_4, x1
    ret

/* ---------------- vector table ---------------- */
.macro ventry
    .balign 0x80
    b       exc_common
.endm
    .balign 0x800
vectors:
    .rept 16
    ventry
    .endr

exc_common:
    sub     sp, sp, #(16 * 16)
    stp     x1, x2, [sp, #0]
    stp     x3, x4, [sp, #16]
    stp     x5, x6, [sp, #32]
    stp     x7, x8, [sp, #48]
    stp     x9, x10, [sp, #64]
    stp     x11, x12, [sp, #80]
    stp     x13, x14, [sp, #96]
    stp     x15, x16, [sp, #112]
    stp     x17, x18, [sp, #128]
    stp     x29, x30, [sp, #144]
    bl      exc_handler             /* returns x0 = value to hand back in x0 */
    ldp     x1, x2, [sp, #0]
    ldp     x3, x4, [sp, #16]
    ldp     x5, x6, [sp, #32]
    ldp     x7, x8, [sp, #48]
    ldp     x9, x10, [sp, #64]
    ldp     x11, x12, [sp, #80]
    ldp     x13, x14, [sp, #96]
    ldp     x15, x16, [sp, #112]
    ldp     x17, x18, [sp, #128]
    ldp     x29, x30, [sp, #144]
    add     sp, sp, #(16 * 16)
    eret
