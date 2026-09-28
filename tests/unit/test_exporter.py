"""Exporter overwrite policy, determinism, and --apply-to idempotency."""

from __future__ import annotations

from pathlib import Path

from peakrdl_qemu.exporter import export_device, export_model
from peakrdl_qemu.builder import build_device
from tests.conftest import RDL_DIR, compile_rdl_file


def _files(outdir: Path):
    return sorted(p.name for p in outdir.iterdir() if p.is_file())


def test_export_is_deterministic(simple_timer_top, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    export_device(simple_timer_top, a, source_rdl="simple_timer.rdl")
    export_device(simple_timer_top, b, source_rdl="simple_timer.rdl")
    names = _files(a)
    assert names == _files(b)
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_behavior_stubs_not_overwritten(simple_timer_top, tmp_path):
    out = tmp_path / "out"
    export_device(simple_timer_top, out, source_rdl="simple_timer.rdl")
    bh = out / "simple_timer_behavior.c"
    original = bh.read_text(encoding="utf-8")
    marker = "/* HAND WRITTEN */\n"
    bh.write_text(marker + original, encoding="utf-8")
    hh = out / "simple_timer_behavior.h"
    hh.write_text(hh.read_text(encoding="utf-8") + "/* keep */\n", encoding="utf-8")

    export_device(simple_timer_top, out, source_rdl="simple_timer.rdl")
    assert bh.read_text(encoding="utf-8").startswith(marker)
    assert "keep" in hh.read_text(encoding="utf-8")
    # generated files still refresh
    assert "DO NOT EDIT" in (out / "simple_timer_gen.c").read_text(encoding="utf-8")


def test_generated_file_set(simple_timer_top, tmp_path):
    out = tmp_path / "out"
    export_device(simple_timer_top, out)
    names = set(_files(out))
    assert names == {
        "simple_timer_regs.h",
        "simple_timer.h",
        "simple_timer_gen.c",
        "simple_timer_behavior.h",
        "simple_timer_behavior.c",
        "meson.build.snippet",
        "Kconfig.snippet",
    }


def test_mmio_is_32bit_only(simple_timer_top, tmp_path):
    """register_*_memory matches exact addr; do not advertise 1-byte accesses."""
    out = tmp_path / "out"
    export_device(simple_timer_top, out)
    gen = (out / "simple_timer_gen.c").read_text(encoding="utf-8")
    assert ".min_access_size = 4," in gen
    assert ".max_access_size = 4," in gen
    assert ".min_access_size = 1," not in gen


def test_generated_write_only_masks_post_read(tmp_path):
    top = compile_rdl_file(RDL_DIR / "write_only.rdl")
    out = tmp_path / "out"
    export_device(top, out)
    gen = (out / "write_only_dev_gen.c").read_text(encoding="utf-8")
    assert "ret &= ~0x000000ff;" in gen
    assert ".post_read = gen_tx_post_read" in gen


def test_generated_shared_pair(tmp_path):
    top = compile_rdl_file(RDL_DIR / "shared_pair.rdl")
    out = tmp_path / "out"
    export_device(top, out)
    gen = (out / "shared_pair_gen.c").read_text(encoding="utf-8")
    hdr = (out / "shared_pair.h").read_text(encoding="utf-8")
    regs = (out / "shared_pair_regs.h").read_text(encoding="utf-8")
    assert ".name = \"TXR_RXR\"" in gen
    assert "s->shadow_rxr" in gen
    assert "VMSTATE_UINT32(shadow_rxr, SharedPairState)" in gen
    assert "uint32_t shadow_rxr;" in hdr
    assert "REG32(TXR, 0xc)" in regs
    assert "FIELD(RXR, DATA, 0, 8)" in regs
    assert "REG32(RXR" not in regs


def test_generated_singlepulse_clears_after_hook(tmp_path):
    top = compile_rdl_file(RDL_DIR / "singlepulse.rdl")
    out = tmp_path / "out"
    export_device(top, out)
    gen = (out / "singlepulse_dev_gen.c").read_text(encoding="utf-8")
    # user hook first, then clear
    hook = gen.find("singlepulse_dev_cr_write")
    clear = gen.find("s->regs[R_CR] &= ~0x00000001;")
    assert hook != -1 and clear != -1 and hook < clear


def test_apply_to_idempotent(simple_timer_top, tmp_path):
    qemu = tmp_path / "qemu"
    misc = qemu / "hw" / "misc"
    misc.mkdir(parents=True)
    (misc / "meson.build").write_text("# existing\n", encoding="utf-8")
    (misc / "Kconfig").write_text("config FOO\n    bool\n", encoding="utf-8")

    out = tmp_path / "out"
    export_device(
        simple_timer_top,
        out,
        apply_to=qemu,
        source_rdl="simple_timer.rdl",
    )
    meson1 = (misc / "meson.build").read_text(encoding="utf-8")
    kconfig1 = (misc / "Kconfig").read_text(encoding="utf-8")
    assert "BEGIN peakrdl-qemu SIMPLE_TIMER" in meson1
    assert "CONFIG_SIMPLE_TIMER" in meson1
    assert "select REGISTER" in kconfig1
    assert (misc / "simple_timer_gen.c").is_file()

    export_device(
        simple_timer_top,
        out,
        apply_to=qemu,
        source_rdl="simple_timer.rdl",
    )
    assert (misc / "meson.build").read_text(encoding="utf-8") == meson1
    assert (misc / "Kconfig").read_text(encoding="utf-8") == kconfig1


def test_apply_to_keeps_existing_behavior(simple_timer_top, tmp_path):
    qemu = tmp_path / "qemu"
    misc = qemu / "hw" / "misc"
    misc.mkdir(parents=True)
    (misc / "meson.build").write_text("", encoding="utf-8")
    (misc / "Kconfig").write_text("", encoding="utf-8")
    (misc / "simple_timer_behavior.c").write_text("/* custom */\n", encoding="utf-8")

    out = tmp_path / "out"
    export_device(simple_timer_top, out, apply_to=qemu)
    assert (misc / "simple_timer_behavior.c").read_text(encoding="utf-8") == "/* custom */\n"


def test_apply_to_inserts_qtest_meson(simple_timer_top, tmp_path):
    qemu = tmp_path / "qemu"
    misc = qemu / "hw" / "misc"
    qtest = qemu / "tests" / "qtest"
    misc.mkdir(parents=True)
    qtest.mkdir(parents=True)
    (misc / "meson.build").write_text("", encoding="utf-8")
    (misc / "Kconfig").write_text("", encoding="utf-8")
    (qtest / "meson.build").write_text(
        "qtests_riscv64 = ['riscv-csr-test'] + \\\n"
        "  (unpack_edk2_blobs ? ['bios-tables-test'] : [])\n"
        "qos_test_ss = ss.source_set()\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    export_device(
        simple_timer_top,
        out,
        apply_to=qemu,
        qtest_base=0x102000,
        qtest_machine="virt",
    )
    text = (qtest / "meson.build").read_text(encoding="utf-8")
    assert "BEGIN peakrdl-qemu SIMPLE_TIMER" in text
    assert text.index("qtests_riscv64 =") < text.index("qtests_riscv64 +=")
    assert "qos_test_ss" in text
    # second run is idempotent
    export_device(
        simple_timer_top,
        out,
        apply_to=qemu,
        qtest_base=0x102000,
        qtest_machine="virt",
    )
    assert (qtest / "meson.build").read_text(encoding="utf-8") == text
    assert (qtest / "simple_timer-test.c").is_file()
