"""Source-path classification: real optical drive vs an .iso file on disk.

`ARM_MANUAL_TRIGGER_ISO` lets the ripper run its scan → identify → rip
pipeline against a file image instead of `/dev/sr0`. Four code paths
need to know which mode they're in (MakeMKV source URL on scan, MakeMKV
source URL on rip, mount options on the disc probe, drive-status probe
in the heartbeat). Rather than thread a mode flag through each callsite,
they each call `is_iso_source` on the bound device_path string.
"""

from __future__ import annotations

from pathlib import Path


def is_iso_source(path: str) -> bool:
    """True when `path` points at an `.iso` file on disk.

    Lower-case `.iso` suffix only — `.ISO` / `.img` / `.nrg` are not
    matched. Broadening the detection is intentionally out of scope:
    MakeMKV's `iso:` URL is happy with any UDF/ISO9660 image, but
    keeping the helper narrow avoids accidentally classifying a real
    device node as a file source.
    """
    return path.endswith(".iso") and Path(path).is_file()


def makemkv_source_url(path: str) -> str:
    """Build the `dev:<device>` or `iso:<file>` URL MakeMKV expects.

    Used by both `scan_disc` and `rip_disc`; centralising it here keeps
    the two callsites in lockstep.
    """
    return f"iso:{path}" if is_iso_source(path) else f"dev:{path}"
