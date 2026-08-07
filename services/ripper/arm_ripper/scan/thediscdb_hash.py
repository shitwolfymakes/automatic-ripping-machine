"""TheDiscDB ContentHash: MD5 over stream-file sizes, read via pycdlib.

Mirrors ImportBuddy's DiskContentHash.cs + HashingExtensions.cs exactly:
Blu-ray/UHD hashes `BDMV/STREAM/*.m2ts`; DVD hashes ALL files under
`VIDEO_TS/`; files are sorted by name ascending; each file's size is fed to
MD5 as 8 little-endian bytes. Reads the UDF/ISO tree straight from the block
device (or an ISO file) — same no-mount pattern as disc_probe's CRC64.

Soft-fail everywhere: any error returns None and the fingerprint is simply
absent (a TheDiscDB miss can only ever degrade to today's behavior).
"""

from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def compute_content_hash(sizes: Sequence[int]) -> str | None:
    """MD5 over each size as 8-byte little-endian, uppercase hex.

    Sizes must already be in filename order. Returns None for an empty list
    (never emit MD5-of-nothing — it would collide across all empty discs).
    """
    if not sizes:
        return None
    md5 = hashlib.md5()
    for size in sizes:
        md5.update(struct.pack("<q", size))
    return md5.hexdigest().upper()


def _clean_iso_name(name: str) -> str:
    """Strip ISO9660 `;1` version suffixes; UDF names pass through."""
    return name.split(";", 1)[0]


def _hash_from_listing(files: list[tuple[str, int]]) -> str | None:
    """Hash a (name, size) listing: sort by name, hash sizes. No filtering —
    the caller decides the file set."""
    ordered = sorted(files, key=lambda item: item[0])
    return compute_content_hash([size for _, size in ordered])


def collect_hash_files(source_path: str) -> list[tuple[str, int]] | None:
    """Read the hashable file set from a device or ISO path via pycdlib.

    Blu-ray/UHD: `/BDMV/STREAM/*.m2ts` (UDF). DVD: every file in `/VIDEO_TS`
    (ISO9660/UDF). Returns None when neither directory exists (CD, data disc).
    """
    from pycdlib import PyCdlib  # lazy: keep import cost off the hot path

    iso = PyCdlib()
    iso.open(source_path)
    try:
        # Blu-ray first: UDF filesystem, STREAM directory.
        try:
            listing = [
                (_clean_iso_name(child.file_identifier().decode("utf-8", "replace")), child.get_data_length())
                for child in iso.list_children(udf_path="/BDMV/STREAM")
                if child is not None and not child.is_dir()
            ]
            m2ts = [(n, s) for n, s in listing if n.lower().endswith(".m2ts")]
            if m2ts:
                return m2ts
        except Exception:  # noqa: BLE001 — no UDF / no BDMV: fall through to DVD
            pass

        for kwargs in ({"iso_path": "/VIDEO_TS"}, {"udf_path": "/VIDEO_TS"}):
            try:
                return [
                    (_clean_iso_name(child.file_identifier().decode("utf-8", "replace")), child.get_data_length())
                    for child in iso.list_children(**kwargs)
                    if child is not None and not child.is_dir() and not child.is_dot() and not child.is_dotdot()
                ]
            except Exception:  # noqa: BLE001 — try next namespace
                continue
        return None
    finally:
        iso.close()


def probe_thediscdb_hash(source_path: str) -> str | None:
    """Compute the ContentHash for a device/ISO path. Never raises."""
    try:
        files = collect_hash_files(source_path)
        if not files:
            return None
        return _hash_from_listing(files)
    except Exception as e:  # noqa: BLE001 — pycdlib / struct.error on out-of-range sizes
        logger.debug("thediscdb hash probe failed for %s: %s", source_path, e)
        return None
