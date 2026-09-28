"""PeakRDL plugin descriptor for the `qemu` exporter subcommand."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from peakrdl.plugins.exporter import ExporterSubcommandPlugin

from .errors import PeakRDLQEMUError
from .exporter import export_device
from .udps import UDP_DEFINITIONS

if TYPE_CHECKING:
    import argparse
    from systemrdl.node import AddrmapNode


class Exporter(ExporterSubcommandPlugin):
    short_desc = "Export a SystemRDL addrmap as a QEMU sysbus device model"
    long_desc = (
        "Generate QEMU register-API device sources from a SystemRDL 2.0 "
        "description. Generated files are always overwritten; behaviour stubs "
        "are written only if they do not already exist."
    )
    udp_definitions = UDP_DEFINITIONS

    def add_exporter_arguments(self, arg_group: "argparse._ActionsContainer") -> None:
        arg_group.add_argument(
            "--device-name",
            metavar="NAME",
            default=None,
            help="Device name (default: top addrmap instance name)",
        )
        arg_group.add_argument(
            "--qemu-subdir",
            metavar="SUBDIR",
            default="misc",
            help="hw/<subdir> to place sources under (default: misc)",
        )
        arg_group.add_argument(
            "--kconfig-select",
            metavar="SYM",
            action="append",
            default=[],
            help="Extra Kconfig symbols to select (repeatable, e.g. I2C)",
        )
        arg_group.add_argument(
            "--endianness",
            choices=["little", "big"],
            default="little",
            help="Device MMIO endianness (default: little)",
        )
        arg_group.add_argument(
            "--license",
            dest="license",
            metavar="SPDX_ID",
            default="GPL-2.0-or-later",
            help="SPDX license identifier for generated C (default: GPL-2.0-or-later)",
        )
        arg_group.add_argument(
            "--apply-to",
            dest="apply_to",
            metavar="QEMU_SRC_DIR",
            default=None,
            help="Copy generated files into a QEMU source tree and patch meson/Kconfig",
        )
        arg_group.add_argument(
            "--qtest-base",
            dest="qtest_base",
            metavar="ADDR",
            default=None,
            help="MMIO base used by the generated qtest (hex or decimal)",
        )
        arg_group.add_argument(
            "--qtest-machine",
            dest="qtest_machine",
            metavar="NAME",
            default=None,
            help="QEMU machine name for the generated qtest (e.g. virt)",
        )

    def main(self, importers, options):  # type: ignore[no-untyped-def]
        """Compile, elaborate, then export.

        PeakRDL 1.5 registers ``udp_definitions`` as *soft* UDPs, which cannot
        be assigned in RDL unless they are also declared there. Register them
        as hard UDPs so ``qemu_irqs = 1;`` works without an include file.
        """
        from peakrdl import process_input
        from systemrdl import RDLCompiler

        rdlc = RDLCompiler()
        for udp in self.udp_definitions:
            rdlc.register_udp(udp, soft=False)

        parameters = process_input.parse_parameters(rdlc, options.parameters)
        process_input.process_input(rdlc, importers, options.input_files, options)
        root = rdlc.elaborate(
            top_def_name=options.top_def_name,
            inst_name=options.inst_name,
            parameters=parameters,
        )
        self.do_export(root.top, options)

    def do_export(self, top_node: "AddrmapNode", options: "argparse.Namespace") -> None:
        source_rdl = "<input.rdl>"
        inputs = getattr(options, "input_files", None) or []
        if inputs:
            source_rdl = Path(str(inputs[-1])).as_posix()

        try:
            export_device(
                top_node,
                Path(options.output),
                device_name=options.device_name,
                qemu_subdir=options.qemu_subdir,
                kconfig_selects=options.kconfig_select or [],
                endianness=options.endianness,
                license_id=options.license,
                apply_to=Path(options.apply_to) if options.apply_to else None,
                source_rdl=source_rdl,
                qtest_base=_parse_addr(options.qtest_base),
                qtest_machine=options.qtest_machine,
            )
        except PeakRDLQEMUError as exc:
            loc = exc.loc.format()
            if loc:
                print(f"error: {exc.user_message} ({loc})", file=sys.stderr)
            else:
                print(f"error: {exc.user_message}", file=sys.stderr)
            sys.exit(1)


def _parse_addr(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    try:
        return int(text, 0)
    except ValueError as exc:
        raise PeakRDLQEMUError(
            f"--qtest-base must be an integer address, not {value!r}"
        ) from exc
