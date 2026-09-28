FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python3-setuptools \
        git ninja-build meson pkg-config \
        gcc flex bison \
        libglib2.0-dev libpixman-1-dev libfdt-dev \
        perl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src/peakrdl-qemu
RUN pip3 install --no-cache-dir --break-system-packages \
        "/src/peakrdl-qemu[dev]"

ENV QEMU_SRC=/src/qemu
CMD ["/bin/bash", "-lc", "cd /src/peakrdl-qemu && pytest && ./ci/build_qemu.sh"]
