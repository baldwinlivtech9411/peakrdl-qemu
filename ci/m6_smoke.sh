#!/usr/bin/env bash
# Drive the OpenCores I2C master on RISC-V virt with the generated qtest.
# This is the in-tree M6 gate: Linux i2c-ocores uses the same CR/SR protocol.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QEMU_SRC="${QEMU_SRC:-$HOME/src/qemu}"
QEMU_BUILD="${QEMU_BUILD:-$QEMU_SRC/build}"
QEMU_BIN="${QEMU_BIN:-$QEMU_BUILD/qemu-system-riscv64}"
QTEST_BIN="${QTEST_BIN:-$QEMU_BUILD/tests/qtest/ocores_i2c-test}"

if [[ ! -x "$QEMU_BIN" ]]; then
    echo "error: qemu binary not found: $QEMU_BIN" >&2
    exit 1
fi
if [[ ! -x "$QTEST_BIN" ]]; then
    echo "error: ocores qtest not found: $QTEST_BIN" >&2
    echo "hint: ninja -C $QEMU_BUILD tests/qtest/ocores_i2c-test" >&2
    exit 1
fi

echo "Running $QTEST_BIN against $QEMU_BIN"
cd "$(dirname "$QEMU_BIN")"
QTEST_QEMU_BINARY="$QEMU_BIN" "$QTEST_BIN" --tap -k
