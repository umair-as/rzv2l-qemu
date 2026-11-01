/*
 * EL3 secure-access probe: entry at EL3, the drop to Non-secure EL1,
 * vectors and helpers. Linked at 0x44000000, where firmware mode (-bios)
 * puts BL31; the machine's BL2 stub enters it at EL3. It carries an arm64
 * Image header so the same file also serves as -kernel, which firmware
 * mode requires and the probe never enters.
 */

    .section .text.head, "ax"
    .globl _head
_head:
    b       _start                  /* code0 */
    .word   0                       /* code1 */
    .quad   0                       /* text_offset */
    .quad   __bss_end - _head       /* image_size, including .bss */
    .quad   0xa                     /* flags: LE, 4K pages, anywhere */
    .quad   0, 0, 0
    .ascii  "ARM\x64"               /* magic at offset 0x38 */
    .word   0

    .text
    /* CPU0 from the BL2 stub, at EL3 (x0 = BL2's parameter block, unused) */
_start:
    ldr     x9, =__bss_start
    ldr     x10, =__bss_end
1:  cmp     x9, x10
    b.hs    2f
    str     xzr, [x9], #8
    b       1b
2:  ldr     x9, =stack_el3_top
    mov     sp, x9
    adr     x10, vectors_el3
    msr     vbar_el3, x10
    isb
    bl      el3_main                /* never returns */
3:  wfi
    b       3b

    /*
     * drop_to_ns_el1(entry): SCR_EL3.NS = 1 and RW = 1 (bits 0 and 10),
     * then ERET to EL1h with DAIF masked. The MMU stays off, so every
     * access from EL1 is Non-secure.
     */
    .globl drop_to_ns_el1
drop_to_ns_el1:
    mov     x9, #((1 << 10) | 1)
    msr     scr_el3, x9
    msr     elr_el3, x0
    mov     x9, #0x3c5
    msr     spsr_el3, x9
    ldr     x9, =stack_el1_top
    msr     sp_el1, x9
    adr     x9, vectors_el1
    msr     vbar_el1, x9
    isb
    eret

    /* SMC from Non-secure EL1 back to EL3 (el3_exc handles it) */
    .globl smc0
smc0:
    smc     #0
    ret

    /* x0 = operation, x1 = parameter; result in x0 (A64 semihosting) */
    .globl semihost
semihost:
    hlt     #0xf000
    ret

    /* One 32-bit load or store; if it aborts, the handler skips it */
    .globl read32
read32:
    ldr     w0, [x0]
    ret

    .globl write32
write32:
    str     w1, [x0]
    ret

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

    /* Every entry of each table goes to that EL's handler */
    .balign 0x800
vectors_el3:
    .rept 16
    ventry el3_common
    .endr

    .balign 0x800
vectors_el1:
    .rept 16
    ventry el1_common
    .endr

el3_common:
    save_regs
    bl      el3_exc
    restore_regs
    eret

el1_common:
    save_regs
    bl      el1_exc
    restore_regs
    eret

    .bss
    .balign 16
    .space  0x2000
stack_el3_top:
    .space  0x2000
stack_el1_top:
