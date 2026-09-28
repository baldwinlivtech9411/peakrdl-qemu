"""Clean, location-aware errors for peakrdl-qemu.

These are converted to a single `error: ...` line on the CLI. Callers must
not let them escape as a Python traceback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SourceLoc:
    """Source location of an RDL construct, if known."""

    path: Optional[str] = None
    line: Optional[int] = None

    def format(self) -> str:
        if self.path and self.line is not None:
            return f"{self.path}:{self.line}"
        if self.path:
            return self.path
        return ""


class PeakRDLQEMUError(Exception):
    """User-facing exporter/builder error with optional file:line."""

    def __init__(self, message: str, loc: Optional[SourceLoc] = None) -> None:
        self.user_message = message
        self.loc = loc or SourceLoc()
        super().__init__(self.format_error())

    def format_error(self) -> str:
        loc = self.loc.format()
        if loc:
            return f"{loc}: {self.user_message}"
        return self.user_message
