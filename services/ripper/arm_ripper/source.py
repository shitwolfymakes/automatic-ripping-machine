"""Source-path classification: real optical drive, an .iso file, or a disc folder.

`ARM_SOURCE_PATH` lets the ripper run its scan → identify → rip
pipeline against an image file or a disc folder (a BDMV / VIDEO_TS tree)
instead of `/dev/sr0`. The callsites that need to know (the MakeMKV
source URL on scan and rip, and every drive-only step: drive-status
ioctl, eject, scan settle retry, the optical fingerprint probe) classify
the bound device_path string here rather than thread a mode flag around:
`is_file_source` is "not a real drive", `is_iso_source` / `is_folder_source`
the two kinds.
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


_DISC_DIRS = ("BDMV", "VIDEO_TS")


def is_folder_source(path: str) -> bool:
    """True when `path` is a directory with a BDMV or VIDEO_TS tree at its root."""
    p = Path(path)
    return p.is_dir() and any((p / d).is_dir() for d in _DISC_DIRS)


def is_file_source(path: str) -> bool:
    """An ISO file or a disc folder: a source with no drive behind it."""
    return is_iso_source(path) or is_folder_source(path)


def makemkv_source_url(path: str) -> str:
    """Build the `dev:<device>`, `iso:<file>` or `file:<folder>` URL MakeMKV expects.

    A disc folder is read as `file:`; so is an ISO that `iso_extract` has
    unpacked (MakeMKV could not open the image itself). Used by both `scan_disc`
    and `rip_disc`; centralising it here keeps the two callsites in lockstep.
    """
    folder = iso_extract.extracted_dir(path)
    if folder is not None:
        return f"file:{_disc_tree(folder)}"
    if is_folder_source(path):
        return f"file:{_disc_tree(Path(path))}"
    return f"iso:{path}" if is_iso_source(path) else f"dev:{path}"


def _disc_tree(folder: Path) -> Path:
    """The BDMV (or VIDEO_TS) directory of a disc folder, which is what
    MakeMKV is pointed at. Never the disc folder itself: the ripper
    bind-mounts a disc folder at /source/<name>, and MakeMKV finds no disc at
    a mount root ("can't find any usable optical drives") while it reads the
    BDMV / VIDEO_TS directory below it fine."""
    for name in _DISC_DIRS:
        if (folder / name).is_dir():
            return folder / name
    return folder
