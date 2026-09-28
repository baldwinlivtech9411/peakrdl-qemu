"""Intermediate representation of a QEMU device, independent of SystemRDL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .errors import SourceLoc

SW_READABLE = frozenset({"r", "rw", "rw1"})
SW_WRITABLE = frozenset({"w", "rw", "w1", "rw1"})


def field_mask(lsb: int, width: int) -> int:
    if width <= 0:
        return 0
    return ((1 << width) - 1) << lsb


@dataclass
class FieldModel:
    name: str
    lsb: int
    width: int
    reset: int
    sw: str
    hw: str
    onwrite: Optional[str]
    onread: Optional[str]
    singlepulse: bool
    hw_writable: bool
    hwset: bool
    hwclr: bool
    intr: bool
    desc: Optional[str] = None
    loc: SourceLoc = field(default_factory=SourceLoc)

    @property
    def mask(self) -> int:
        return field_mask(self.lsb, self.width)

    @property
    def msb(self) -> int:
        return self.lsb + self.width - 1


@dataclass
class RegisterModel:
    name: str
    offset: int
    width: int
    fields: List[FieldModel]
    desc: Optional[str]
    loc: SourceLoc
    qemu_read_hook: bool
    qemu_no_write_hook: bool
    reset: int = 0
    ro: int = 0
    w1c: int = 0
    cor: int = 0
    rsvd: int = 0
    rset: int = 0
    pulse: int = 0
    woset: int = 0
    wot: int = 0
    wzs: int = 0
    wzc: int = 0
    wzt: int = 0
    wclr: int = 0
    wset: int = 0
    has_write_hook: bool = False
    has_read_hook: bool = False
    read_hook_reg: Optional[str] = None
    is_shared_pair: bool = False
    pair_access_name: Optional[str] = None
    pair_read_name: Optional[str] = None
    pair_read_reset: int = 0
    pair_read_fields: List[FieldModel] = field(default_factory=list)
    pair_read_cor: int = 0
    pair_read_rset: int = 0
    shadow_name: Optional[str] = None

    @property
    def r_index(self) -> int:
        return self.offset // 4

    @property
    def name_lower(self) -> str:
        return self.name.lower()

    @property
    def access_name(self) -> str:
        return self.pair_access_name or self.name

    @property
    def sw_readable(self) -> bool:
        return any(f.sw in SW_READABLE for f in self.fields)

    @property
    def sw_writable(self) -> bool:
        return any(f.sw in SW_WRITABLE for f in self.fields)

    @property
    def hw_writable_fields(self) -> List[FieldModel]:
        return [f for f in self.fields if f.hw_writable or f.hwset or f.hwclr]

    @property
    def writeonly_mask(self) -> int:
        mask = 0
        for f in self.fields:
            if f.sw in ("w", "w1"):
                mask |= f.mask
        return mask & 0xFFFFFFFF

    @property
    def pair_hw_writable_fields(self) -> List[FieldModel]:
        return [
            f for f in self.pair_read_fields
            if f.hw_writable or f.hwset or f.hwclr
        ]

    @property
    def needs_pre_write(self) -> bool:
        return bool(
            self.woset
            or self.wot
            or self.wzs
            or self.wzc
            or self.wzt
            or self.wclr
            or self.wset
        )

    @property
    def needs_post_read(self) -> bool:
        if self.is_shared_pair:
            return True
        return bool(self.has_read_hook or self.writeonly_mask or self.rset)

    @property
    def needs_post_write(self) -> bool:
        return bool(self.has_write_hook or self.pulse)

    @property
    def post_read_uses_state(self) -> bool:
        return bool(
            self.has_read_hook
            or self.rset
            or self.is_shared_pair
        )

    @property
    def post_write_uses_val(self) -> bool:
        return self.has_write_hook

    @property
    def read_hook_name(self) -> str:
        return (self.read_hook_reg or self.name).lower()

    @property
    def readable_mask(self) -> int:
        """Bits software can observe on a 32-bit read of this access."""
        if self.is_shared_pair:
            mask = 0
            for f in self.pair_read_fields:
                if f.sw in SW_READABLE:
                    mask |= f.mask
            return mask & 0xFFFFFFFF
        return (~self.writeonly_mask) & 0xFFFFFFFF

    @property
    def rw_mask(self) -> int:
        """Bits that software can write and later read back as stored."""
        if self.is_shared_pair:
            return 0
        mask = 0
        for f in self.fields:
            if f.sw in ("rw", "rw1") and not f.singlepulse:
                if f.onwrite in (None, "woset", "wot", "wzs", "wzc", "wzt"):
                    if f.onread not in ("rclr", "rset"):
                        mask |= f.mask
        # reserved/RO bits are already excluded by sw
        return (mask & ~self.w1c & ~self.cor & ~self.pulse) & 0xFFFFFFFF

    @property
    def qtest_skip_reason(self) -> Optional[str]:
        """Why a generated qtest should skip this register, or None."""
        reasons = []
        if self.has_read_hook:
            reasons.append("qemu_read_hook can change the observed value")
        if self.is_shared_pair:
            reasons.append("read value comes from behavior-owned shadow storage")
        if reasons:
            return "; ".join(reasons)
        return None

    @property
    def qtest_hw_owned(self) -> bool:
        return bool(self.hw_writable_fields or self.pair_hw_writable_fields)

    @property
    def qtest_check_reset(self) -> bool:
        if self.qtest_skip_reason:
            return False
        if self.qtest_hw_owned:
            return False
        return True

    @property
    def qtest_check_rw(self) -> bool:
        if self.qtest_skip_reason or self.qtest_hw_owned:
            return False
        return self.rw_mask != 0

    @property
    def qtest_check_w1c(self) -> bool:
        return not self.qtest_skip_reason and self.w1c != 0

    @property
    def qtest_check_rclr(self) -> bool:
        return not self.qtest_skip_reason and self.cor != 0


@dataclass
class SharedPair:
    """A write-only / read-only register pair that share one address."""

    offset: int
    write_reg: str
    read_reg: str
    loc: SourceLoc
    write: Optional[RegisterModel] = None
    read: Optional[RegisterModel] = None

    @property
    def access_name(self) -> str:
        if self.write is not None and self.read is not None:
            return f"{self.write.name}_{self.read.name}"
        return f"{self.write_reg}_{self.read_reg}"

    @property
    def shadow_name(self) -> str:
        if self.write is not None and self.write.shadow_name:
            return self.write.shadow_name
        return f"shadow_{self.read_reg.lower()}"


@dataclass
class Hook:
    kind: str  # "init", "reset", "write", "read"
    name: str
    signature: str
    todo: str = "TODO: implement"


@dataclass
class DeviceModel:
    name: str
    name_upper: str
    name_camel: str
    qom_name: str
    desc: Optional[str]
    source_rdl: str
    generator_version: str
    license: str
    endianness: str
    qemu_subdir: str
    kconfig_selects: List[str]
    irqs: int
    mmio_size: int
    r_max: int
    regs: List[RegisterModel]
    shared_pairs: List[SharedPair]
    hooks: List[Hook]
    loc: SourceLoc = field(default_factory=SourceLoc)
    qtest_base: Optional[int] = None
    qtest_machine: Optional[str] = None

    @property
    def emit_qtest(self) -> bool:
        return self.qtest_base is not None and self.qtest_machine is not None

    @property
    def qtest_base_hex(self) -> str:
        return f"0x{self.qtest_base:x}" if self.qtest_base is not None else "0"

    @property
    def qtest_meson_name(self) -> str:
        return f"{self.name}-test"

    @property
    def type_macro(self) -> str:
        return f"TYPE_{self.name_upper}"

    @property
    def state_type(self) -> str:
        return f"{self.name_camel}State"

    @property
    def behavior_type(self) -> str:
        return f"{self.name_camel}Behavior"

    @property
    def func_prefix(self) -> str:
        return self.name
