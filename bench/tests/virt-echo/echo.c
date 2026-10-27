/*
 * Bench self-test program for QEMU virt (PL011 at 0x09000000).
 * Prints a banner, echoes every key, and on:
 *   'u'  reads an unmapped address (0x0c000000) once: an invalid_mem log line
 *   'q'  exits QEMU with status 0 through semihosting
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <stdint.h>

#define UART        0x09000000UL
#define UART_DR     (*(volatile uint32_t *)(UART + 0x00))
#define UART_FR     (*(volatile uint32_t *)(UART + 0x18))
#define FR_RXFE     (1u << 4)
#define FR_TXFF     (1u << 5)
#define HOLE        0x0c000000UL

uint64_t semihost(uint64_t op, uint64_t param);
uint32_t read32(uint64_t addr);

static void putc_(char c)
{
    while (UART_FR & FR_TXFF) {
    }
    UART_DR = (uint32_t)c;
}

static void puts_(const char *s)
{
    while (*s) {
        putc_(*s++);
    }
}

static char getc_(void)
{
    while (UART_FR & FR_RXFE) {
    }
    return (char)(UART_DR & 0xff);
}

void main(void);
void main(void)
{
    static uint64_t exit_block[2] = { 0x20026, 0 };  /* ADP_Stopped_ApplicationExit */

    puts_("bench self-test: echo ready\r\n");
    for (;;) {
        char c = getc_();

        if (c == 'q') {
            puts_("\r\nbye\r\n");
            semihost(0x18, (uint64_t)exit_block);          /* SYS_EXIT */
        } else if (c == 'u') {
            (void)read32(HOLE);
            puts_("\r\nread hole\r\n");
        } else {
            putc_(c == '\r' ? '\n' : c);
        }
    }
}
