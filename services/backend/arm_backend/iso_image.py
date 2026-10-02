"""Spot an ISO file that is shorter than its own file system says.

A copy or download that stopped partway leaves an image whose UDF partition
(or ISO 9660 volume) runs past the end of the file. MakeMKV then crashes or
lists nothing, and the extract fallback unpacks for half an hour only to
find the streams unreadable. Reading two descriptors answers it in
milliseconds, so `POST /api/iso/rips` refuses such a file up front.

Pure and dependency-free (stdlib only). Anything it can't read or doesn't
recognise yields None: unknown layouts are not judged, the rip just runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SECTOR = 2048

# A shortfall smaller than this is not a truncation: some tools trim
# trailing padding, and a real cut-off is gigabytes.
_TOLERANCE_BYTES = 64 * 1024**2

_ISO9660_PVD_SECTOR = 16
_UDF_ANCHOR_SECTOR = 256
_UDF_TAG_ANCHOR = 2
_UDF_TAG_PARTITION = 5
_UDF_TAG_TERMINATOR = 8
# The volume descriptor sequence is at most 16 sectors (ECMA-167 3/8.4.2);
# never walk further, whatever the anchor claims.
_UDF_MAX_VDS_SECTORS = 16


@dataclass(frozen=True)
class Truncation:
    present_bytes: int
    declared_bytes: int

    def message(self) -> str:
        return (
            f"This ISO is incomplete: {self.present_bytes / 1e9:.1f} GB of {self.declared_bytes / 1e9:.1f} GB "
            "is present (the copy or download stopped partway). Copy or download it again, then rip it."
        )


def _u32(b: bytes, at: int) -> int:
    return int.from_bytes(b[at : at + 4], "little")


def _u16(b: bytes, at: int) -> int:
    return int.from_bytes(b[at : at + 2], "little")


def _read(f: object, sector: int, size: int) -> bytes:
    f.seek(sector * SECTOR)  # type: ignore[attr-defined]
    data: bytes = f.read(size)  # type: ignore[attr-defined]
    return data


def declared_size(path: Path) -> int | None:
    """The largest end-of-volume the image's descriptors declare, in bytes:
    the ISO 9660 volume space size and/or the end of each UDF partition."""
    sizes: list[int] = []
    try:
        with open(path, "rb") as f:
            pvd = _read(f, _ISO9660_PVD_SECTOR, SECTOR)
            if len(pvd) == SECTOR and pvd[0] == 1 and pvd[1:6] == b"CD001":
                sizes.append(_u32(pvd, 80) * _u16(pvd, 128))

            anchor = _read(f, _UDF_ANCHOR_SECTOR, 24)
            if len(anchor) == 24 and _u16(anchor, 0) == _UDF_TAG_ANCHOR:
                vds_sectors = min(max(1, _u32(anchor, 16) // SECTOR), _UDF_MAX_VDS_SECTORS)
                vds_start = _u32(anchor, 20)
                for i in range(vds_sectors):
                    d = _read(f, vds_start + i, SECTOR)
                    if len(d) < 196:
                        break
                    tag = _u16(d, 0)
                    if tag == _UDF_TAG_PARTITION:
                        sizes.append((_u32(d, 188) + _u32(d, 192)) * SECTOR)
                    elif tag == _UDF_TAG_TERMINATOR:
                        break
    except OSError:
        return None
    return max(sizes) if sizes else None


def truncation(path: Path) -> Truncation | None:
    """A `Truncation` when the file is clearly shorter than its declared
    volume; None when it is complete or can't be judged."""
    declared = declared_size(path)
    if declared is None:
        return None
    try:
        present = os.path.getsize(path)
    except OSError:
        return None
    if declared - present > _TOLERANCE_BYTES:
        return Truncation(present_bytes=present, declared_bytes=declared)
    return None
