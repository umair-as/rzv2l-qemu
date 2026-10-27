/* QEMU virt RAM starts at 0x40000000; the ELF loader enters at _start. */
ENTRY(_start)
SECTIONS
{
    . = 0x40080000;
    .text : { *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
}
