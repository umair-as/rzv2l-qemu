/*
 * M2 hello probe: Image header, entry, vectors, helpers.
 * Built from tests/probes/m1-skeleton/start.S. Linked at 0x48200000,
 * where QEMU places an arm64 Image whose header says text_offset 0 on
 * rzv2l-smarc (qemu hw/arm/boot.c:858-870).
 */

    .section .text.head, "ax"
    .globl _head
_head:
    /* arm64 Linux Image header (Documentation/arch/arm64/booting.rst) */
    b       _start                  /* code0 */
    .word   0                       /* code1 */
    .quad   0                       /* text_offset */
    .quad   __bss_end - _head       /* image_size, including .bss */
    .quad   0xa                     /* flags: LE, 4K pages, anywhere */
    .quad   0, 0, 0
    .ascii  "ARM\x64"               /* magic at offset 0x38 */
    .word   0

    .text
    /* CPU0 entry from QEMU's boot stub (x0 = DTB address, unused) */
    .globl _start
_start:
    ldr     x9, =__bss_start        /* zero .bss: it is not in the Image */
    ldr     x10, =__bss_end
1:  cmp     x9, x10
    b.hs    2f
    str     xzr, [x9], #8
    b       1b
2:  ldr     x9, =stack0_top
    mov     sp, x9
    adr     x10, vectors
    msr     vbar_el1, x10
    isb
    bl      probe_main              /* never returns: exits via semihosting */
3:  wfi
    b       3b

    /* x0 = operation, x1 = parameter; result in x0 (A64 semihosting) */
    .globl semihost
semihost:
    hlt     #0xf000
    ret

    /* One 16-bit load or store. If it aborts, the handler skips it. */
    .globl read16
read16:
    ldrh    w0, [x0]
    ret

    .globl write16
write16:
    strh    w1, [x0]
    ret

/*
 * Vector table. The IRQ entry for the current EL with SP_ELx (offset
 * 0x280) goes to irq_handler; every other entry goes to exc_handler.
 */
.macro save_regs
    sub     sp, sp, #(12 * 16)
    stp     x0, x1, [sp, #0]
    stp     x2, x3, [sp, #16]
    stp     x4, x5, [sp, #32]
    stp     x6, x7, [sp, #48]
    stp     x8, x9, [sp, #64]
    stp     x10, x11, [sp, #80]
    stp     x12, x13, [sp, #96]
    stp     x14, x15, [sp, #112]
    stp     x16, x17, [sp, #128]
    stp     x18, x29, [sp, #144]
    str     x30, [sp, #160]
.endm

.macro restore_regs
    ldp     x0, x1, [sp, #0]
    ldp     x2, x3, [sp, #16]
    ldp     x4, x5, [sp, #32]
    ldp     x6, x7, [sp, #48]
    ldp     x8, x9, [sp, #64]
    ldp     x10, x11, [sp, #80]
    ldp     x12, x13, [sp, #96]
    ldp     x14, x15, [sp, #112]
    ldp     x16, x17, [sp, #128]
    ldp     x18, x29, [sp, #144]
    ldr     x30, [sp, #160]
    add     sp, sp, #(12 * 16)
.endm

.macro ventry target
    .balign 0x80
    b       \target
.endm

    .balign 0x800
vectors:
    ventry exc_common               /* current EL, SP_EL0 */
    ventry exc_common
    ventry exc_common
    ventry exc_common
    ventry exc_common               /* current EL, SP_ELx: sync */
    ventry irq_common               /* current EL, SP_ELx: IRQ */
    ventry exc_common
    ventry exc_common
    .rept 8                         /* lower ELs */
    ventry exc_common
    .endr

exc_common:
    save_regs
    bl      exc_handler
    restore_regs
    eret

irq_common:
    save_regs
    bl      irq_handler
    restore_regs
    eret

    .bss
    .balign 16
    .space  0x2000
stack0_top:
