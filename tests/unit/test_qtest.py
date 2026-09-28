"""Generated qtest: skip policy, RW mask, meson snippet, CLI flags."""

from __future__ import annotations

from peakrdl_qemu.builder import build_device
from peakrdl_qemu.errors import PeakRDLQEMUError
from peakrdl_qemu.exporter import export_device
from tests.conftest import RDL_DIR, compile_rdl_file


def test_qtest_not_emitted_without_flags(simple_timer_top, tmp_path):
    export_device(simple_timer_top, tmp_path)
    assert not (tmp_path / "simple_timer-test.c").exists()
    assert not (tmp_path / "qtest.meson.build.snippet").exists()


def test_qtest_requires_both_flags(simple_timer_top):
    try:
        build_device(simple_timer_top, qtest_base=0x102000)
        assert False, "expected PeakRDLQEMUError"
    except PeakRDLQEMUError as exc:
        assert "together" in str(exc)


def test_simple_timer_qtest_skip_and_checks(simple_timer_top, tmp_path):
    model = export_device(
        simple_timer_top,
        tmp_path,
        qtest_base=0x102000,
        qtest_machine="virt",
        source_rdl="simple_timer.rdl",
    )
    by_name = {r.name: r for r in model.regs}
    assert by_name["CTRL"].qtest_check_reset
    assert by_name["CTRL"].qtest_check_rw
    assert by_name["CTRL"].rw_mask == 0x0000FF03
    assert by_name["LOAD"].qtest_check_rw
    assert by_name["LOAD"].rw_mask == 0xFFFFFFFF
    assert not by_name["COUNT"].qtest_check_reset  # hw-writable
    assert not by_name["COUNT"].qtest_check_rw
    assert by_name["STATUS"].qtest_check_w1c
    assert by_name["STATUS"].qtest_check_rclr
    assert not by_name["STATUS"].qtest_check_reset
    assert by_name["ID"].qtest_check_reset
    assert not by_name["ID"].qtest_check_rw

    src = (tmp_path / "simple_timer-test.c").read_text(encoding="utf-8")
    assert "SIMPLE_TIMER_BASE 0x102000" in src
    assert "-machine virt" in src
    assert "test_ctrl_reset" in src
    assert "test_ctrl_rw" in src
    assert "test_load_reset" in src
    assert "test_id_reset" in src
    assert "test_status_w1c" in src
    assert "test_status_rclr" in src
    assert "test_count_reset" not in src
    assert "hardware-writable fields are owned by behavior" in src
    meson = (tmp_path / "qtest.meson.build.snippet").read_text(encoding="utf-8")
    assert "simple-timer-test" in meson or "simple_timer-test" in meson
    assert "CONFIG_SIMPLE_TIMER" in meson


def test_shared_pair_qtest_skipped(tmp_path):
    top = compile_rdl_file(RDL_DIR / "shared_pair.rdl")
    model = export_device(
        top, tmp_path, qtest_base=0x1000, qtest_machine="virt"
    )
    r = model.regs[0]
    assert r.qtest_skip_reason
    src = (tmp_path / "shared_pair-test.c").read_text(encoding="utf-8")
    assert "TXR skipped:" in src
    assert "test_txr_reset" not in src


def test_w1c_only_qtest(tmp_path):
    top = compile_rdl_file(RDL_DIR / "w1c_only.rdl")
    model = export_device(
        top, tmp_path, qtest_base=0x2000, qtest_machine="virt"
    )
    r = model.regs[0]
    assert r.qtest_check_w1c
    assert r.qtest_check_rw
    src = (tmp_path / "w1c_only-test.c").read_text(encoding="utf-8")
    assert "test_st_w1c" in src
    assert "test_st_rw" in src


def test_rclr_only_qtest(tmp_path):
    top = compile_rdl_file(RDL_DIR / "rclr_only.rdl")
    model = export_device(
        top, tmp_path, qtest_base=0x3000, qtest_machine="virt"
    )
    r = model.regs[0]
    assert r.qtest_check_rclr
    assert r.cor == 0x2
    src = (tmp_path / "rclr_only-test.c").read_text(encoding="utf-8")
    assert "test_st_rclr" in src


def test_rw_rsvd_mask(tmp_path):
    top = compile_rdl_file(RDL_DIR / "rw_rsvd.rdl")
    model = export_device(
        top, tmp_path, qtest_base=0x4000, qtest_machine="virt"
    )
    r = model.regs[0]
    assert r.rw_mask == 0xF
    src = (tmp_path / "rw_rsvd-test.c").read_text(encoding="utf-8")
    assert "uint32_t mask = 0x0000000f;" in src or "mask = 0x0000000f" in src
