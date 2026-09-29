#!/usr/bin/env bash
# Boot RISC-V virt with the bare-metal guest. The hart itself MMIO-accesses
# simple-timer and OpenCores I2C (tmp105@0x48). Exit code comes from the
# SiFive test device (0x5555 pass / 0x3333 fail).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUEST="${ROOT}/examples/riscv-guest"
QEMU_BIN="${QEMU_BIN:-}"

if [[ -z "${QEMU_BIN}" ]]; then
    if [[ -n "${QEMU_SRC:-}" && -x "${QEMU_SRC}/build/qemu-system-riscv64" ]]; then
        QEMU_BIN="${QEMU_SRC}/build/qemu-system-riscv64"
    elif [[ -x "${HOME}/src/qemu/build/qemu-system-riscv64" ]]; then
        QEMU_BIN="${HOME}/src/qemu/build/qemu-system-riscv64"
    elif command -v qemu-system-riscv64 >/dev/null 2>&1; then
        QEMU_BIN="$(command -v qemu-system-riscv64)"
    else
        echo "error: qemu-system-riscv64 not found (set QEMU_BIN or QEMU_SRC)" >&2
        exit 1
    fi
fi

if ! command -v riscv64-unknown-elf-gcc >/dev/null 2>&1; then
    echo "error: riscv64-unknown-elf-gcc is required to build the guest" >&2
    exit 1
fi

make -C "${GUEST}"

echo "Running ${QEMU_BIN} -kernel ${GUEST}/firmware.elf"
# -bios none: jump straight to the ELF. The firmware exits QEMU via sifive_test.
set +e
out="$("${QEMU_BIN}" -M virt -nographic -monitor none \
    -bios none -kernel "${GUEST}/firmware.elf" \
    -serial stdio 2>&1)"
rc=$?
set -e
printf '%s\n' "${out}"

if [[ ${rc} -ne 0 ]]; then
    echo "error: QEMU exited ${rc} (guest FAIL / crash)" >&2
    exit 1
fi
if ! printf '%s\n' "${out}" | grep -q 'RESULT: PASS'; then
    echo "error: guest did not print RESULT: PASS" >&2
    exit 1
fi
if printf '%s\n' "${out}" | grep -q '^FAIL:'; then
    echo "error: guest reported FAIL lines" >&2
    exit 1
fi
echo "riscv guest smoke: PASS"
