/*
 * Bench self-test program for QEMU virt: entry, vectors, helpers.
 * Every exception skips the faulting instruction, so a read of a hole
 * (key 'u') aborts once and the program carries on.
 * SPDX-License-Identifier: Apache-2.0
 */
    .text
    .globl _start
_start:
    ldr     x0, =stack_top
    mov     sp, x0
    adr     x0, vectors
    msr     vbar_el1, x0
    isb
    bl      main
1:  wfi
    b       1b

    /* x0 = operation, x1 = parameter (A64 semihosting) */
    .globl semihost
semihost:
    hlt     #0xf000
    ret

    .globl read32
read32:
    ldr     w0, [x0]
    ret

    .balign 0x800
vectors:
    .rept 16
    .balign 0x80
    mrs     x17, elr_el1        /* x17 (IP1): scratch, never live across read32 */
    add     x17, x17, #4
    msr     elr_el1, x17
    eret
    .endr

    .bss
    .balign 16
    .space  4096
stack_top:
