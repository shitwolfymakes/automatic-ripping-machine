"""UDF-only images (no ISO 9660 descriptor) read through 7-Zip.

PyCdlib refuses an image without a primary volume descriptor, and that is
exactly what a DVDFab UDF 2.50 Blu-ray backup looks like, so the BD disc
title and the matrix256 fingerprint were unavailable for them. 7-Zip's UDF
reader lists the tree with sizes and extracts single files without mounting
anything, which keeps the ripper unprivileged. Every function here returns
None instead of raising, and None also when 7z is not installed.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger("arm_ripper.scan.udf_image")

_LIST_TIMEOUT_SECONDS = 180
_READ_TIMEOUT_SECONDS = 60


def _exe() -> str | None:
    # Debian 12's `7zip` package (the ripper image) ships only `7zz`; p7zip
    # and newer Debian install `7z`.
    return shutil.which("7z") or shutil.which("7zz")


def available() -> bool:
    return _exe() is not None


def _run(args: list[str], timeout: float) -> bytes | None:
    exe = _exe()
    if exe is None:
        return None
    try:
        proc = subprocess.run([exe, *args], capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("7z %s failed: %s", args[:2], e)
        return None
    if proc.returncode != 0:
        logger.debug("7z %s exited %d: %s", args[:2], proc.returncode, proc.stderr[-200:].decode(errors="replace"))
        return None
    return proc.stdout


def parse_listing(text: str) -> list[tuple[str, int]]:
    """(relative path, size) for every regular file in a `7z l -slt` listing."""
    records: list[tuple[str, int]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                fields[key] = value
        path = fields.get("Path")
        if not path or "Folder" not in fields or fields["Folder"] != "-":
            continue
        try:
            size = int(fields.get("Size") or "")
        except ValueError:
            continue
        records.append((path.replace("\\", "/").lstrip("/"), size))
    return records


def list_files(image_path: str) -> list[tuple[str, int]] | None:
    """Every regular file in the image as (relative path, size), or None."""
    out = _run(["l", "-slt", "-ba", "--", image_path], _LIST_TIMEOUT_SECONDS)
    if out is None:
        return None
    records = parse_listing(out.decode("utf-8", "replace"))
    return records or None


def read_file(image_path: str, inner_path: str) -> bytes | None:
    """The bytes of one file inside the image (`inner_path` relative), or None."""
    out = _run(["e", "-so", "--", image_path, inner_path.lstrip("/")], _READ_TIMEOUT_SECONDS)
    if not out:
        return None
    return out
