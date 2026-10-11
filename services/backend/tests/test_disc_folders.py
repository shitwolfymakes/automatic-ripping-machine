"""Finding disc folders (a BDMV or VIDEO_TS tree at their root) anywhere in
the ISO library, for "Rip from folder"."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend import disc_folders  # noqa: E402


def _disc(root: Path, rel: str, video_dir: str = "BDMV") -> Path:
    d = root / rel
    (d / video_dir / "STREAM").mkdir(parents=True)
    return d


def test_finds_disc_folders_at_any_depth_sorted_by_path(tmp_path: Path) -> None:
    _disc(tmp_path, "Movies/Fantasy/MirrorMask (2005)")
    _disc(tmp_path, "Lord of the Rings/Extended/Fellowship/Disc 2")
    _disc(tmp_path, "Lord of the Rings/Extended/Fellowship/Disc 1")
    _disc(tmp_path, "Comedy/1998/Half Baked", "VIDEO_TS")
    (tmp_path / "Movies" / "notes").mkdir()
    (tmp_path / "loose.iso").write_bytes(b"x")

    found, partial = disc_folders.find(tmp_path)

    assert [(f.path, f.disc_type) for f in found] == [
        ("Comedy/1998/Half Baked", "dvd"),
        ("Lord of the Rings/Extended/Fellowship/Disc 1", "bluray"),
        ("Lord of the Rings/Extended/Fellowship/Disc 2", "bluray"),
        ("Movies/Fantasy/MirrorMask (2005)", "bluray"),
    ]
    assert partial is False


def test_the_library_root_itself_can_be_a_disc_folder_only_below_it(tmp_path: Path) -> None:
    """A disc folder is something inside the library, never the library."""
    (tmp_path / "BDMV").mkdir()
    assert disc_folders.find(tmp_path) == ([], False)


def test_never_walks_into_a_disc_folder_or_a_hidden_one(tmp_path: Path) -> None:
    outer = _disc(tmp_path, "Outer")
    _disc(outer, "BDMV/BACKUP/Nested")  # inside a disc tree: not a separate disc
    _disc(tmp_path, ".snapshot/Old")

    found, _ = disc_folders.find(tmp_path)

    assert [f.path for f in found] == ["Outer"]


def test_stops_at_the_depth_limit(tmp_path: Path) -> None:
    _disc(tmp_path, "a/b/c")
    _disc(tmp_path, "1/2/3/4/5/6/7/8/9")  # the disc folder is 9 levels down

    found, partial = disc_folders.find(tmp_path, max_depth=8)

    assert [f.path for f in found] == ["a/b/c"]
    assert partial is False  # a depth limit is a rule, not a truncated listing


def test_reports_a_partial_listing_when_the_folder_budget_runs_out(tmp_path: Path) -> None:
    for i in range(20):
        (tmp_path / f"empty{i:02}").mkdir()
    _disc(tmp_path, "zz/Last")

    found, partial = disc_folders.find(tmp_path, max_dirs=5)

    assert partial is True
    assert found == []


def test_an_unreadable_folder_is_skipped(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _disc(tmp_path, "ok/Disc")
    (tmp_path / "locked").mkdir()
    real = os.scandir

    def _scandir(p):  # type: ignore[no-untyped-def]
        if str(p).endswith("locked"):
            raise PermissionError(p)
        return real(p)

    monkeypatch.setattr(disc_folders.os, "scandir", _scandir)
    found, _ = disc_folders.find(tmp_path)
    assert [f.path for f in found] == ["ok/Disc"]


def test_disc_type_of_a_folder(tmp_path: Path) -> None:
    assert disc_folders.disc_type(_disc(tmp_path, "bd")) == "bluray"
    assert disc_folders.disc_type(_disc(tmp_path, "dvd", "VIDEO_TS")) == "dvd"
    (tmp_path / "plain").mkdir()
    assert disc_folders.disc_type(tmp_path / "plain") is None
