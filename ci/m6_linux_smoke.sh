#!/usr/bin/env bash
# Optional Linux smoke for M6. Requires a RISC-V virt kernel with i2c-ocores
# and a rootfs with i2c-tools + lm75/tmp105. Not run in default CI.
#
#   OCORES_KERNEL=path/to/Image OCORES_ROOTFS=path/to/rootfs.ext4 \
#       ./ci/m6_linux_smoke.sh
set -euo pipefail

QEMU_BIN="${QEMU_BIN:-${QEMU_BUILD:-$HOME/src/qemu/build}/qemu-system-riscv64}"
KERNEL="${OCORES_KERNEL:-}"
ROOTFS="${OCORES_ROOTFS:-}"

if [[ -z "$KERNEL" || -z "$ROOTFS" ]]; then
    echo "skip: set OCORES_KERNEL and OCORES_ROOTFS to run the Linux smoke test"
    echo "The protocol is covered by ci/m6_smoke.sh (qtest) without a kernel."
    exit 0
fi

if [[ ! -x "$QEMU_BIN" ]]; then
    echo "error: qemu binary not found: $QEMU_BIN" >&2
    exit 1
fi

echo "Booting $KERNEL with $ROOTFS"
# The guest must have i2c-ocores, i2c-dev, and lm75/tmp105. Expected:
#   dmesg | grep ocores
#   i2cdetect -y 0   -> 48
#   cat /sys/class/hwmon/hwmon0/temp1_input
exec "$QEMU_BIN" -M virt -nographic -kernel "$KERNEL" \
    -drive file="$ROOTFS",format=raw,if=virtio \
    -append "root=/dev/vda rw console=ttyS0"
