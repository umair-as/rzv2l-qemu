# EXP-001 probe build. Override CROSS for another toolchain.
CROSS  ?= aarch64-linux-gnu-
CFLAGS := -O1 -ffreestanding -fno-pic -fno-pie -mgeneral-regs-only -mstrict-align \
          -fno-stack-protector -nostdlib -Wall
OUT    := out

all: $(OUT)/probe.elf $(OUT)/probe.Image

$(OUT)/probe.elf: start.S probe.c probe.ld | $(OUT)
	$(CROSS)gcc $(CFLAGS) -no-pie -T probe.ld -Wl,--build-id=none -o $@ start.S probe.c

$(OUT)/probe.Image: $(OUT)/probe.elf
	$(CROSS)objcopy -O binary $< $@

$(OUT):
	mkdir -p $@

clean:
	rm -rf $(OUT)
.PHONY: all clean
