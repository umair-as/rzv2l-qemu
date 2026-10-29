# M2 hello probe (M2-T08). Override CROSS for another toolchain.
CROSS  ?= aarch64-linux-gnu-
CFLAGS := -O1 -ffreestanding -fno-pic -fno-pie -mgeneral-regs-only -mstrict-align \
          -fno-stack-protector -nostdlib -Wall -Wextra -Werror
OUT    := out

all: $(OUT)/probe.Image

$(OUT)/probe.elf: start.S hello.c probe.ld | $(OUT)
	$(CROSS)gcc $(CFLAGS) -no-pie -T probe.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -o $@ start.S hello.c

$(OUT)/probe.Image: $(OUT)/probe.elf
	$(CROSS)objcopy -O binary $< $@

$(OUT):
	mkdir -p $@

clean:
	rm -rf $(OUT)
.PHONY: all clean
