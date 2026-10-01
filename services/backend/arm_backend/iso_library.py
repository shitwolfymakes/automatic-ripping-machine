"""Pure helpers for the ISO library (Rip from ISO, spec section 4.4).

Dependency-free on purpose: it imports only settings and the stdlib, so both
`ripper_manager` (spawn mounts) and `iso_rips` (lifecycle) can use it without
an import cycle.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from arm_backend.config import settings


def library_configured() -> bool:
    """The host path is set, absolute, and the backend's read-only mount of it
    exists. A relative value would make docker read the ripper's bind source
    as a named volume, so it counts as not configured."""
    host = settings.ARM_HOST_ISO_LIBRARY_PATH
    return bool(host) and Path(host).is_absolute() and Path(settings.ISO_INGRESS_ROOT).is_dir()


def library_host_path() -> str:
    return settings.ARM_HOST_ISO_LIBRARY_PATH


def iso_host_path(source_path: str, *, library_host: str | None = None) -> str:
    """Host path of one ISO: `<library host>/<source_path>`. `source_path` is
    always relative to the library (validated through file_browser.resolve
    before it is stored). `library_host` overrides the global setting, for a
    caller holding its own Settings (the ripper manager)."""
    base = library_host if library_host is not None else settings.ARM_HOST_ISO_LIBRARY_PATH
    return str(PurePosixPath(base) / source_path.lstrip("/"))
