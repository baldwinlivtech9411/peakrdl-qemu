"""CLI surface and rejection messages without a Python traceback."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RDL_DIR = ROOT / "tests" / "rdl"
EXAMPLE = ROOT / "examples" / "simple_timer" / "simple_timer.rdl"


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "peakrdl", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def test_help_lists_phase1_options():
    r = _run("qemu", "--help")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for opt in (
        "--device-name",
        "--qemu-subdir",
        "--kconfig-select",
        "--endianness",
        "--license",
        "--apply-to",
        "-o",
    ):
        assert opt in out, opt
    for opt in ("--qtest-base", "--qtest-machine"):
        assert opt in out, opt
    assert "--emit-ai-context" not in out


def test_cli_generates_write_only(tmp_path):
    r = _run(
        "qemu",
        str(RDL_DIR / "write_only.rdl"),
        "-o",
        str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    gen = (tmp_path / "write_only_dev_gen.c").read_text(encoding="utf-8")
    assert "ret &= ~0x000000ff;" in gen


def test_cli_generates_shared_pair(tmp_path):
    r = _run(
        "qemu",
        str(RDL_DIR / "shared_pair.rdl"),
        "-o",
        str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    gen = (tmp_path / "shared_pair_gen.c").read_text(encoding="utf-8")
    assert ".name = \"TXR_RXR\"" in gen
    assert "s->shadow_rxr" in gen
    hdr = (tmp_path / "shared_pair.h").read_text(encoding="utf-8")
    assert "uint32_t shadow_rxr;" in hdr


def test_cli_generates_array(tmp_path):
    r = _run(
        "qemu",
        str(RDL_DIR / "reg_array.rdl"),
        "-o",
        str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    regs = (tmp_path / "array_dev_regs.h").read_text(encoding="utf-8")
    assert "REG32(DATA_0" in regs
    assert "REG32(DATA_3" in regs
    gen = (tmp_path / "array_dev_gen.c").read_text(encoding="utf-8")
    assert ".name = \"DATA_0\"" in gen
    assert ".name = \"DATA_3\"" in gen


def test_cli_emits_qtest(tmp_path):
    r = _run(
        "qemu",
        str(EXAMPLE),
        "-o",
        str(tmp_path),
        "--qtest-base",
        "0x102000",
        "--qtest-machine",
        "virt",
    )
    assert r.returncode == 0, r.stderr
    src = (tmp_path / "simple_timer-test.c").read_text(encoding="utf-8")
    assert "SIMPLE_TIMER_BASE 0x102000" in src
    assert "-machine virt" in src
