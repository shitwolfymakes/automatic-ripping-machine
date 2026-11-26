"""matrix256 fingerprint coverage. The digest math belongs to the reference
`matrix256` library (a runtime dependency) and is not re-tested here; what
this suite covers is ARM's side of the contract: the sparse-skeleton
materialization that turns pycdlib (path, size) records into the mounted-root
input the library expects, pycdlib view selection and tree collection against
a stub image, and the probe's soft-fail behavior."""

import logging
from pathlib import Path
from typing import Any
from unittest import mock

import pycdlib
import pytest

from arm_ripper.scan import matrix256_fp
from arm_ripper.scan.matrix256_fp import (
    UnsafeRecordError,
    _choose_view,
    _collect_from_iso,
    _collect_records,
    _hashed_path,
    collect_tree_records,
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


def _victim(tmp_path: Path) -> Path:
    victim = tmp_path / "title_t00.mkv"
    victim.write_bytes(b"x" * 1000)
    return victim


def _escaping(target: Path) -> str:
    # Enough `..` to reach `/` from wherever the temp root lives.
    return "../" * 64 + str(target).lstrip("/")


def test_dotdot_record_cannot_escape_the_skeleton(tmp_path: Path) -> None:
    """A disc-supplied `..` name must not truncate a file outside the
    skeleton root (the defect's PoC)."""
    victim = _victim(tmp_path)
    with pytest.raises(UnsafeRecordError):
        fingerprint_records([(_escaping(victim), 0), ("BDMV/index.bdmv", 5)])
    assert victim.read_bytes() == b"x" * 1000


def test_absolute_record_cannot_escape_the_skeleton(tmp_path: Path) -> None:
    # `root / "/abs"` discards root, so an absolute name is an escape too.
    victim = _victim(tmp_path)
    with pytest.raises(UnsafeRecordError):
        fingerprint_records([(str(victim), 0)])
    assert victim.read_bytes() == b"x" * 1000


def test_escaping_record_creates_no_directories(tmp_path: Path) -> None:
    # The check runs before mkdir, so no directory appears outside the root.
    with pytest.raises(UnsafeRecordError):
        fingerprint_records([(_escaping(tmp_path / "escaped" / "x"), 1)])
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("relative", ["", ".", "a/.."])
def test_record_naming_the_root_is_rejected(relative: str) -> None:
    with pytest.raises(UnsafeRecordError):
        fingerprint_records([(relative, 1)])


@pytest.mark.parametrize("relative", ["A/../X", "./X", "A/./X", "A//X", "A/X/"])
def test_record_that_is_not_plain_is_rejected_not_normalized(relative: str) -> None:
    # Normalizing would collapse it onto `X`/`A/X` and hash two disc files as one.
    with pytest.raises(UnsafeRecordError, match="not a plain relative path"):
        fingerprint_records([(relative, 1), ("X", 2)])


def test_containment_failure_is_an_unsafe_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # A plain name that still resolves outside (e.g. through a symlink) is
    # refused the same way, so the probe logs it as hostile too.
    def _escapes(_root: Path, relative: str) -> Path:
        raise ValueError(f"path {relative!r} escapes")

    monkeypatch.setattr(matrix256_fp, "safe_join", _escapes)
    with pytest.raises(UnsafeRecordError, match="escapes"):
        fingerprint_records([("BDMV/index.bdmv", 1)])


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


def test_probe_soft_fails_on_reader_error(caplog: pytest.LogCaptureFixture) -> None:
    # An unreadable disc is routine: no fingerprint, and nothing above DEBUG.
    caplog.set_level(logging.DEBUG, logger=matrix256_fp.__name__)
    with mock.patch.object(matrix256_fp, "collect_tree_records", side_effect=OSError("boom")):
        assert probe_matrix256("/dev/sr0") is None
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]


def test_probe_soft_fails_on_unmaterializable_record() -> None:
    # A record the skeleton cannot create (component over NAME_MAX) raises
    # OSError inside fingerprint_records; the probe soft-fails to None.
    records = [("x" * 4096, 1)]
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=(records, "udf")):
        assert probe_matrix256("/dev/sr0") is None


def test_probe_soft_fails_on_escaping_record(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # A hostile tree yields no fingerprint, leaves the file it named
    # untouched, and is refused by the record check (the WARNING), not by
    # some unrelated failure on the way there.
    victim = _victim(tmp_path)
    records = [(_escaping(victim), 0), ("BDMV/index.bdmv", 5)]
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=(records, "udf")):
        assert probe_matrix256("/dev/sr0") is None
    assert victim.read_bytes() == b"x" * 1000
    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "hostile disc tree" in warning.getMessage()


# --- _choose_view ------------------------------------------------------------


class _RaisingIso(_StubIso):
    """A stub whose named `has_*` checks raise, as a broken descriptor would."""

    def __init__(self, *broken: str, **flags: bool) -> None:
        super().__init__("iso_path", [], {}, **flags)
        self._broken = broken

    def has_udf(self) -> bool:
        if "udf" in self._broken:
            raise OSError("bad udf descriptor")
        return super().has_udf()

    def has_rock_ridge(self) -> bool:
        if "rock_ridge" in self._broken:
            raise OSError("bad rr descriptor")
        return super().has_rock_ridge()

    def has_joliet(self) -> bool:
        if "joliet" in self._broken:
            raise OSError("bad joliet descriptor")
        return super().has_joliet()


def test_choose_view_picks_joliet_when_it_is_the_only_extended_view() -> None:
    assert _choose_view(_StubIso("joliet_path", [], {}, joliet=True)) == ("joliet", "joliet_path")


def test_choose_view_skips_a_raising_check_and_tries_the_next_view() -> None:
    iso = _RaisingIso("udf", rock_ridge=True)
    assert _choose_view(iso) == ("rock_ridge", "rr_path")


def test_choose_view_falls_back_to_plain_iso9660_when_no_extension_is_present() -> None:
    assert _choose_view(_StubIso("iso_path", [], {})) == ("iso9660", "iso_path")


def test_choose_view_falls_back_to_iso9660_when_every_extended_check_raises() -> None:
    assert _choose_view(_RaisingIso("udf", "rock_ridge", "joliet")) == ("iso9660", "iso_path")


def test_choose_view_prefers_udf_over_every_other_view() -> None:
    iso = _StubIso("udf_path", [], {}, udf=True, rock_ridge=True, joliet=True)
    assert _choose_view(iso) == ("udf", "udf_path")


def test_choose_view_prefers_rock_ridge_over_joliet() -> None:
    iso = _StubIso("rr_path", [], {}, rock_ridge=True, joliet=True)
    assert _choose_view(iso) == ("rock_ridge", "rr_path")


def test_choose_view_treats_a_falsy_non_bool_check_as_absent() -> None:
    class _FalsyIso:
        def has_udf(self) -> int:
            return 0

        def has_rock_ridge(self) -> None:
            return None

        def has_joliet(self) -> str:
            return ""

    assert _choose_view(_FalsyIso()) == ("iso9660", "iso_path")


def test_collect_tree_records_opens_walks_and_closes_the_image(monkeypatch: pytest.MonkeyPatch) -> None:
    class _OpenableIso(_StubIso):
        instances: list["_OpenableIso"] = []

        def __init__(self) -> None:
            super().__init__("iso_path", [("/", [], ["A.TXT;1"])], {"/A.TXT;1": _Rec(7)})
            self.opened: str | None = None
            self.closed = 0
            _OpenableIso.instances.append(self)

        def open(self, path: str) -> None:
            self.opened = path

        def close(self) -> None:
            self.closed += 1

    monkeypatch.setattr(pycdlib, "PyCdlib", _OpenableIso)
    assert collect_tree_records("/dev/sr0") == ([("A.TXT", 7)], "iso9660")
    [iso] = _OpenableIso.instances
    assert iso.opened == "/dev/sr0"
    assert iso.closed == 1


def test_hashed_path_iso9660_strips_version_suffix_and_leading_slash() -> None:
    assert _hashed_path("/VIDEO_TS/VTS_01_1.VOB;1", "iso9660") == "VIDEO_TS/VTS_01_1.VOB"


@pytest.mark.parametrize("view", ["udf", "joliet", "rock_ridge"])
def test_hashed_path_extended_views_keep_a_semicolon_in_the_name(view: str) -> None:
    assert _hashed_path("/dir/a;b.txt", view) == "dir/a;b.txt"


def test_hashed_path_without_leading_slash_passes_through() -> None:
    assert _hashed_path("dir/a.txt", "udf") == "dir/a.txt"


def test_collect_records_returns_pycdlib_result_without_calling_7zip(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.scan import udf_image

    def _boom(_path: str) -> list[tuple[str, int]]:
        raise AssertionError("7-Zip must not run when pycdlib succeeds")

    monkeypatch.setattr(udf_image, "list_files", _boom)
    with mock.patch.object(matrix256_fp, "collect_tree_records", return_value=([("a", 1)], "udf")):
        assert _collect_records("/dev/sr0") == ([("a", 1)], "udf")


def test_collect_records_falls_back_to_7zip_listing_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from arm_ripper.scan import udf_image

    monkeypatch.setattr(udf_image, "list_files", lambda _path: [("b", 2)])
    with (
        mock.patch.object(matrix256_fp, "collect_tree_records", side_effect=OSError("no PVD")),
        caplog.at_level(logging.DEBUG, logger=matrix256_fp.logger.name),
    ):
        assert _collect_records("/dev/sr0") == ([("b", 2)], "udf-7z")
    assert [r.getMessage() for r in caplog.records] == ["matrix256 pycdlib walk failed for /dev/sr0: no PVD; trying 7z"]


def test_collect_records_none_when_7zip_lists_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.scan import udf_image

    monkeypatch.setattr(udf_image, "list_files", lambda _path: [])
    with mock.patch.object(matrix256_fp, "collect_tree_records", side_effect=OSError("no PVD")):
        assert _collect_records("/dev/sr0") is None


def test_collect_records_propagates_a_7zip_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.scan import udf_image

    def _fail(_path: str) -> list[tuple[str, int]]:
        raise RuntimeError("7z failed")

    monkeypatch.setattr(udf_image, "list_files", _fail)
    with (
        mock.patch.object(matrix256_fp, "collect_tree_records", side_effect=OSError("no PVD")),
        pytest.raises(RuntimeError, match="7z failed"),
    ):
        _collect_records("/dev/sr0")
