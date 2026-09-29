# OpenCores I2C master (M6)

SystemRDL plus reference behavior for the Wishbone I2C-Master Core,
wired so Linux `i2c-ocores` can talk to a `tmp105` at `0x48`.

## Generate

```shell
peakrdl qemu examples/ocores_i2c/ocores_i2c.rdl -o out/ \
    --qemu-subdir i2c \
    --kconfig-select I2C --kconfig-select I2C_DEVICES \
    --apply-to $QEMU_SRC
```

Then copy the **owned** behavior files over the stubs (the exporter never
overwrites them if they already exist):

```shell
cp examples/ocores_i2c/ocores_i2c_behavior.c \
   examples/ocores_i2c/ocores_i2c_behavior.h \
   $QEMU_SRC/hw/i2c/
```

Apply [qemu-patches/m6-virt-ocores-i2c.patch](/home/ubuntu/peakrdl-qemu/qemu-patches/m6-virt-ocores-i2c.patch)
for the RISC-V virt board hookup (0x103000, IRQ 13, DT node, tmp105 child).

## Protocol (Linux `i2c-ocores`)

Registers are 32-bit spaced (`reg-shift = 2`):

| Offset | Write | Read |
|---|---|---|
| 0x00 | PRERLO | PRERLO |
| 0x04 | PRERHI | PRERHI |
| 0x08 | CTR (`EN`, `IEN`) | CTR |
| 0x0C | TXR | RXR |
| 0x10 | CR (`STA/STO/RD/WR/ACK/IACK`) | SR (`IF/TIP/AL/BUSY/RXACK`) |

CR command bits are `singlepulse`. Behavior runs `i2c_start_transfer` /
`i2c_send` / `i2c_recv` / `i2c_nack` / `i2c_end_transfer`, sets `SR.IF`,
and raises the IRQ when `CTR.IEN` is set. Transfers complete immediately
(QEMU I2C is synchronous), so `TIP` is always left clear.

## Tests


Host qtest (no guest CPU):

```shell
QEMU_SRC=/path/to/qemu ninja -C $QEMU_SRC/build tests/qtest/ocores_i2c-test
QTEST_QEMU_BINARY=$QEMU_SRC/build/qemu-system-riscv64 \
    $QEMU_SRC/build/tests/qtest/ocores_i2c-test --tap -k
```

RISC-V hart using the IP over MMIO:

```shell
QEMU_SRC=/path/to/qemu ./ci/riscv_guest_smoke.sh
```

See [examples/riscv-guest](../riscv-guest/).
