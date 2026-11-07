"""ContentHash (TheDiscDB) unit coverage: MD5-over-sizes vectors, ISO name
cleaning, file-set selection (BDMV/STREAM/*.m2ts vs VIDEO_TS/*), soft-fail."""

from typing import Any
from unittest import mock

import pycdlib
import pytest

from arm_ripper.scan.thediscdb_hash import (
    _clean_iso_name,
    _file_entry,
    _hash_from_listing,
    collect_hash_files,
    compute_content_hash,
    probe_thediscdb_hash,
)


def test_content_hash_known_vector() -> None:
    # MD5 over 8-byte little-endian sizes, uppercase hex.
    assert compute_content_hash([123, 456789, 9876543210]) == "D9041EE29C567CFF50030C5FD0DDDF68"


def test_content_hash_single_file_vector() -> None:
    assert compute_content_hash([36380633088]) == "51FA3253A72C8BA91430EBA8AA80AB3D"


def test_content_hash_empty_returns_none_marker() -> None:
    # No files -> no hash (never emit the MD5-of-nothing).
    assert compute_content_hash([]) is None


def test_clean_iso_name_strips_version_suffix() -> None:
    assert _clean_iso_name("VTS_01_1.VOB;1") == "VTS_01_1.VOB"
    assert _clean_iso_name("00003.m2ts") == "00003.m2ts"


def test_hash_from_listing_sorts_by_name() -> None:
    # Same files, shuffled input order -> same hash (ordering is by name).
    a = _hash_from_listing([("00002.m2ts", 20), ("00001.m2ts", 10)])
    b = _hash_from_listing([("00001.m2ts", 10), ("00002.m2ts", 20)])
    assert a == b == compute_content_hash([10, 20])


def test_hash_from_listing_bluray_filters_m2ts() -> None:
    # Filtering happens in collect_hash_files; _hash_from_listing hashes
    # exactly what it is given — assert it does NOT filter.
    with_extra = _hash_from_listing([("index.bdmv", 5), ("00001.m2ts", 10)])
    assert with_extra == compute_content_hash([10, 5])  # 00001.m2ts sorts first


def test_probe_soft_fails_on_unreadable_source() -> None:
    with mock.patch(
        "arm_ripper.scan.thediscdb_hash.collect_hash_files",
        side_effect=OSError("boom"),
    ):
        assert probe_thediscdb_hash("/dev/sr0") is None


def test_probe_soft_fails_on_out_of_range_size() -> None:
    # struct.pack("<q", size) raises struct.error for sizes > 2**63-1.
    # probe_thediscdb_hash must catch it and return None (soft-fail).
    with mock.patch(
        "arm_ripper.scan.thediscdb_hash.collect_hash_files",
        return_value=[("huge.m2ts", 2**63)],
    ):
        assert probe_thediscdb_hash("/fake/path") is None


# --- collect_hash_files: pycdlib walk against a fake image -------------------


class _Child:
    def __init__(self, name: str, size: int = 0, *, is_dir: bool = False, dot: bool = False, dotdot: bool = False):
        self._name = name
        self._size = size
        self._dir = is_dir
        self._dot = dot
        self._dotdot = dotdot

    def file_identifier(self) -> bytes:
        return self._name.encode()

    def get_data_length(self) -> int:
        return self._size

    def is_dir(self) -> bool:
        return self._dir

    def is_dot(self) -> bool:
        return self._dot

    def is_dotdot(self) -> bool:
        return self._dotdot


class _FakeCdlib:
    """Answers list_children(<namespace>=<path>) from `listings`; an Exception value is raised."""

    listings: dict[tuple[str, str], Any] = {}
    instances: list["_FakeCdlib"] = []

    def __init__(self) -> None:
        self.opened: str | None = None
        self.closed = 0
        _FakeCdlib.instances.append(self)

    def open(self, path: str) -> None:
        self.opened = path

    def close(self) -> None:
        self.closed += 1

    def list_children(self, **kwargs: str) -> list[_Child | None]:
        ((namespace, path),) = kwargs.items()
        result = self.listings[(namespace, path)]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fake_cdlib(monkeypatch: pytest.MonkeyPatch) -> type[_FakeCdlib]:
    _FakeCdlib.listings = {}
    _FakeCdlib.instances = []
    monkeypatch.setattr(pycdlib, "PyCdlib", _FakeCdlib)
    return _FakeCdlib


_BDMV = ("udf_path", "/BDMV/STREAM")
_ISO_VTS = ("iso_path", "/VIDEO_TS")
_UDF_VTS = ("udf_path", "/VIDEO_TS")


def _dvd_children() -> list[_Child | None]:
    return [
        _Child(".", dot=True, is_dir=True),
        _Child("..", dotdot=True, is_dir=True),
        None,
        _Child("SUBDIR", is_dir=True),
        _Child("VTS_01_1.VOB;1", 300),
        _Child("VIDEO_TS.IFO;1", 40),
    ]


def test_collect_bluray_returns_only_m2ts_files_with_clean_names(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = [
        None,
        _Child("00001.m2ts;1", 111),
        _Child("notes.txt", 5),
        _Child("00002.M2TS", 222),
        _Child("SUB", 9, is_dir=True),
    ]
    assert collect_hash_files("/dev/sr0") == [("00001.m2ts", 111), ("00002.M2TS", 222)]
    assert fake_cdlib.instances[0].opened == "/dev/sr0"


def test_collect_falls_to_dvd_when_bdmv_stream_has_no_m2ts(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = [_Child("readme.txt", 5)]
    fake_cdlib.listings[_ISO_VTS] = _dvd_children()
    assert collect_hash_files("/dev/sr0") == [("VTS_01_1.VOB", 300), ("VIDEO_TS.IFO", 40)]


def test_collect_falls_to_dvd_when_listing_bdmv_raises(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = OSError("no udf")
    fake_cdlib.listings[_ISO_VTS] = _dvd_children()
    assert collect_hash_files("/dev/sr0") == [("VTS_01_1.VOB", 300), ("VIDEO_TS.IFO", 40)]


def test_collect_dvd_via_iso_path_skips_dot_dotdot_dir_and_none(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = OSError("no bdmv")
    fake_cdlib.listings[_ISO_VTS] = _dvd_children()
    result = collect_hash_files("/dev/sr0")
    assert result is not None
    assert [name for name, _ in result] == ["VTS_01_1.VOB", "VIDEO_TS.IFO"]


def test_collect_dvd_via_udf_path_when_iso_path_raises(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = OSError("no bdmv")
    fake_cdlib.listings[_ISO_VTS] = OSError("no iso9660 tree")
    fake_cdlib.listings[_UDF_VTS] = [_Child("VTS_01_0.IFO", 7)]
    assert collect_hash_files("/dev/sr0") == [("VTS_01_0.IFO", 7)]


def test_collect_returns_none_when_no_directory_is_listable(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = OSError("no bdmv")
    fake_cdlib.listings[_ISO_VTS] = OSError("no iso")
    fake_cdlib.listings[_UDF_VTS] = OSError("no udf")
    assert collect_hash_files("/dev/sr0") is None


def test_collect_dvd_with_no_files_returns_empty_list(fake_cdlib: type[_FakeCdlib]) -> None:
    fake_cdlib.listings[_BDMV] = OSError("no bdmv")
    fake_cdlib.listings[_ISO_VTS] = [_Child(".", dot=True, is_dir=True), _Child("..", dotdot=True, is_dir=True)]
    assert collect_hash_files("/dev/sr0") == []


@pytest.mark.parametrize("case", ["bluray", "dvd", "neither"])
def test_collect_always_closes_the_image(fake_cdlib: type[_FakeCdlib], case: str) -> None:
    if case == "bluray":
        fake_cdlib.listings[_BDMV] = [_Child("00001.m2ts", 1)]
    else:
        fake_cdlib.listings[_BDMV] = OSError("no bdmv")
        fake_cdlib.listings[_ISO_VTS] = [_Child("A.VOB", 1)] if case == "dvd" else OSError("x")
        fake_cdlib.listings[_UDF_VTS] = OSError("x")
    collect_hash_files("/dev/sr0")
    assert [inst.closed for inst in fake_cdlib.instances] == [1]


class _RawChild:
    def __init__(self, raw_name: bytes, size: int) -> None:
        self._raw_name = raw_name
        self._size = size

    def file_identifier(self) -> bytes:
        return self._raw_name

    def get_data_length(self) -> int:
        return self._size


def test_file_entry_strips_iso_version_suffix() -> None:
    assert _file_entry(_RawChild(b"00001.M2TS;1", 42)) == ("00001.M2TS", 42)


def test_file_entry_passes_udf_name_through() -> None:
    assert _file_entry(_RawChild(b"00001.m2ts", 7)) == ("00001.m2ts", 7)


def test_file_entry_replaces_undecodable_byte() -> None:
    assert _file_entry(_RawChild(b"bad\xffname", 1)) == ("bad\ufffdname", 1)
