CROSS   ?= riscv64-unknown-elf-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy

CFLAGS  := -march=rv64gc -mabi=lp64d -mcmodel=medany \
           -ffreestanding -fno-builtin -fno-pic -nostdlib -nostartfiles \
           -O2 -Wall -Wextra
LDFLAGS := -T link.ld -nostdlib -nostartfiles -static -Wl,--no-dynamic-linker

all: firmware.elf firmware.bin

firmware.elf: start.S main.c link.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ start.S main.c

firmware.bin: firmware.elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -f firmware.elf firmware.bin

.PHONY: all clean
