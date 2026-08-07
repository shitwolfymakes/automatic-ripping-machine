"""Snapshot index: tarball -> sqlite build, lookup, atomic replace."""
from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from arm_backend.thediscdb.snapshot import SnapshotStore, build_index

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
    assert not dest.with_suffix(".sqlite.new").exists()


def test_missing_store(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "nope")
    assert not store.exists()
    assert store.lookup("2D61282D8DA5EAC2CA87B451BCE9A055") is None
    assert store.count() == 0
