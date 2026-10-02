"""Incomplete-ISO detection: an image file shorter than the size its own file
system declares (a copy or download that stopped partway) is refused when
an ISO rip is created, instead of after a long unpack and scan."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend import iso_image  # noqa: E402

SECTOR = 2048
GB = 1024**3


def _tag(ident: int) -> bytes:
    return ident.to_bytes(2, "little") + b"\0" * 14


def udf_image(path: Path, *, declared_bytes: int, file_bytes: int) -> Path:
    """A sparse image whose UDF partition ends at `declared_bytes`: anchor at
    sector 256 -> volume descriptor sequence at sector 32 holding a partition
    descriptor (tag 5) and a terminator (tag 8)."""
    start = 288
    length = declared_bytes // SECTOR - start
    with open(path, "wb") as f:
        f.truncate(file_bytes)
        avdp = bytearray(_tag(2) + (2 * SECTOR).to_bytes(4, "little") + (32).to_bytes(4, "little"))
        f.seek(256 * SECTOR)
        f.write(avdp)
        pd = bytearray(SECTOR)
        pd[0:16] = _tag(5)
        pd[188:192] = start.to_bytes(4, "little")
        pd[192:196] = length.to_bytes(4, "little")
        f.seek(32 * SECTOR)
        f.write(pd)
        f.seek(33 * SECTOR)
        f.write(_tag(8))
    return path


def iso9660_image(path: Path, *, declared_bytes: int, file_bytes: int) -> Path:
    with open(path, "wb") as f:
        f.truncate(file_bytes)
        pvd = bytearray(SECTOR)
        pvd[0] = 1
        pvd[1:6] = b"CD001"
        blocks = declared_bytes // SECTOR
        pvd[80:84] = blocks.to_bytes(4, "little")
        pvd[84:88] = blocks.to_bytes(4, "big")
        pvd[128:130] = SECTOR.to_bytes(2, "little")
        pvd[130:132] = SECTOR.to_bytes(2, "big")
        f.seek(16 * SECTOR)
        f.write(pvd)
    return path


def test_a_udf_image_cut_off_partway_is_incomplete(tmp_path: Path) -> None:
    """The MirrorMask case: a 32 GB BD-50 partition in a 13.8 GB file."""
    img = udf_image(tmp_path / "m.iso", declared_bytes=32 * GB, file_bytes=13 * GB)
    t = iso_image.truncation(img)
    assert t is not None
    assert (t.present_bytes, t.declared_bytes) == (13 * GB, 32 * GB)


def test_a_complete_udf_image_is_fine(tmp_path: Path) -> None:
    # A real image ends with the closing anchor after its partition, so the
    # file is a little longer than the partition end.
    img = udf_image(tmp_path / "ok.iso", declared_bytes=20 * GB, file_bytes=20 * GB + 256 * SECTOR)
    assert iso_image.truncation(img) is None


def test_an_iso9660_image_cut_off_partway_is_incomplete(tmp_path: Path) -> None:
    img = iso9660_image(tmp_path / "dvd.iso", declared_bytes=8 * GB, file_bytes=4 * GB)
    t = iso_image.truncation(img)
    assert t is not None and t.declared_bytes == 8 * GB


def test_a_tiny_shortfall_is_tolerated(tmp_path: Path) -> None:
    """Some tools trim trailing padding; only a real gap counts."""
    img = udf_image(tmp_path / "trim.iso", declared_bytes=20 * GB, file_bytes=20 * GB - 4 * 1024**2)
    assert iso_image.truncation(img) is None


def test_an_image_without_readable_descriptors_is_not_judged(tmp_path: Path) -> None:
    """Unknown layout, or a file too short to hold the descriptors: fail open
    and let the rip try, as before."""
    blank = tmp_path / "blank.iso"
    blank.write_bytes(b"\0" * 300 * SECTOR)
    tiny = tmp_path / "tiny.iso"
    tiny.write_bytes(b"x")
    assert iso_image.truncation(blank) is None
    assert iso_image.truncation(tiny) is None
    assert iso_image.truncation(tmp_path / "missing.iso") is None


def test_the_message_names_both_sizes() -> None:
    t = iso_image.Truncation(present_bytes=13_794_123_776, declared_bytes=32_001_687_552)
    assert t.message() == (
        "This ISO is incomplete: 13.8 GB of 32.0 GB is present (the copy or download stopped partway). "
        "Copy or download it again, then rip it."
    )


def test_an_anchor_pointing_past_the_end_of_the_file_is_not_judged(tmp_path: Path) -> None:
    img = tmp_path / "odd.iso"
    with open(img, "wb") as f:
        f.truncate(300 * SECTOR)
        f.seek(256 * SECTOR)
        f.write(_tag(2) + (2 * SECTOR).to_bytes(4, "little") + (10_000).to_bytes(4, "little"))
    assert iso_image.truncation(img) is None


def test_a_file_that_vanishes_mid_check_is_not_judged(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    img = udf_image(tmp_path / "m.iso", declared_bytes=32 * GB, file_bytes=13 * GB)

    def _gone(_p: object) -> int:
        raise FileNotFoundError(str(_p))

    monkeypatch.setattr(iso_image.os.path, "getsize", _gone)
    assert iso_image.truncation(img) is None
