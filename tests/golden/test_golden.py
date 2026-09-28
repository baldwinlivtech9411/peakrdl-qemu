"""Golden-file tests for generated output."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from peakrdl_qemu.exporter import export_device
from tests.conftest import EXAMPLES, compile_rdl_file

GOLDEN = Path(__file__).resolve().parent


def _check_golden(
    tmp_path: Path,
    rdl: Path,
    source_rdl: str,
    golden_dir: Path,
    qemu_subdir: str = "misc",
    kconfig_selects: Optional[Iterable[str]] = None,
) -> None:
    top = compile_rdl_file(rdl)
    out = tmp_path / "out"
    export_device(
        top,
        out,
        source_rdl=source_rdl,
        qemu_subdir=qemu_subdir,
        kconfig_selects=kconfig_selects,
    )
    assert golden_dir.is_dir(), f"golden directory missing: {golden_dir}"
    for expected in sorted(golden_dir.iterdir()):
        if expected.name.endswith("-test.c") or expected.name.startswith("qtest."):
            continue
        if expected.suffix == ".rdl" or expected.name == "README.md":
            continue
        if expected.name.endswith("_behavior.c") or expected.name.endswith("_behavior.h"):
            # Owned files may differ from the empty stub goldens.
            continue
        got = out / expected.name
        assert got.is_file(), f"missing generated file {expected.name}"
        assert got.read_text(encoding="utf-8") == expected.read_text(
            encoding="utf-8"
        ), f"golden mismatch for {expected.name}"


def test_simple_timer_golden(tmp_path):
    _check_golden(
        tmp_path,
        EXAMPLES / "simple_timer" / "simple_timer.rdl",
        "examples/simple_timer/simple_timer.rdl",
        GOLDEN / "simple_timer",
    )


def test_m3_features_golden(tmp_path):
    _check_golden(
        tmp_path,
        EXAMPLES / "m3_features" / "m3_features.rdl",
        "examples/m3_features/m3_features.rdl",
        GOLDEN / "m3_features",
    )


def test_m5_arrays_golden(tmp_path):
    _check_golden(
        tmp_path,
        EXAMPLES / "m5_arrays" / "m5_arrays.rdl",
        "examples/m5_arrays/m5_arrays.rdl",
        GOLDEN / "m5_arrays",
    )


def test_ocores_i2c_golden(tmp_path):
    _check_golden(
        tmp_path,
        EXAMPLES / "ocores_i2c" / "ocores_i2c.rdl",
        "examples/ocores_i2c/ocores_i2c.rdl",
        GOLDEN / "ocores_i2c",
        qemu_subdir="i2c",
        kconfig_selects=["I2C", "I2C_DEVICES"],
    )
