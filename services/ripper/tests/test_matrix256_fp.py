"""matrix256 fingerprint coverage. The digest math belongs to the reference
`matrix256` library (a runtime dependency) and is not re-tested here; what
this suite covers is ARM's side of the contract: the sparse-skeleton
materialization that turns pycdlib (path, size) records into the mounted-root
input the library expects, pycdlib view selection and tree collection against
a stub image, and the probe's soft-fail behavior."""

from pathlib import Path
from typing import Any
from unittest import mock

from arm_ripper.scan import matrix256_fp
from arm_ripper.scan.matrix256_fp import (
    _collect_from_iso,
    fingerprint_records,
    probe_matrix256,
)

# --- skeleton materialization ------------------------------------------------


def test_records_digest_matches_reference_on_real_tree(tmp_path: Path) -> None:
    """The skeleton path must be invisible in the digest: fingerprinting
    records through the sparse skeleton equals the library fingerprinting an
    equivalent real tree — including a symlink the library skips and the
    pycdlib collector never emits."""
    from matrix256 import v1

    records: list[tuple[str, int]] = [
        ("BDMV/STREAM/00001.m2ts", 4096),
        ("BDMV/index.bdmv", 0),  # empty file
        ("édition/notes.txt", 11),  # non-ASCII directory name
        ("Z.txt", 1),
        ("a.txt", 2),
    ]
    for rel, size in records:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\x00" * size)
    (tmp_path / "link.txt").symlink_to(tmp_path / "a.txt")

    assert fingerprint_records(records) == v1.fingerprint(tmp_path)


def test_sparse_sizes_hash_without_disk_cost() -> None:
    """Disc-scale sizes (a 30 GB m2ts) materialize as sparse files: st_size
    is exact, no bytes are written, and the digest is order-independent."""
    records = [("BDMV/STREAM/00800.m2ts", 30_000_000_000), ("BDMV/index.bdmv", 4096)]
    assert fingerprint_records(records) == fingerprint_records(list(reversed(records)))


def test_surrogate_escaped_name_round_trips() -> None:
    """An undecodable name byte (surrogateescape'd by the reader) must
    materialize and hash, not raise — the library maps lone surrogates to
    U+FFFD per spec §2.2."""
    assert fingerprint_records([("bad\udc80name", 3)]) == fingerprint_records([("bad�name", 3)])


# --- pycdlib view selection and collection (stub image) ----------------------


class _Rec:
    def __init__(self, size: int, symlink: bool = False) -> None:
        self._size = size
        self._symlink = symlink

    def get_data_length(self) -> int:
        return self._size

    def is_symlink(self) -> bool:
        return self._symlink


class _StubIso:
    """Minimal pycdlib stand-in: one namespace's walk() + get_record()."""

    def __init__(
        self,
        key: str,
        tree: list[tuple[str, list[str], list[str]]],
        files: dict[str, _Rec],
        *,
        udf: bool = False,
        rock_ridge: bool = False,
        joliet: bool = False,
    ) -> None:
        self._key = key
        self._tree = tree
        self._files = files
        self._udf = udf
        self._rr = rock_ridge
        self._joliet = joliet

    def has_udf(self) -> bool:
        return self._udf

    def has_rock_ridge(self) -> bool:
        return self._rr

    def has_joliet(self) -> bool:
        return self._joliet

    def walk(self, **kwargs: Any) -> Any:
        assert list(kwargs) == [self._key], f"walked wrong namespace: {kwargs}"
        yield from self._tree

    def get_record(self, **kwargs: Any) -> _Rec:
        assert list(kwargs) == [self._key]
        return self._files[kwargs[self._key]]


def test_collect_prefers_udf_and_joins_paths() -> None:
    iso = _StubIso(
        "udf_path",
        [("/", ["BDMV"], []), ("/BDMV", ["STREAM"], ["index.bdmv"]), ("/BDMV/STREAM", [], ["00001.m2ts"])],
        {"/BDMV/index.bdmv": _Rec(10), "/BDMV/STREAM/00001.m2ts": _Rec(20)},
        udf=True,
        joliet=True,  # UDF must win over Joliet
    )
    collected = _collect_from_iso(iso)
    assert collected is not None
    records, view = collected
    assert view == "udf"
    assert sorted(records) == [("BDMV/STREAM/00001.m2ts", 20), ("BDMV/index.bdmv", 10)]


def test_collect_skips_symlinks() -> None:
    iso = _StubIso(
        "rr_path",
        [("/", [], ["real.bin", "link.bin"])],
        {"/real.bin": _Rec(5), "/link.bin": _Rec(5, symlink=True)},
        rock_ridge=True,
    )
    collected = _collect_from_iso(iso)
    assert collected is not None
    records, view = collected
    assert view == "rock_ridge"
    assert records == [("real.bin", 5)]


def test_collect_bare_iso9660_strips_version_suffix() -> None:
    iso = _StubIso(
        "iso_path",
        [("/", ["VIDEO_TS"], []), ("/VIDEO_TS", [], ["VTS_01_1.VOB;1"])],
        {"/VIDEO_TS/VTS_01_1.VOB;1": _Rec(42)},
    )
    collected = _collect_from_iso(iso)
    assert collected is not None
    records, view = collected
    assert view == "iso9660"
    assert records == [("VIDEO_TS/VTS_01_1.VOB", 42)]


# --- probe soft-fail ---------------------------------------------------------


def test_probe_happy_path() -> None:
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=([("a.txt", 1)], "udf")):
        assert probe_matrix256("/dev/sr0") == fingerprint_records([("a.txt", 1)])


def test_probe_empty_tree_none() -> None:
    # Never emit the digest-of-nothing: all empty/unreadable discs would collide.
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=([], "udf")):
        assert probe_matrix256("/dev/sr0") is None


def test_probe_no_walkable_view_none() -> None:
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=None):
        assert probe_matrix256("/dev/sr0") is None


def test_probe_soft_fails_on_reader_error() -> None:
    with mock.patch.object(matrix256_fp, "collect_tree_records", side_effect=OSError("boom")):
        assert probe_matrix256("/dev/sr0") is None


def test_probe_soft_fails_on_unmaterializable_record() -> None:
    # A record the skeleton cannot create (component over NAME_MAX) raises
    # OSError inside fingerprint_records; the probe soft-fails to None.
    records = [("x" * 4096, 1)]
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=(records, "udf")):
        assert probe_matrix256("/dev/sr0") is None
