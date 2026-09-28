#!/usr/bin/env bash
# Boot RISC-V virt with the simple-timer test device and check reset values.
#
# Mapping (see qemu-patches/phase1-virt-simple-timer.patch):
#   MMIO base  0x102000  (gap after goldfish RTC at 0x101000)
#   IRQ        12
#
# Guest physical reads use the qtest protocol (`readl`) rather than HMP `xp`.
# `xp` walks the CPU address space and is a weaker check of MemoryRegionOps.
# `info mtree` is still taken from HMP over a unix monitor socket.
set -euo pipefail

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

python3 - "${QEMU_BIN}" <<'PY'
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

qemu = sys.argv[1]
BASE = 0x102000
EXPECTED = {
    "CTRL": (BASE + 0x00, 0x00001000),
    "LOAD": (BASE + 0x04, 0xFFFFFFFF),
    "ID":   (BASE + 0x10, 0x54494D52),
}

tmpdir = tempfile.mkdtemp(prefix="peakrdl-qemu-smoke-")
mon = os.path.join(tmpdir, "monitor.sock")

cmd = [
    qemu,
    "-M", "virt",
    "-nographic",
    "-display", "none",
    "-serial", "none",
    "-S",
    "-accel", "qtest",
    "-qtest", "stdio",
    "-chardev", f"socket,id=mon,path={mon},server=on,wait=off",
    "-mon", "chardev=mon,mode=readline",
]
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

def qtest(line: str) -> str:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(line + "\n")
    proc.stdin.flush()
    return proc.stdout.readline().rstrip("\n")

def readl(addr: int) -> int:
    resp = qtest(f"readl {addr:#x}")
    m = re.search(r"0x[0-9a-fA-F]+", resp)
    if not m:
        raise SystemExit(f"unexpected qtest response to readl {addr:#x}: {resp!r}")
    return int(m.group(0), 16)

def hmp(command: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while not os.path.exists(mon):
        if time.time() > deadline:
            raise SystemExit("monitor socket did not appear")
        time.sleep(0.05)
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise SystemExit(f"qemu exited before monitor was ready: {err}")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    while True:
        try:
            sock.connect(mon)
            break
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            if time.time() > deadline:
                raise SystemExit("could not connect to monitor socket")
            time.sleep(0.05)
    sock.settimeout(timeout)
    # Drain the banner / prompt
    buf = b""
    while b"(qemu)" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    sock.sendall((command + "\n").encode())
    out = b""
    while b"(qemu)" not in out:
        chunk = sock.recv(4096)
        if not chunk:
            break
        out += chunk
    sock.sendall(b"quit\n")
    try:
        sock.close()
    except OSError:
        pass
    return out.decode(errors="replace")

ok = True
try:
    for name, (addr, exp) in EXPECTED.items():
        got = readl(addr)
        print(f"{name:5} @ {addr:#x} = {got:#010x}")
        if got != exp:
            print(f"FAIL: {name} reset, expected {exp:#010x} got {got:#010x}",
                  file=sys.stderr)
            ok = False
    mtree = hmp("info mtree")
    if "simple-timer" not in mtree and "0x102000" not in mtree:
        print("FAIL: info mtree does not mention simple-timer / 0x102000",
              file=sys.stderr)
        print(mtree, file=sys.stderr)
        ok = False
    else:
        print("info mtree: simple-timer region present")
        for line in mtree.splitlines():
            if "102000" in line or "simple-timer" in line or "simple_timer" in line:
                print(" ", line.strip())
    qtest("quit")
finally:
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

if not ok:
    sys.exit(1)
print("phase1 smoke: MMIO region visible and reset values OK")
PY
