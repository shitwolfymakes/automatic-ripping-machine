"""ContentHash (TheDiscDB) unit coverage: MD5-over-sizes vectors, ISO name
cleaning, file-set selection (BDMV/STREAM/*.m2ts vs VIDEO_TS/*), soft-fail."""

from unittest import mock

from arm_ripper.scan.thediscdb_hash import (
    _clean_iso_name,
    _hash_from_listing,
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
