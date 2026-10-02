"""Source-path classification: real optical drive vs an .iso file on disk.

`ARM_SOURCE_PATH` lets the ripper run its scan → identify → rip
pipeline against a file image instead of `/dev/sr0`. Four code paths
need to know which mode they're in (MakeMKV source URL on scan, MakeMKV
source URL on rip, mount options on the disc probe, drive-status probe
in the heartbeat). Rather than thread a mode flag through each callsite,
they each call `is_iso_source` on the bound device_path string.
"""

from __future__ import annotations

from pathlib import Path

from arm_ripper import iso_extract


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
    """Build the `dev:<device>`, `iso:<file>` or `file:<folder>` URL MakeMKV expects.

    An ISO that `iso_extract` has unpacked (MakeMKV could not open the image
    itself) is read as its extracted disc folder. Used by both `scan_disc`
    and `rip_disc`; centralising it here keeps the two callsites in lockstep.
    """
    folder = iso_extract.extracted_dir(path)
    if folder is not None:
        return f"file:{folder}"
    return f"iso:{path}" if is_iso_source(path) else f"dev:{path}"
