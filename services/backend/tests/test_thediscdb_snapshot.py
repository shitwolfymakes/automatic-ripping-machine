"""Snapshot index: tarball -> sqlite build, lookup, atomic replace."""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path

import httpx
import pytest

from arm_backend.identity.sources import thediscdb_snapshot
from arm_backend.identity.sources.thediscdb_snapshot import TARBALL_URL, SnapshotStore, build_index, refresh

DISC = {
    "Index": 1,
    "Slug": "blu-ray",
    "Format": "Blu-Ray",
    "ContentHash": "2D61282D8DA5EAC2CA87B451BCE9A055",
    "GlobalDiscId": "BDE5486DBE5FA6E7B9D66485CB9AA774C527D8EE",
    "Titles": [
        {
            "Index": 0,
            "Comment": "Main.mkv",
            "SourceFile": "00001.mpls",
            "Duration": "2:11:34",
            "Item": {"Title": "Round Midnight", "Type": "MainMovie"},
        }
    ],
}
METADATA = {"Title": "Round Midnight", "Year": 1986, "ExternalIds": {"Tmdb": "14670", "Imdb": "tt0090557"}}
RELEASE = {"Slug": "2022-criterion-blu-ray", "Title": "Criterion Blu-ray"}


def _mini_tarball(path: Path) -> Path:
    """data-main/data/movie/<title>/<release>/disc01.json + siblings."""
    tar_path = path / "data.tar.gz"
    base = "data-main/data/movie/Round Midnight (1986)"
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, obj in [
            (f"{base}/metadata.json", METADATA),
            (f"{base}/2022-criterion-blu-ray/release.json", RELEASE),
            (f"{base}/2022-criterion-blu-ray/disc01.json", DISC),
        ]:
            raw = json.dumps(obj).encode()
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return tar_path


def test_build_and_lookup(tmp_path: Path) -> None:
    tarball = _mini_tarball(tmp_path)
    dest = tmp_path / "index.sqlite"
    count = build_index(tarball, dest)
    assert count == 1
    store = SnapshotStore(tmp_path)
    assert store.exists()
    assert store.count() == 1
    hit = store.lookup("2D61282D8DA5EAC2CA87B451BCE9A055")
    assert hit is not None
    assert hit.kind == "movie"
    assert hit.metadata["ExternalIds"]["Imdb"] == "tt0090557"
    assert hit.disc["Titles"][0]["SourceFile"] == "00001.mpls"
    assert store.lookup("00000000000000000000000000000000") is None


def test_lookup_is_case_insensitive(tmp_path: Path) -> None:
    build_index(_mini_tarball(tmp_path), tmp_path / "index.sqlite")
    store = SnapshotStore(tmp_path)
    assert store.lookup("2d61282d8da5eac2ca87b451bce9a055") is not None


def test_build_replaces_atomically(tmp_path: Path) -> None:
    dest = tmp_path / "index.sqlite"
    build_index(_mini_tarball(tmp_path), dest)
    before = dest.stat().st_mtime_ns
    build_index(_mini_tarball(tmp_path), dest)  # rebuild over live index
    assert dest.exists() and SnapshotStore(tmp_path).count() == 1
    assert dest.stat().st_mtime_ns != before
    assert not list(tmp_path.glob("index.sqlite.*.new"))


def test_build_failure_removes_temp_file_and_keeps_live_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "index.sqlite"
    build_index(_mini_tarball(tmp_path), dest)

    def _boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(thediscdb_snapshot.os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        build_index(_mini_tarball(tmp_path), dest)
    assert SnapshotStore(tmp_path).count() == 1
    assert not list(tmp_path.glob("index.sqlite.*.new"))


def test_overlapping_builds_use_distinct_temp_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-159: two builds into the same dest must not share a temp path.
    seen: list[Path] = []
    real_write = thediscdb_snapshot._write_index

    def _spy(new_path: Path, *args: object) -> int:
        seen.append(new_path)
        return real_write(new_path, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(thediscdb_snapshot, "_write_index", _spy)
    dest = tmp_path / "index.sqlite"
    build_index(_mini_tarball(tmp_path), dest)
    build_index(_mini_tarball(tmp_path), dest)
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(p.parent == tmp_path for p in seen)


def test_missing_store(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "nope")
    assert not store.exists()
    assert store.lookup("2D61282D8DA5EAC2CA87B451BCE9A055") is None
    assert store.count() == 0


def test_empty_tarball_refuses_to_replace(tmp_path: Path) -> None:
    # Build a populated index first
    dest = tmp_path / "index.sqlite"
    build_index(_mini_tarball(tmp_path), dest)
    assert SnapshotStore(tmp_path).count() == 1

    # Create a tarball with no disc entries (unrelated JSON)
    empty_tar = tmp_path / "empty.tar.gz"
    with tarfile.open(empty_tar, "w:gz") as tar:
        raw = json.dumps({"unrelated": "data"}).encode()
        info = tarfile.TarInfo("unrelated.json")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))

    # Attempt to rebuild with empty tarball should raise
    try:
        build_index(empty_tar, dest)
        assert False, "Expected ValueError for empty disc tarball"
    except ValueError as e:
        assert "no indexable discs" in str(e)

    # Verify live index unchanged and no .new leftover
    assert SnapshotStore(tmp_path).count() == 1
    assert not list(tmp_path.glob("index.sqlite.*.new"))


# --- build_index: member filtering and malformed entries ----------------------


def _custom_tarball(path: Path, members: list[tuple[str, bytes | None]]) -> Path:
    """Arbitrary members; `None` content adds a directory entry."""
    tar_path = path / "custom.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, raw in members:
            info = tarfile.TarInfo(name)
            if raw is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
    return tar_path


def test_build_skips_non_json_dirs_and_malformed_discs(tmp_path: Path) -> None:
    base = "data-main/data/movie/Round Midnight (1986)/2022-criterion-blu-ray"
    tarball = _custom_tarball(
        tmp_path,
        [
            ("data-main/data/movie", None),  # directory entry
            ("data-main/README.md", b"# not json"),  # non-.json file
            (f"{base}/disc01.json", b"{not valid json"),  # malformed → skipped
            (f"{base}/disc02.json", json.dumps(DISC).encode()),
        ],
    )
    assert build_index(tarball, tmp_path / "index.sqlite") == 1
    assert SnapshotStore(tmp_path).lookup(str(DISC["ContentHash"])) is not None


def test_build_treats_unextractable_member_as_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # extractfile() returns None for members that aren't regular files; with
    # every disc unreadable the build must refuse to replace the index.
    monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda self, member: None)
    with pytest.raises(ValueError, match="no indexable discs"):
        build_index(_mini_tarball(tmp_path), tmp_path / "index.sqlite")


def test_store_path_property(tmp_path: Path) -> None:
    assert SnapshotStore(tmp_path).path == tmp_path / "index.sqlite"


# --- refresh: download → build, failure keeps the previous index --------------


async def test_refresh_downloads_tarball_and_builds_index(tmp_path: Path) -> None:
    payload = _mini_tarball(tmp_path).read_bytes()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=payload)

    store_dir = tmp_path / "store"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        count = await refresh(http, store_dir)

    assert count == 1
    assert seen == [TARBALL_URL]
    assert SnapshotStore(store_dir).count() == 1


async def test_refresh_http_failure_propagates_and_keeps_index_absent(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    store_dir = tmp_path / "store"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await refresh(http, store_dir)

    assert not SnapshotStore(store_dir).exists()


async def test_concurrent_refreshes_are_serialised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-159: a second refresh is refused at once instead of building alongside
    the first, or queueing behind it."""
    active = 0
    peak = 0
    running_during: list[bool] = []

    async def _fake_locked(http: object, dir_path: Path) -> int:
        nonlocal active, peak
        running_during.append(thediscdb_snapshot.refresh_running())
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1

    monkeypatch.setattr(thediscdb_snapshot, "_refresh_locked", _fake_locked)
    assert not thediscdb_snapshot.refresh_running()
    results = await asyncio.gather(
        refresh(object(), tmp_path),  # type: ignore[arg-type]
        refresh(object(), tmp_path),  # type: ignore[arg-type]
        return_exceptions=True,
    )
    assert results[0] == 1
    assert isinstance(results[1], thediscdb_snapshot.RefreshBusy)
    assert peak == 1
    assert running_during == [True]
    assert not thediscdb_snapshot.refresh_running()


def _series_disc(index: int, season: str, hash_: str) -> dict:
    return {
        "Index": index,
        "ContentHash": hash_,
        "Titles": [
            {
                "SourceFile": "00001.mpls",
                "Duration": "0:45:00",
                "Item": {"Type": "Episode", "Season": season, "Episode": "1"},
            },
            {"SourceFile": "00002.mpls", "Duration": "0:10:00", "Item": {"Type": "Extra"}},
        ],
    }


DISC_S1 = _series_disc(1, "1", "A" * 32)
DISC_S2 = _series_disc(2, "2", "B" * 32)


def _series_tarball(path: Path, discs: list[tuple[str, dict]]) -> Path:
    tar_path = path / "data.tar.gz"
    base = "data-main/data/series/Some Show (2020)"
    with tarfile.open(tar_path, "w:gz") as tar:
        for i, (release_dir, disc) in enumerate(discs):
            raw = json.dumps(disc).encode()
            info = tarfile.TarInfo(f"{base}/{release_dir}/disc{i + 1:02d}.json")
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return tar_path


def test_index_records_the_release_seasons(tmp_path: Path) -> None:
    tarball = _series_tarball(tmp_path, discs=[("season-1-2", DISC_S1), ("season-1-2", DISC_S2)])
    build_index(tarball, tmp_path / "index.sqlite")
    hit = SnapshotStore(tmp_path).lookup(str(DISC_S1["ContentHash"]))
    assert hit is not None and hit.release_seasons == [1, 2]


def test_index_leaves_release_seasons_null_without_episodes(tmp_path: Path) -> None:
    build_index(_mini_tarball(tmp_path), tmp_path / "index.sqlite")
    hit = SnapshotStore(tmp_path).lookup(str(DISC["ContentHash"]))
    assert hit is not None and hit.release_seasons is None


def test_lookup_tolerates_an_index_without_release_seasons(tmp_path: Path) -> None:
    import sqlite3

    build_index(_mini_tarball(tmp_path), tmp_path / "index.sqlite")
    conn = sqlite3.connect(tmp_path / "index.sqlite")
    conn.execute("ALTER TABLE discs DROP COLUMN release_seasons")
    conn.commit()
    conn.close()
    hit = SnapshotStore(tmp_path).lookup(str(DISC["ContentHash"]))
    assert hit is not None and hit.release_seasons is None


def test_index_ignores_episodes_without_a_usable_season(tmp_path: Path) -> None:
    disc = _series_disc(1, "1", "C" * 32)
    disc["Titles"] += [
        {"SourceFile": "00003.mpls", "Item": {"Type": "Episode", "Season": "special"}},
        {"SourceFile": "00004.mpls", "Item": {"Type": "Episode"}},
    ]
    build_index(_series_tarball(tmp_path, discs=[("s1", disc)]), tmp_path / "index.sqlite")
    hit = SnapshotStore(tmp_path).lookup("C" * 32)
    assert hit is not None and hit.release_seasons == [1]
