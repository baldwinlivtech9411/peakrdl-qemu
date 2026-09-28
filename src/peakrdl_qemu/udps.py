"""User-defined properties registered by the peakrdl-qemu exporter."""

from __future__ import annotations

from typing import Any, List, Type

from systemrdl import component as comp
from systemrdl.node import FieldNode, Node
from systemrdl.udp import UDPDefinition


class QemuIrqsUDP(UDPDefinition):
    """Number of sysbus IRQ outputs on the generated device."""

    name = "qemu_irqs"
    valid_components = {comp.Addrmap}
    valid_type = int
    default_assignment = 0

    def get_unassigned_default(self, node: Node) -> Any:
        # Implied default: 1 if any field is an interrupt, otherwise 0.
        for descendant in node.descendants(skip_not_present=True):
            if isinstance(descendant, FieldNode) and descendant.get_property("intr"):
                return 1
        return 0


class QemuReadHookUDP(UDPDefinition):
    """Generate a software-read hook for this register."""

    name = "qemu_read_hook"
    valid_components = {comp.Reg}
    valid_type = bool
    # Bound as `qemu_read_hook;` (no RHS) means true. Unassigned stays false.
    default_assignment = True

    def get_unassigned_default(self, node: Node) -> Any:
        return False


class QemuNoWriteHookUDP(UDPDefinition):
    """Suppress the default write hook for a writable register."""

    name = "qemu_no_write_hook"
    valid_components = {comp.Reg}
    valid_type = bool
    default_assignment = True

    def get_unassigned_default(self, node: Node) -> Any:
        return False


UDP_DEFINITIONS: List[Type[UDPDefinition]] = [
    QemuIrqsUDP,
    QemuReadHookUDP,
    QemuNoWriteHookUDP,
]
