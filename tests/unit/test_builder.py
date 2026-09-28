"""Model-builder unit tests: masks, naming, and feature gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from peakrdl_qemu.builder import build_device
from peakrdl_qemu.errors import PeakRDLQEMUError
from tests.conftest import RDL_DIR, compile_rdl_file, compile_rdl_text

EXPECTED_SIMPLE_TIMER = {
    "CTRL": {
        "reset": 0x00001000,
        "ro": 0xFFFF00FC,
        "w1c": 0,
        "cor": 0,
        "rsvd": 0xFFFF00FC,
    },
    "LOAD": {
        "reset": 0xFFFFFFFF,
        "ro": 0,
        "w1c": 0,
        "cor": 0,
        "rsvd": 0,
    },
    "COUNT": {
        "reset": 0,
        "ro": 0xFFFFFFFF,
        "w1c": 0,
        "cor": 0,
        "rsvd": 0,
    },
    "STATUS": {
        "reset": 0,
        "ro": 0xFFFFFFFE,
        "w1c": 0x1,
        "cor": 0x2,
        "rsvd": 0xFFFFFFFC,
    },
    "ID": {
        "reset": 0x54494D52,
        "ro": 0xFFFFFFFF,
        "w1c": 0,
        "cor": 0,
        "rsvd": 0,
    },
}


def test_simple_timer_masks(simple_timer_top):
    model = build_device(simple_timer_top, source_rdl="simple_timer.rdl")
    assert model.name == "simple_timer"
    assert model.name_upper == "SIMPLE_TIMER"
    assert model.qom_name == "simple-timer"
    assert model.irqs == 1
    assert model.r_max == 5
    assert model.mmio_size == 0x14

    by_name = {r.name: r for r in model.regs}
    assert set(by_name) == set(EXPECTED_SIMPLE_TIMER)
    for name, expected in EXPECTED_SIMPLE_TIMER.items():
        r = by_name[name]
        for key, value in expected.items():
            got = getattr(r, key)
            assert got == value, f"{name}.{key}: got {got:#010x} expected {value:#010x}"


def test_simple_timer_hooks(simple_timer_top):
    model = build_device(simple_timer_top)
    kinds = {(h.kind, h.name) for h in model.hooks}
    assert ("init", "simple_timer_behavior_init") in kinds
    assert ("reset", "simple_timer_behavior_reset") in kinds
    # writable registers get write hooks; COUNT/ID are RO so they do not
    assert ("write", "simple_timer_ctrl_write") in kinds
    assert ("write", "simple_timer_load_write") in kinds
    assert ("write", "simple_timer_status_write") in kinds
    assert not any(h.kind == "write" and "count" in h.name for h in model.hooks)
    assert not any(h.kind == "write" and h.name.endswith("_id_write") for h in model.hooks)
    assert not any(h.kind == "read" for h in model.hooks)


def test_qemu_read_hook_udp():
    top = compile_rdl_text(
        """
        addrmap with_read_hook {
            default regwidth = 32;
            reg {
                qemu_read_hook;
                field { sw = r; hw = w; } VALUE[31:0];
            } COUNT @ 0x00;
        };
        """,
        name="read_hook.rdl",
    )
    model = build_device(top)
    assert model.regs[0].has_read_hook
    assert any(h.kind == "read" for h in model.hooks)


def test_qemu_no_write_hook_udp():
    top = compile_rdl_text(
        """
        addrmap no_write {
            default regwidth = 32;
            reg {
                qemu_no_write_hook;
                field { sw = rw; } EN[0:0];
            } CTRL @ 0x00;
        };
        """,
        name="no_write.rdl",
    )
    model = build_device(top)
    assert not model.regs[0].has_write_hook
    assert not any(h.kind == "write" for h in model.hooks)


def test_irq_default_from_intr():
    top = compile_rdl_text(
        """
        addrmap irq_dev {
            default regwidth = 32;
            reg {
                field { sw = r; hw = w; } FLAG[0:0];
            } ST @ 0x00;
        };
        """,
        name="no_intr.rdl",
    )
    model = build_device(top)
    assert model.irqs == 0

    top = compile_rdl_text(
        """
        addrmap irq_dev {
            default regwidth = 32;
            reg {
                field { sw = rw; onwrite = woclr; } FLAG[0:0];
            } ST @ 0x00;
        };
        """,
        name="still_no_intr.rdl",
    )
    assert build_device(top).irqs == 0


def test_reserved_bits_go_into_ro_and_rsvd():
    top = compile_rdl_text(
        """
        addrmap rsvd_dev {
            default regwidth = 32;
            reg {
                field { sw = rw; } LOW[3:0] = 0;
            } R @ 0x00;
        };
        """,
        name="rsvd.rdl",
    )
    r = build_device(top).regs[0]
    assert r.rsvd == 0xFFFFFFF0
    assert r.ro == 0xFFFFFFF0


def test_device_name_override(simple_timer_top):
    model = build_device(simple_timer_top, device_name="my_timer")
    assert model.name == "my_timer"
    assert model.qom_name == "my-timer"
    assert model.name_camel == "MyTimer"


def test_write_only_field_masks():
    top = compile_rdl_file(RDL_DIR / "write_only.rdl")
    r = build_device(top).regs[0]
    assert r.writeonly_mask == 0xFF
    assert r.ro == 0xFFFFFF00
    assert r.needs_post_read
    assert r.has_write_hook


def test_woset_sets_pre_write():
    top = compile_rdl_file(RDL_DIR / "woset.rdl")
    r = build_device(top).regs[0]
    assert r.woset == 0x1
    assert r.needs_pre_write
    assert r.w1c == 0


def test_rset_sets_post_read():
    top = compile_rdl_file(RDL_DIR / "rset.rdl")
    r = build_device(top).regs[0]
    assert r.rset == 0x1
    assert r.cor == 0
    assert r.needs_post_read


def test_singlepulse_sets_post_write():
    top = compile_rdl_file(RDL_DIR / "singlepulse.rdl")
    r = build_device(top).regs[0]
    assert r.pulse == 0x1
    assert r.needs_post_write
    assert r.has_write_hook


def test_shared_pair_merges_to_write_side():
    top = compile_rdl_file(RDL_DIR / "shared_pair.rdl")
    model = build_device(top)
    assert len(model.regs) == 1
    r = model.regs[0]
    assert r.is_shared_pair
    assert r.name == "TXR"
    assert r.pair_read_name == "RXR"
    assert r.access_name == "TXR_RXR"
    assert r.shadow_name == "shadow_rxr"
    assert r.offset == 0x0C
    # write-side unused bits are RO so writes store DATA[7:0]
    assert r.ro == 0xFFFFFF00
    assert r.rsvd == 0xFFFFFF00
    assert r.needs_post_read
    assert r.has_write_hook
    assert not r.has_read_hook
    assert len(model.shared_pairs) == 1
    assert model.shared_pairs[0].write_reg == "TXR"
    assert model.shared_pairs[0].read_reg == "RXR"


def test_onwrite_rest_masks():
    top = compile_rdl_file(RDL_DIR / "onwrite_rest.rdl")
    r = build_device(top).regs[0]
    assert r.wot == 0x1
    assert r.wzc == 0x2
    assert r.wzs == 0x4
    assert r.wclr == 0x8
    assert r.wset == 0x10
    assert r.wzt == 0x20
    assert r.needs_pre_write


def test_m3_features_example():
    from tests.conftest import EXAMPLES

    top = compile_rdl_file(EXAMPLES / "m3_features" / "m3_features.rdl")
    model = build_device(top)
    by_name = {r.name: r for r in model.regs}
    assert set(by_name) == {"MIXED", "WOSET", "RSET", "TXR", "CR"}
    assert by_name["MIXED"].writeonly_mask == 0xFF00
    assert by_name["WOSET"].woset == 0x1
    assert by_name["RSET"].rset == 0x1
    assert by_name["TXR"].is_shared_pair
    assert by_name["TXR"].pair_read_name == "RXR"
    assert by_name["CR"].pulse == 0x1


@pytest.mark.parametrize(
    "filename,needle",
    [
        ("regwidth64.rdl", "regwidth = 64 is not supported"),
        ("mem.rdl", "mem components are not supported"),
        ("overlap.rdl", "overlapping registers"),
        ("counter.rdl", "counters are not supported"),
        ("wuser.rdl", "onwrite = wuser is not supported"),
        ("ruser.rdl", "onread = ruser is not supported"),
        ("overlap_fields.rdl", "overlapping fields"),
    ],
)
def test_rejected_features(filename, needle):
    path = RDL_DIR / filename
    try:
        top = compile_rdl_file(path)
    except pytest.fail.Exception:
        pytest.skip(f"systemrdl-compiler rejected {filename} before the exporter")
    with pytest.raises(PeakRDLQEMUError) as ei:
        build_device(top, source_rdl=str(path))
    msg = str(ei.value)
    assert needle in msg
    # file:line should be present for RDL-sourced errors
    assert ":" in (ei.value.loc.format() or msg)


def test_error_has_no_python_traceback_text():
    top = compile_rdl_file(RDL_DIR / "counter.rdl")
    with pytest.raises(PeakRDLQEMUError) as ei:
        build_device(top)
    assert "Traceback" not in str(ei.value)
    assert "File " not in str(ei.value)


def test_register_array_expands():
    top = compile_rdl_file(RDL_DIR / "reg_array.rdl")
    model = build_device(top)
    names = [r.name for r in model.regs]
    assert names == ["DATA_0", "DATA_1", "DATA_2", "DATA_3"]
    assert [r.offset for r in model.regs] == [0x00, 0x04, 0x08, 0x0C]
    assert model.r_max == 4
    assert model.mmio_size == 0x10
    write_hooks = [h.name for h in model.hooks if h.kind == "write"]
    assert "array_dev_data_0_write" in write_hooks
    assert "array_dev_data_3_write" in write_hooks


def test_regfile_flattens_with_prefix():
    top = compile_rdl_file(RDL_DIR / "regfile.rdl")
    model = build_device(top)
    assert [r.name for r in model.regs] == ["GRP_R0"]
    assert model.regs[0].offset == 0x00


def test_m5_arrays_example():
    from tests.conftest import EXAMPLES

    top = compile_rdl_file(EXAMPLES / "m5_arrays" / "m5_arrays.rdl")
    model = build_device(top)
    names = [r.name for r in model.regs]
    assert names[:4] == ["DATA_0", "DATA_1", "DATA_2", "DATA_3"]
    assert "GRP_R0" in names
    assert "GRP_R1" in names
    assert "BANK_0_V" in names
    assert "BANK_1_V" in names
    by_name = {r.name: r for r in model.regs}
    assert by_name["DATA_3"].offset == 0x0C
    assert by_name["GRP_R0"].offset == 0x100
    assert by_name["GRP_R1"].offset == 0x104
    assert by_name["BANK_0_V"].offset == 0x200
    assert by_name["BANK_1_V"].offset == 0x210


def test_ocores_i2c_shared_pairs():
    from tests.conftest import EXAMPLES

    top = compile_rdl_file(EXAMPLES / "ocores_i2c" / "ocores_i2c.rdl")
    model = build_device(top)
    by_name = {r.name: r for r in model.regs}
    assert set(by_name) == {"PRERLO", "PRERHI", "CTR", "TXR", "CR"}
    assert by_name["TXR"].is_shared_pair
    assert by_name["TXR"].pair_read_name == "RXR"
    assert by_name["TXR"].offset == 0x0C
    assert by_name["CR"].is_shared_pair
    assert by_name["CR"].pair_read_name == "SR"
    assert by_name["CR"].pulse & 0xF1 == 0xF1  # IACK, WR, RD, STO, STA
    assert model.irqs == 1
    names = {h.name for h in model.hooks}
    assert "ocores_i2c_cr_write" in names
    assert "ocores_i2c_ctr_write" in names
