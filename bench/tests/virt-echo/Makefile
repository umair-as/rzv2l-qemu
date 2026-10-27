# Bench self-test program for QEMU virt. Override CROSS for another toolchain.
CROSS  ?= aarch64-linux-gnu-
CFLAGS := -O1 -ffreestanding -fno-pic -fno-pie -mgeneral-regs-only -mstrict-align \
          -fno-stack-protector -nostdlib -Wall -Wextra -Werror
OUT    := out

all: $(OUT)/echo.elf

$(OUT)/echo.elf: start.S echo.c echo.ld | $(OUT)
	$(CROSS)gcc $(CFLAGS) -no-pie -T echo.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -o $@ start.S echo.c

$(OUT):
	mkdir -p $@

clean:
	rm -rf $(OUT)
.PHONY: all clean
