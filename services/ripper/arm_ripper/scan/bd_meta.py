"""Blu-ray BDMT disc title: BDMV/META/DL/bdmt_<lang>.xml read via pycdlib
(same no-mount pattern as thediscdb_hash). Soft-fail: any error -> None."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from arm_common.schemas import BdDiscMeta

logger = logging.getLogger(__name__)

_DI = "{urn:BDA:bdmv;discinfo}"
_BDMT_RE = re.compile(r"^bdmt_([a-z]{3})\.xml(?:;\d+)?$", re.IGNORECASE)
_META_DIR = "/BDMV/META/DL"


def pick_bdmt_file(names: list[str]) -> tuple[str, str] | None:
    """(file name, language) — English first, else the alphabetically first."""
    found = sorted((m.group(1).lower(), n) for n in names if (m := _BDMT_RE.match(n)))
    if not found:
        return None
    for lang, name in found:
        if lang == "eng":
            return name, lang
    lang, name = found[0]
    return name, lang


def _int(text: str | None) -> int | None:
    # Postgres's disc_number/disc_total columns are int4; a malformed BDMT
    # setNumber/numSets must not carry an out-of-range value through to a
    # 500 on commit. 999 is generous for any real box set.
    try:
        value = int((text or "").strip())
    except ValueError:
        return None
    return value if 1 <= value <= 999 else None


def parse_bdmt(xml_bytes: bytes, language: str | None) -> BdDiscMeta | None:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    title = root.find(f".//{_DI}title")
    if title is None:
        return None
    name = (title.findtext(f"{_DI}name") or "").strip()
    if not name:
        return None
    set_number = _int(title.findtext(f"{_DI}setNumber"))
    num_sets = _int(title.findtext(f"{_DI}numSets"))
    if set_number is not None and num_sets is not None and set_number > num_sets:
        set_number = num_sets = None
    return BdDiscMeta(name=name, set_number=set_number, num_sets=num_sets, language=language)


def _read_bdmt(source_path: str) -> tuple[bytes, str] | None:
    from io import BytesIO

    from pycdlib import PyCdlib  # lazy: keep import cost off the hot path

    iso = PyCdlib()
    iso.open(source_path)
    try:
        names = [
            child.file_identifier().decode("utf-8", "replace")
            for child in iso.list_children(udf_path=_META_DIR)
            if child is not None and not child.is_dir()
        ]
        picked = pick_bdmt_file(names)
        if picked is None:
            return None
        name, lang = picked
        buf = BytesIO()
        iso.get_file_from_iso_fp(buf, udf_path=f"{_META_DIR}/{name}")
        return buf.getvalue(), lang
    finally:
        iso.close()


def _read_bdmt_udf(source_path: str) -> tuple[bytes, str] | None:
    """7-Zip fallback for a UDF-only image PyCdlib refuses (no ISO 9660 PVD)."""
    from arm_ripper.scan import udf_image

    files = udf_image.list_files(source_path)
    if not files:
        return None
    prefix = _META_DIR.lstrip("/") + "/"
    names = [path[len(prefix) :] for path, _size in files if path.startswith(prefix) and "/" not in path[len(prefix) :]]
    picked = pick_bdmt_file(names)
    if picked is None:
        return None
    name, lang = picked
    data = udf_image.read_file(source_path, f"{prefix}{name}")
    if data is None:
        return None
    return data, lang


def probe_bd_meta(source_path: str) -> BdDiscMeta | None:
    """Never raises."""
    try:
        read = _read_bdmt(source_path)
    except Exception as e:  # noqa: BLE001 — pycdlib raises several flavours; no UDF / no META dir
        logger.debug("bdmt probe via pycdlib failed for %s: %s; trying 7z", source_path, e)
        try:
            read = _read_bdmt_udf(source_path)
        except Exception as e2:  # noqa: BLE001
            logger.debug("bdmt probe via 7z failed for %s: %s", source_path, e2)
            return None
    if read is None:
        return None
    data, lang = read
    return parse_bdmt(data, lang)
