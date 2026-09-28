"""Hook-diff report on regeneration (M5)."""

from __future__ import annotations

from peakrdl_qemu.exporter import export_device
from tests.conftest import compile_rdl_text


def test_hook_diff_new_and_stale(tmp_path, capsys):
    first = """
    addrmap hookdiff {
        default regwidth = 32;
        default hw = r;
        reg { field { sw = rw; } A[31:0]; } OLD @ 0x00;
        reg { field { sw = rw; } B[31:0]; } KEEP @ 0x04;
    };
    """
    top = compile_rdl_text(first, name="hookdiff1.rdl")
    export_device(top, tmp_path, source_rdl="hookdiff.rdl")
    behavior = tmp_path / "hookdiff_behavior.c"
    assert behavior.exists()
    original = behavior.read_text(encoding="utf-8")
    assert "hookdiff_old_write" in original
    assert "hookdiff_keep_write" in original

    second = """
    addrmap hookdiff {
        default regwidth = 32;
        default hw = r;
        reg { field { sw = rw; } B[31:0]; } KEEP @ 0x04;
        reg { field { sw = rw; } C[31:0]; } NEWREG @ 0x08;
    };
    """
    top2 = compile_rdl_text(second, name="hookdiff2.rdl")
    export_device(top2, tmp_path, source_rdl="hookdiff.rdl")
    # behavior.c is not overwritten
    assert behavior.read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "NEW HOOK: void hookdiff_newreg_write(HookdiffState *s, uint32_t val)" in out
    assert "STALE HOOK: hookdiff_old_write" in out
    new_file = tmp_path / "hookdiff_behavior.new_hooks.c"
    assert new_file.exists()
    text = new_file.read_text(encoding="utf-8")
    assert "hookdiff_newreg_write" in text
    assert "hookdiff_old_write" not in text
    assert "hookdiff_keep_write" not in text
    # generated files did update
    gen = (tmp_path / "hookdiff_gen.c").read_text(encoding="utf-8")
    assert ".name = \"NEWREG\"" in gen
    assert ".name = \"OLD\"" not in gen


def test_first_export_does_not_emit_new_hooks(tmp_path, capsys):
    top = compile_rdl_text(
        """
        addrmap first {
            default regwidth = 32;
            default hw = r;
            reg { field { sw = rw; } A[31:0]; } R @ 0x00;
        };
        """,
        name="first.rdl",
    )
    export_device(top, tmp_path)
    out = capsys.readouterr().out
    assert "NEW HOOK:" not in out
    assert not (tmp_path / "first_behavior.new_hooks.c").exists()
