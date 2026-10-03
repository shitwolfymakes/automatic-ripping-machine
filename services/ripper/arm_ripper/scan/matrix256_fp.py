"""matrix256v1 disc fingerprint via the reference `matrix256` library.

The digest itself is computed by the reference implementation (`matrix256`
on PyPI) — this module never reimplements the algorithm. What the spec
deliberately leaves to the caller (SPEC.md §1: mounting and filesystem-view
selection are outside the normative algorithm) is handled here:

1. The disc's tree is enumerated with pycdlib straight off the device or an
   ISO file — the same no-mount pattern as disc_probe's CRC64 and
   thediscdb_hash; the ripper runs without CAP_SYS_ADMIN and never mounts.
2. The enumerated (path, size) records are materialized as a sparse-file
   skeleton in a temporary directory: every regular file is created at its
   relative path and truncated to its size, which costs no disk (sparse) yet
   reports the exact `st_size` the library hashes. matrix256v1 hashes only
   paths and sizes, never contents, so the skeleton is a faithful input.
3. `matrix256.v1.fingerprint(skeleton_root)` produces the digest.

Filesystem-view selection follows the spec's implementer guidance
(IMPLEMENTERS.md §2): prefer UDF when present — the view desktop kernels
mount for commercial DVD/BD and the one the published corpus was generated
under — then Rock Ridge, then Joliet (the extended views that surface
full-length names, in the Linux kernel's own preference order), then bare
ISO 9660 with `;1` version suffixes stripped as a last resort. The chosen
view is logged with the digest; per the guidance, digests from different
views of the same disc legitimately differ.

Soft-fail everywhere: any error returns None and the fingerprint is simply
absent (a matrix256 miss only ever degrades to today's behavior).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

# pycdlib path-keyword per filesystem view, in preference order.
_VIEW_KEYS = (("udf", "udf_path"), ("rock_ridge", "rr_path"), ("joliet", "joliet_path"), ("iso_path", "iso_path"))


def fingerprint_records(records: Iterable[tuple[str, int]]) -> str:
    """matrix256v1 digest of (relative path, size) records, computed by the
    reference library against a sparse skeleton of the records.

    Every record becomes an empty file truncated to its size under a
    temporary root (sparse: no disk is consumed, `st_size` is exact), and
    the digest is `matrix256.v1.fingerprint` of that root. Path text
    (Unicode normalization, undecodable bytes) round-trips through the
    filesystem unaltered on Linux, so the library sees the same names
    pycdlib enumerated. Raises OSError on unmaterializable paths; the
    probe wrapper soft-fails.
    """
    from matrix256 import v1  # type: ignore[import-untyped]  # lazy: off the hot path

    with tempfile.TemporaryDirectory(prefix="arm-matrix256-") as tmp:
        root = Path(tmp)
        for relative, size in records:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
            os.truncate(target, size)
        digest: str = v1.fingerprint(root)
    return digest


def _choose_view(iso: Any) -> tuple[str, str] | None:
    """Pick the filesystem view to walk, per IMPLEMENTERS.md §2 preference."""
    for view, key in _VIEW_KEYS:
        try:
            if view == "udf" and iso.has_udf():
                return view, key
            if view == "rock_ridge" and iso.has_rock_ridge():
                return view, key
            if view == "joliet" and iso.has_joliet():
                return view, key
            if view == "iso_path":
                return "iso9660", key
        except Exception:  # noqa: BLE001 — a broken descriptor: try the next view
            continue
    return None


def _is_symlink(record: Any) -> bool:
    """True when the view's record marks a symbolic link (spec §2.1 skips
    them). Not every namespace can answer (plain ISO 9660 has no symlinks);
    an inconclusive record counts as a regular entry."""
    try:
        return bool(record.is_symlink())
    except Exception:  # noqa: BLE001 — namespace without symlink metadata
        return False


def _collect_from_iso(iso: Any) -> tuple[list[tuple[str, int]], str] | None:
    """Walk the opened pycdlib image's preferred view into (relative path,
    size) records for every regular file. Returns (records, view name), or
    None when no view is walkable."""
    chosen = _choose_view(iso)
    if chosen is None:
        return None
    view, key = chosen
    records: list[tuple[str, int]] = []
    for dirpath, _dirnames, filenames in iso.walk(**{key: "/"}):
        prefix = dirpath if dirpath.endswith("/") else dirpath + "/"
        for name in filenames:
            full = prefix + name
            record = iso.get_record(**{key: full})
            if _is_symlink(record):
                continue
            relative = full.lstrip("/")
            if view == "iso9660":
                # Bare ISO 9660 names carry `;1` version suffixes the kernel
                # never shows on a mount; strip them from the hashed path
                # (the pycdlib lookup above still needs the raw name).
                relative = relative.split(";", 1)[0]
            records.append((relative, record.get_data_length()))
    return records, view


def collect_tree_records(source_path: str) -> tuple[list[tuple[str, int]], str] | None:
    """Read the full-tree (path, size) records from a device or ISO path."""
    from pycdlib import PyCdlib  # lazy: keep import cost off the hot path

    iso = PyCdlib()
    iso.open(source_path)
    try:
        return _collect_from_iso(iso)
    finally:
        iso.close()


def probe_matrix256(source_path: str) -> str | None:
    """Compute the matrix256v1 fingerprint for a device/ISO path. Never raises.

    Returns None when the source has no readable filesystem or no regular
    files — an empty tree technically has a spec digest (SHA-256 of nothing),
    but emitting it would make every unreadable disc "match" every other, so
    like thediscdb we never fingerprint nothing.
    """
    try:
        collected = collect_tree_records(source_path)
        if collected is None:
            return None
        records, view = collected
        if not records:
            return None
        digest = fingerprint_records(records)
        logger.info("matrix256 view=%s files=%d source=%s", view, len(records), source_path)
    except Exception as e:  # noqa: BLE001 — pycdlib / OS errors, a few flavors
        logger.debug("matrix256 probe failed for %s: %s", source_path, e)
        return None
    return digest
