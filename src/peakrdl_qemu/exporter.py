"""Render DeviceModel through Jinja2 templates and optionally apply to QEMU."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import __version__
from .builder import build_device
from .errors import PeakRDLQEMUError
from .model import DeviceModel

try:
    from systemrdl.node import AddrmapNode
except ImportError:  # pragma: no cover
    AddrmapNode = object  # type: ignore


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# (template, dest filename formatter, overwrite?)
GENERATED_FILES = [
    ("regs.h.j2", "{name}_regs.h", True),
    ("device.h.j2", "{name}.h", True),
    ("gen.c.j2", "{name}_gen.c", True),
    ("meson.snippet.j2", "meson.build.snippet", True),
    ("kconfig.snippet.j2", "Kconfig.snippet", True),
]
QTEST_FILES = [
    ("qtest.c.j2", "{name}-test.c", True),
    ("qtest.meson.snippet.j2", "qtest.meson.build.snippet", True),
]
STUB_FILES = [
    ("behavior.h.j2", "{name}_behavior.h", False),
    ("behavior.c.j2", "{name}_behavior.c", False),
]

BEGIN_MARKER = "# BEGIN peakrdl-qemu {dev}"
END_MARKER = "# END peakrdl-qemu {dev}"

_HOOK_START_RE = re.compile(r"^(?:void|uint32_t)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _c_hex(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08x}"


def _c_hex_short(value: int) -> str:
    return f"0x{value:x}"


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )
    env.filters["c_hex"] = _c_hex
    env.filters["c_hex_short"] = _c_hex_short
    return env


def render_template(env: Environment, name: str, model: DeviceModel) -> str:
    template = env.get_template(name)
    text = template.render(d=model, version=__version__)
    # Deterministic: Unix newlines, no trailing whitespace.
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines) + "\n"


def write_file(path: Path, content: str, overwrite: bool) -> str:
    """Write content. Returns 'wrote', 'kept', or 'unchanged'."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return "unchanged"
        if not overwrite:
            print(f"kept existing {path}")
            return "kept"
    path.write_text(content, encoding="utf-8", newline="\n")
    return "wrote"


def _parse_defined_hooks(text: str) -> List[str]:
    """Return C function names defined at column 0 in behavior.c."""
    names: List[str] = []
    for line in text.splitlines():
        m = _HOOK_START_RE.match(line)
        if m:
            names.append(m.group(1))
    return names


def report_hook_diff(model: DeviceModel, behavior_c: Path, outdir: Path) -> None:
    """Print NEW HOOK / STALE HOOK and write <dev>_behavior.new_hooks.c."""
    existing = behavior_c.read_text(encoding="utf-8")
    defined = set(_parse_defined_hooks(existing))
    new_hooks = [h for h in model.hooks if h.name not in defined]
    declared_names = {h.name for h in model.hooks}
    stale = [
        name for name in _parse_defined_hooks(existing) if name not in declared_names
    ]

    for h in new_hooks:
        print(f"NEW HOOK: {h.signature}")
    for name in stale:
        print(f"STALE HOOK: {name}")

    if not new_hooks:
        return

    env = make_env()
    slim = DeviceModel(
        name=model.name,
        name_upper=model.name_upper,
        name_camel=model.name_camel,
        qom_name=model.qom_name,
        desc=model.desc,
        source_rdl=model.source_rdl,
        generator_version=model.generator_version,
        license=model.license,
        endianness=model.endianness,
        qemu_subdir=model.qemu_subdir,
        kconfig_selects=list(model.kconfig_selects),
        irqs=model.irqs,
        mmio_size=model.mmio_size,
        r_max=model.r_max,
        regs=list(model.regs),
        shared_pairs=list(model.shared_pairs),
        hooks=new_hooks,
        loc=model.loc,
        qtest_base=model.qtest_base,
        qtest_machine=model.qtest_machine,
    )
    content = render_template(env, "behavior.c.j2", slim)
    dest = outdir / f"{model.name}_behavior.new_hooks.c"
    dest.write_text(content, encoding="utf-8", newline="\n")


def export_model(model: DeviceModel, outdir: Path) -> Dict[str, str]:
    """Render all files into outdir. Returns status per filename."""
    env = make_env()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    status: Dict[str, str] = {}
    files = list(GENERATED_FILES + STUB_FILES)
    if model.emit_qtest:
        files.extend(QTEST_FILES)
    for template, fmt, overwrite in files:
        filename = fmt.format(name=model.name)
        content = render_template(env, template, model)
        status[filename] = write_file(outdir / filename, content, overwrite)
        if filename == f"{model.name}_behavior.c" and status[filename] == "kept":
            report_hook_diff(model, outdir / filename, outdir)
    return status


def _snippet_block(dev: str, body: str) -> str:
    begin = BEGIN_MARKER.format(dev=dev)
    end = END_MARKER.format(dev=dev)
    body = body.rstrip() + "\n"
    return f"{begin}\n{body}{end}\n"


def _replace_or_append(path: Path, dev: str, body: str) -> str:
    """Idempotently insert a marked snippet into path. Returns action."""
    block = _snippet_block(dev, body)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(block, encoding="utf-8", newline="\n")
        return "wrote"
    text = path.read_text(encoding="utf-8")
    begin = BEGIN_MARKER.format(dev=dev)
    end = END_MARKER.format(dev=dev)
    if begin in text and end in text:
        pre, rest = text.split(begin, 1)
        _, post = rest.split(end, 1)
        new = pre.rstrip("\n") + "\n" + block + post.lstrip("\n")
        if not new.endswith("\n"):
            new += "\n"
        if new == text:
            return "unchanged"
        path.write_text(new, encoding="utf-8", newline="\n")
        return "replaced"
    # Append
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block, encoding="utf-8", newline="\n")
    return "appended"


def apply_to_qemu(model: DeviceModel, qemu_src: Path, generated_dir: Path) -> None:
    qemu_src = Path(qemu_src)
    subdir = qemu_src / "hw" / model.qemu_subdir
    if not subdir.is_dir():
        raise PeakRDLQEMUError(
            f"--apply-to: hw/{model.qemu_subdir} does not exist under {qemu_src}"
        )

    env = make_env()
    copies = [
        ("regs.h.j2", f"{model.name}_regs.h", True),
        ("device.h.j2", f"{model.name}.h", True),
        ("gen.c.j2", f"{model.name}_gen.c", True),
        ("behavior.h.j2", f"{model.name}_behavior.h", False),
        ("behavior.c.j2", f"{model.name}_behavior.c", False),
    ]
    for template, filename, overwrite in copies:
        # Prefer already-rendered files from outdir so a kept stub is reused.
        src = generated_dir / filename
        if src.exists() and not overwrite:
            content = src.read_text(encoding="utf-8")
        else:
            content = render_template(env, template, model)
        action = write_file(subdir / filename, content, overwrite)
        if filename == f"{model.name}_behavior.c" and action == "kept":
            report_hook_diff(model, subdir / filename, generated_dir)

    meson_body = render_template(env, "meson.snippet.j2", model)
    kconfig_body = render_template(env, "kconfig.snippet.j2", model)
    _replace_or_append(subdir / "meson.build", model.name_upper, meson_body)
    _replace_or_append(subdir / "Kconfig", model.name_upper, kconfig_body)

    if model.emit_qtest:
        qtest_dir = qemu_src / "tests" / "qtest"
        if not qtest_dir.is_dir():
            raise PeakRDLQEMUError(
                f"--apply-to: tests/qtest does not exist under {qemu_src}"
            )
        qtest_name = f"{model.name}-test.c"
        src = generated_dir / qtest_name
        if src.exists():
            content = src.read_text(encoding="utf-8")
        else:
            content = render_template(env, "qtest.c.j2", model)
        write_file(qtest_dir / qtest_name, content, True)
        qmeson = render_template(env, "qtest.meson.snippet.j2", model)
        _insert_qtest_meson(qtest_dir / "meson.build", model.name_upper, qmeson)


def _insert_qtest_meson(path: Path, dev: str, body: str) -> str:
    """Place the snippet after `qtests_riscv64 =` so the list is still live."""
    block = _snippet_block(dev, body)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    begin = BEGIN_MARKER.format(dev=dev)
    end = END_MARKER.format(dev=dev)
    if begin in text and end in text:
        pre, rest = text.split(begin, 1)
        _, post = rest.split(end, 1)
        new = pre.rstrip("\n") + "\n" + block + post.lstrip("\n")
        if not new.endswith("\n"):
            new += "\n"
        if new == text:
            return "unchanged"
        path.write_text(new, encoding="utf-8", newline="\n")
        return "replaced"
    marker = "qtests_riscv64 ="
    idx = text.find(marker)
    if idx != -1:
        # The assignment is often continued with `\`. Skip to the first
        # following non-continued line so meson still parses it.
        insert_at = len(text)
        i = idx
        while True:
            nl = text.find("\n", i)
            if nl == -1:
                insert_at = len(text)
                break
            line = text[i:nl].rstrip()
            i = nl + 1
            if not line.endswith("\\"):
                insert_at = i
                break
        new = text[:insert_at] + block + text[insert_at:]
        path.write_text(new, encoding="utf-8", newline="\n")
        return "inserted"
    return _replace_or_append(path, dev, body)


def export_device(
    top: AddrmapNode,
    outdir: Path,
    *,
    device_name: Optional[str] = None,
    qemu_subdir: str = "misc",
    kconfig_selects: Optional[Iterable[str]] = None,
    endianness: str = "little",
    license_id: str = "GPL-2.0-or-later",
    apply_to: Optional[Path] = None,
    source_rdl: str = "<input.rdl>",
    qtest_base: Optional[int] = None,
    qtest_machine: Optional[str] = None,
) -> DeviceModel:
    model = build_device(
        top,
        device_name=device_name,
        source_rdl=source_rdl,
        license_id=license_id,
        endianness=endianness,
        qemu_subdir=qemu_subdir,
        kconfig_selects=kconfig_selects,
        generator_version=__version__,
        qtest_base=qtest_base,
        qtest_machine=qtest_machine,
    )
    outdir = Path(outdir)
    export_model(model, outdir)
    if apply_to is not None:
        apply_to_qemu(model, Path(apply_to), outdir)
    return model
