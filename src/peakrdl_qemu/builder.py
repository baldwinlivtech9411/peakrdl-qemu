"""Build a DeviceModel from an elaborated SystemRDL addrmap."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from systemrdl.node import (
    AddrmapNode,
    FieldNode,
    MemNode,
    Node,
    RegNode,
    RegfileNode,
    SignalNode,
)
from systemrdl.rdltypes import AccessType, OnReadType, OnWriteType
from systemrdl.source_ref import DetailedFileSourceRef, FileSourceRef, SourceRefBase

from . import __version__
from .errors import PeakRDLQEMUError, SourceLoc
from .model import (
    DeviceModel,
    FieldModel,
    Hook,
    RegisterModel,
    SharedPair,
    field_mask,
)

REG_WIDTH_BITS = 32
REG_WIDTH_MASK = 0xFFFFFFFF

# Accellera onwrite/onread values we can implement. wuser/ruser stay rejected.
SUPPORTED_ONWRITE = {
    None,
    OnWriteType.woclr,
    OnWriteType.woset,
    OnWriteType.wot,
    OnWriteType.wzs,
    OnWriteType.wzc,
    OnWriteType.wzt,
    OnWriteType.wclr,
    OnWriteType.wset,
}
SUPPORTED_ONREAD = {
    None,
    OnReadType.rclr,
    OnReadType.rset,
}


def _src_loc(node: Node, prop: Optional[str] = None) -> SourceLoc:
    ref: Optional[SourceRefBase] = None
    if prop:
        ref = node.property_src_ref.get(prop)
    if ref is None:
        ref = node.inst_src_ref or node.def_src_ref
    if isinstance(ref, DetailedFileSourceRef):
        return SourceLoc(path=ref.path, line=ref.line)
    if isinstance(ref, FileSourceRef):
        return SourceLoc(path=ref.path)
    return SourceLoc()


def _access_name(value: Optional[AccessType]) -> str:
    if value is None:
        return "na"
    return value.name


def _onwrite_name(value: Optional[OnWriteType]) -> Optional[str]:
    return None if value is None else value.name


def _onread_name(value: Optional[OnReadType]) -> Optional[str]:
    return None if value is None else value.name


def _c_ident(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not ident or ident[0].isdigit():
        ident = "_" + ident
    return ident


def _camel_case(name: str) -> str:
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", name) if p]
    return "".join(p[:1].upper() + p[1:].lower() for p in parts) or "Device"


def _flatten_path_segment(seg: str) -> str:
    """DATA[0] -> DATA_0, MAT[1][2] -> MAT_1_2, GRP -> GRP."""
    ident = seg.replace("][", "_").replace("[", "_").replace("]", "")
    return _c_ident(ident).upper()


def _flattened_reg_name(reg: RegNode, top: AddrmapNode) -> str:
    """Prefix regfile parents and expand array indices into the C name."""
    segs = list(reg.get_path_segments())
    top_seg = top.get_path_segment()
    if segs and segs[0] == top_seg:
        segs = segs[1:]
    if not segs:
        _error(f"could not derive a register name for {reg.inst_name}", reg)
    return "_".join(_flatten_path_segment(s) for s in segs)


def _error(message: str, node: Optional[Node] = None, prop: Optional[str] = None) -> None:
    loc = _src_loc(node, prop) if node is not None else SourceLoc()
    raise PeakRDLQEMUError(message, loc)


def _is_counter_field(field: FieldNode) -> bool:
    if field.get_property("counter"):
        return True
    for prop in (
        "incr",
        "decr",
        "incrvalue",
        "decrvalue",
        "incrsaturate",
        "decrsaturate",
    ):
        val = field.get_property(prop)
        if val not in (None, False, 0):
            return True
    return False


def _reset_int(field: FieldNode) -> int:
    reset = field.get_property("reset")
    if reset is None:
        return 0
    if not isinstance(reset, int):
        _error(
            "non-integer field reset values are not supported",
            field,
            "reset",
        )
    return reset & field_mask(0, field.width)


def _hw_writable(field: FieldNode) -> bool:
    hw = field.get_property("hw")
    if hw in (AccessType.w, AccessType.rw, AccessType.w1, AccessType.rw1):
        return True
    we = field.get_property("we")
    wel = field.get_property("wel")
    if we not in (None, False) or wel not in (None, False):
        return True
    return False


def _compute_masks(reg: RegisterModel) -> None:
    covered = 0
    reset = 0
    ro = 0
    w1c = 0
    cor = 0
    rset = 0
    pulse = 0
    woset = 0
    wot = 0
    wzs = 0
    wzc = 0
    wzt = 0
    wclr = 0
    wset = 0
    for f in reg.fields:
        mask = f.mask
        covered |= mask
        reset |= (f.reset << f.lsb) & mask
        if f.sw in ("r",):
            ro |= mask
        if f.onwrite == "woclr":
            w1c |= mask
        elif f.onwrite == "woset":
            woset |= mask
        elif f.onwrite == "wot":
            wot |= mask
        elif f.onwrite == "wzs":
            wzs |= mask
        elif f.onwrite == "wzc":
            wzc |= mask
        elif f.onwrite == "wzt":
            wzt |= mask
        elif f.onwrite == "wclr":
            wclr |= mask
        elif f.onwrite == "wset":
            wset |= mask
        if f.onread == "rclr":
            cor |= mask
        elif f.onread == "rset":
            rset |= mask
        if f.singlepulse:
            pulse |= mask
    uncovered = (~covered) & REG_WIDTH_MASK
    # Bits not covered by any field are reserved. `.rsvd` only logs a warning
    # on write, so also OR them into `.ro` to actually block writes.
    rsvd = uncovered
    ro |= uncovered
    reg.reset = reset & REG_WIDTH_MASK
    reg.ro = ro & REG_WIDTH_MASK
    reg.w1c = w1c & REG_WIDTH_MASK
    reg.cor = cor & REG_WIDTH_MASK
    reg.rsvd = rsvd & REG_WIDTH_MASK
    reg.rset = rset & REG_WIDTH_MASK
    reg.pulse = pulse & REG_WIDTH_MASK
    reg.woset = woset & REG_WIDTH_MASK
    reg.wot = wot & REG_WIDTH_MASK
    reg.wzs = wzs & REG_WIDTH_MASK
    reg.wzc = wzc & REG_WIDTH_MASK
    reg.wzt = wzt & REG_WIDTH_MASK
    reg.wclr = wclr & REG_WIDTH_MASK
    reg.wset = wset & REG_WIDTH_MASK


def _register_hooks(reg: RegisterModel, dev_name: str) -> List[Hook]:
    hooks: List[Hook] = []
    camel = _camel_case(dev_name)
    if reg.sw_writable and not reg.qemu_no_write_hook:
        reg.has_write_hook = True
        hooks.append(
            Hook(
                kind="write",
                name=f"{dev_name}_{reg.name.lower()}_write",
                signature=(
                    f"void {dev_name}_{reg.name.lower()}_write("
                    f"{camel}State *s, uint32_t val)"
                ),
            )
        )
    hook_reg = reg.read_hook_reg or reg.name
    if reg.qemu_read_hook:
        reg.has_read_hook = True
        hooks.append(
            Hook(
                kind="read",
                name=f"{dev_name}_{hook_reg.lower()}_read",
                signature=(
                    f"uint32_t {dev_name}_{hook_reg.lower()}_read("
                    f"{camel}State *s, uint32_t val)"
                ),
            )
        )
    return hooks


def _walk_unsupported_children(node: Node) -> None:
    for child in node.children(skip_not_present=True):
        if isinstance(child, MemNode):
            _error("mem components are not supported", child)
        if isinstance(child, SignalNode):
            continue
        if isinstance(child, (AddrmapNode, RegfileNode, RegNode, FieldNode)):
            continue
        ctype = getattr(child, "component_type_name", None) or type(child).__name__
        _error(f"{ctype} components are not supported", child)


def _validate_field(field: FieldNode, parent: RegNode) -> FieldModel:
    loc = _src_loc(field)
    if field.external:
        _error("external components are not supported", field)

    sw = field.get_property("sw")
    hw = field.get_property("hw")
    onwrite = field.get_property("onwrite")
    onread = field.get_property("onread")
    singlepulse = bool(field.get_property("singlepulse"))

    if _is_counter_field(field):
        _error("counters are not supported", field, "counter")

    if onwrite not in SUPPORTED_ONWRITE:
        name = _onwrite_name(onwrite)
        _error(
            f"onwrite = {name} is not supported",
            field,
            "onwrite",
        )

    if onread not in SUPPORTED_ONREAD:
        name = _onread_name(onread)
        _error(
            f"onread = {name} is not supported",
            field,
            "onread",
        )

    if field.width < 1:
        _error("field width must be at least 1", field)

    lsb = int(field.lsb)
    width = int(field.width)
    if lsb < 0 or lsb + width > REG_WIDTH_BITS:
        _error(
            f"field {field.inst_name} bits [{field.msb}:{field.lsb}] exceed 32-bit register",
            field,
        )

    hwset = bool(field.get_property("hwset"))
    hwclr = bool(field.get_property("hwclr"))

    return FieldModel(
        name=_c_ident(field.inst_name).upper(),
        lsb=lsb,
        width=width,
        reset=_reset_int(field),
        sw=_access_name(sw),
        hw=_access_name(hw),
        onwrite=_onwrite_name(onwrite),
        onread=_onread_name(onread),
        singlepulse=singlepulse,
        hw_writable=_hw_writable(field),
        hwset=hwset,
        hwclr=hwclr,
        intr=bool(field.get_property("intr")),
        desc=field.get_property("name") or field.get_property("desc"),
        loc=loc,
    )


def _validate_reg(reg: RegNode, top: AddrmapNode) -> RegisterModel:
    if reg.external:
        _error("external components are not supported", reg)
    if reg.is_alias:
        _error("alias registers are not supported", reg)
    # Array instances are expanded by _collect_regs (current_idx set). Do not
    # reject is_array here — unrolled nodes still report is_array=True.
    width = int(reg.get_property("regwidth"))
    if width != REG_WIDTH_BITS:
        _error(
            f"regwidth = {width} is not supported (v1 supports 32-bit registers only)",
            reg,
            "regwidth",
        )
    offset = int(reg.absolute_address)
    if offset % 4 != 0:
        _error(
            f"register offset 0x{offset:x} is not 4-byte aligned",
            reg,
        )

    fields = []
    covered_bits = 0
    for field in reg.fields(skip_not_present=True):
        fm = _validate_field(field, reg)
        overlap = covered_bits & fm.mask
        if overlap:
            _error(
                f"overlapping fields in register {reg.inst_name}",
                field,
            )
        covered_bits |= fm.mask
        fields.append(fm)

    if not fields:
        _error(f"register {reg.inst_name} has no fields", reg)

    qemu_read_hook = bool(reg.get_property("qemu_read_hook"))
    qemu_no_write_hook = bool(reg.get_property("qemu_no_write_hook"))

    model = RegisterModel(
        name=_flattened_reg_name(reg, top),
        offset=offset,
        width=width,
        fields=fields,
        desc=reg.get_property("name") or reg.get_property("desc"),
        loc=_src_loc(reg),
        qemu_read_hook=qemu_read_hook,
        qemu_no_write_hook=qemu_no_write_hook,
    )
    _compute_masks(model)
    return model


def _merge_shared_pair(write: RegisterModel, read: RegisterModel) -> RegisterModel:
    """Fold a WO/RO pair into one RegisterAccessInfo (write-side storage)."""
    merged = RegisterModel(
        name=write.name,
        offset=write.offset,
        width=write.width,
        fields=list(write.fields),
        desc=write.desc,
        loc=write.loc,
        qemu_read_hook=bool(read.qemu_read_hook or write.qemu_read_hook),
        qemu_no_write_hook=write.qemu_no_write_hook,
        reset=write.reset,
        ro=write.ro,
        w1c=write.w1c,
        cor=0,  # read-side cor is applied to the shadow, not write storage
        rsvd=write.rsvd,
        rset=0,
        pulse=write.pulse,
        woset=write.woset,
        wot=write.wot,
        wzs=write.wzs,
        wzc=write.wzc,
        wzt=write.wzt,
        wclr=write.wclr,
        wset=write.wset,
        is_shared_pair=True,
        pair_access_name=f"{write.name}_{read.name}",
        pair_read_name=read.name,
        pair_read_reset=read.reset,
        pair_read_fields=list(read.fields),
        pair_read_cor=read.cor,
        pair_read_rset=read.rset,
        shadow_name=f"shadow_{read.name.lower()}",
        read_hook_reg=read.name if read.qemu_read_hook else write.name,
    )
    return merged


def _group_by_offset(
    regs: Sequence[RegNode],
) -> Tuple[List[RegNode], List[Tuple[RegNode, RegNode]], List[Tuple[RegNode, ...]]]:
    """Partition registers into unique-offset, (write, read) pairs, and other overlaps."""
    by_off: Dict[int, List[RegNode]] = defaultdict(list)
    for r in regs:
        by_off[int(r.absolute_address)].append(r)

    unique: List[RegNode] = []
    pairs: List[Tuple[RegNode, RegNode]] = []
    other: List[Tuple[RegNode, ...]] = []

    for offset, group in sorted(by_off.items()):
        if len(group) == 1:
            unique.append(group[0])
            continue
        if len(group) == 2:
            a, b = group
            a_w = a.has_sw_writable and not a.has_sw_readable
            a_r = a.has_sw_readable and not a.has_sw_writable
            b_w = b.has_sw_writable and not b.has_sw_readable
            b_r = b.has_sw_readable and not b.has_sw_writable
            if (a_w and b_r) or (a_r and b_w):
                w = a if a_w else b
                rnode = b if a_w else a
                pairs.append((w, rnode))
                continue
        other.append(tuple(group))
    return unique, pairs, other


def _collect_regs(top: AddrmapNode) -> List[RegNode]:
    regs: List[RegNode] = []

    def walk(node: Node) -> None:
        _walk_unsupported_children(node)
        for child in node.children(unroll=True, skip_not_present=True):
            if isinstance(child, RegfileNode):
                if child.external:
                    _error("external components are not supported", child)
                walk(child)
            elif isinstance(child, AddrmapNode):
                if child is not top:
                    _error("nested addrmap components are not supported", child)
            elif isinstance(child, RegNode):
                regs.append(child)
            elif isinstance(child, MemNode):
                _error("mem components are not supported", child)
            elif isinstance(child, SignalNode):
                continue
            elif isinstance(child, FieldNode):
                continue
            else:
                walk(child)

    walk(top)
    return regs


def _irq_count(top: AddrmapNode) -> int:
    explicit = top.get_property("qemu_irqs")
    if explicit is not None:
        if not isinstance(explicit, int) or explicit < 0:
            _error("qemu_irqs must be a non-negative integer", top, "qemu_irqs")
        return int(explicit)
    return 0


def build_device(
    top: AddrmapNode,
    *,
    device_name: Optional[str] = None,
    source_rdl: str = "<input.rdl>",
    license_id: str = "GPL-2.0-or-later",
    endianness: str = "little",
    qemu_subdir: str = "misc",
    kconfig_selects: Optional[Iterable[str]] = None,
    generator_version: Optional[str] = None,
    qtest_base: Optional[int] = None,
    qtest_machine: Optional[str] = None,
) -> DeviceModel:
    """Convert an elaborated addrmap into a DeviceModel."""
    inst_name = device_name or top.inst_name
    if not inst_name:
        _error("could not determine device name; pass --device-name", top)

    c_name = _c_ident(inst_name).lower()
    name_upper = c_name.upper()
    name_camel = _camel_case(c_name)
    qom_name = c_name.replace("_", "-")

    if endianness not in ("little", "big"):
        raise PeakRDLQEMUError(
            f"endianness must be 'little' or 'big', not {endianness!r}"
        )
    if (qtest_base is None) ^ (not qtest_machine):
        raise PeakRDLQEMUError(
            "--qtest-base and --qtest-machine must be given together"
        )
    if qtest_base is not None and qtest_base < 0:
        raise PeakRDLQEMUError("--qtest-base must be a non-negative address")

    regs_nodes = _collect_regs(top)
    unique, pair_nodes, other_overlaps = _group_by_offset(regs_nodes)

    if other_overlaps:
        group = other_overlaps[0]
        names = ", ".join(r.inst_name for r in group)
        _error(
            f"overlapping registers at 0x{int(group[0].address_offset):x}: {names}",
            group[0],
        )

    registers: List[RegisterModel] = []
    shared_pairs: List[SharedPair] = []

    for node in unique:
        registers.append(_validate_reg(node, top))

    for write_node, read_node in pair_nodes:
        write = _validate_reg(write_node, top)
        read = _validate_reg(read_node, top)
        merged = _merge_shared_pair(write, read)
        registers.append(merged)
        shared_pairs.append(
            SharedPair(
                offset=merged.offset,
                write_reg=write.name,
                read_reg=read.name,
                loc=write.loc,
                write=write,
                read=read,
            )
        )

    registers.sort(key=lambda r: r.offset)

    if not registers:
        _error("addrmap contains no registers", top)

    occupied: Dict[int, str] = {}
    for r in registers:
        for byte in range(r.offset, r.offset + (r.width // 8)):
            if byte in occupied:
                _error(
                    f"overlapping registers {occupied[byte]} and {r.name} at 0x{byte:x}",
                    None,
                )
            occupied[byte] = r.name

    highest = max(r.offset + (r.width // 8) for r in registers)
    mmio_size = (highest + 3) & ~3
    addrmap_size = int(top.size)
    addrmap_size = (addrmap_size + 3) & ~3
    if addrmap_size > mmio_size:
        mmio_size = addrmap_size
    r_max = mmio_size // 4

    irqs = _irq_count(top)

    hooks: List[Hook] = [
        Hook(
            kind="init",
            name=f"{c_name}_behavior_init",
            signature=f"void {c_name}_behavior_init({name_camel}State *s)",
        ),
        Hook(
            kind="reset",
            name=f"{c_name}_behavior_reset",
            signature=f"void {c_name}_behavior_reset({name_camel}State *s)",
        ),
    ]
    for r in registers:
        hooks.extend(_register_hooks(r, c_name))

    desc = top.get_property("name") or top.get_property("desc")

    return DeviceModel(
        name=c_name,
        name_upper=name_upper,
        name_camel=name_camel,
        qom_name=qom_name,
        desc=desc,
        source_rdl=source_rdl,
        generator_version=generator_version or __version__,
        license=license_id,
        endianness=endianness,
        qemu_subdir=qemu_subdir,
        kconfig_selects=list(kconfig_selects or []),
        irqs=irqs,
        mmio_size=mmio_size,
        r_max=r_max,
        regs=registers,
        shared_pairs=shared_pairs,
        hooks=hooks,
        loc=_src_loc(top),
        qtest_base=qtest_base,
        qtest_machine=qtest_machine,
    )
