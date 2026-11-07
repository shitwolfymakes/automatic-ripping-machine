"""The outcome of one rip, shared by every ripper (MakeMKV, abcde and dd)."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RipResult:
    """One rip or one ripped title: the output file on success, the error text on failure."""

    ok: bool
    output_path: Path | None = None
    size_bytes: int | None = None
    duration_seconds: int | None = None
    sha256: str | None = None
    error: str | None = None
