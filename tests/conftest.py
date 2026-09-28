"""Shared pytest helpers for compiling SystemRDL snippets."""

from __future__ import annotations

from pathlib import Path

import pytest
from systemrdl import RDLCompiler, RDLCompileError

from peakrdl_qemu.udps import UDP_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
RDL_DIR = Path(__file__).resolve().parent / "rdl"


def compile_rdl_text(text: str, *, name: str = "snippet.rdl"):
    path = Path("/tmp") / name
    path.write_text(text, encoding="utf-8")
    return compile_rdl_file(path)


def compile_rdl_file(path: Path):
    rdlc = RDLCompiler()
    for udp in UDP_DEFINITIONS:
        rdlc.register_udp(udp, soft=False)
    try:
        rdlc.compile_file(str(path))
        root = rdlc.elaborate()
    except RDLCompileError as exc:
        pytest.fail(f"SystemRDL compile failed for {path}: {exc}")
    return root.top


@pytest.fixture
def simple_timer_top():
    return compile_rdl_file(EXAMPLES / "simple_timer" / "simple_timer.rdl")
