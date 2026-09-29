# RISC-V guest: a hart that actually uses the IP

Bare-metal firmware for QEMU `virt`. The **RISC-V CPU** issues 32-bit
loads and stores to the peakrdl-qemu devices — not host qtest.

| Device | Guest physical | What the hart does |
|---|---|---|
| UART NS16550 | `0x10000000` | prints results |
| SiFive test | `0x100000` | `0x5555` pass / `0x3333` fail (exits QEMU) |
| simple-timer | `0x102000` | checks CTRL / LOAD / ID reset |
| OpenCores I2C | `0x103000` | enable, detect `tmp105@0x48`, NACK `0x22`, read 0 °C |

## Build and run

Needs `riscv64-unknown-elf-gcc` and a QEMU tree with both devices
applied (`qemu-patches/m6-virt-ocores-i2c.patch`).

```shell
make -C examples/riscv-guest
qemu-system-riscv64 -M virt -nographic -bios none \
    -kernel examples/riscv-guest/firmware.elf
```

Or:

```shell
QEMU_SRC=$HOME/src/qemu ./ci/riscv_guest_smoke.sh
```

Expected UART:

```text
peakrdl-qemu RISC-V guest: I2C over MMIO
ok: simple-timer MMIO reset values
ok: OpenCores I2C enable via MMIO
ok: detected tmp105 @ 0x48 over I2C MMIO
ok: absent 0x22 NACKed
tmp105 temp bytes: 00 00
ok: tmp105 read 0 C via RISC-V MMIO
RESULT: PASS
```

The I2C sequence is the same CR/SR protocol as Linux `i2c-ocores` and
`examples/ocores_i2c/ocores_i2c-test.c`, except every access is a RISC-V
`lw`/`sw` to `0x103000`.
