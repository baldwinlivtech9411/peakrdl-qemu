#!/usr/bin/env bash
# Clone (if needed) and build the pinned QEMU tag with a fast riscv64 configuration.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="$(tr -d '[:space:]' < "${ROOT}/QEMU_VERSION")"
QEMU_SRC="${QEMU_SRC:-${HOME}/src/qemu}"
JOBS="${JOBS:-$(nproc)}"

if [[ ! -d "${QEMU_SRC}/.git" ]]; then
    mkdir -p "$(dirname "${QEMU_SRC}")"
    git clone --depth 1 --branch "${TAG}" https://gitlab.com/qemu-project/qemu.git "${QEMU_SRC}"
else
    git -C "${QEMU_SRC}" fetch --depth 1 origin "refs/tags/${TAG}:refs/tags/${TAG}" || true
    git -C "${QEMU_SRC}" checkout --detach "${TAG}"
fi

cd "${QEMU_SRC}"
if [[ ! -f build/build.ninja ]]; then
    ./configure \
        --target-list=riscv64-softmmu \
        --enable-werror \
        --disable-docs \
        --disable-guest-agent \
        --disable-sdl \
        --disable-gtk \
        --disable-vnc \
        --disable-tools \
        --audio-drv-list=
fi

ninja -C build -j"${JOBS}"
echo "QEMU built at ${QEMU_SRC}/build/qemu-system-riscv64"
