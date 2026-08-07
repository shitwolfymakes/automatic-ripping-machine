"""Matcher: duration parse, SourceFile join, map build, track stamping."""
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.thediscdb.matcher import build_map, parse_duration  # noqa: E402
from arm_backend.thediscdb.snapshot import DiscMatch  # noqa: E402
from arm_common.schemas import ScanResult, ScanTitle  # noqa: E402
from arm_common import DiscType  # noqa: E402


def _match(titles: list[dict[str, Any]], kind: str = "movie") -> DiscMatch:
    return DiscMatch(
        kind=kind,
        title_slug="round-midnight-1986",
        release_slug="2022-criterion-blu-ray",
        disc={"ContentHash": "2D61282D8DA5EAC2CA87B451BCE9A055", "Titles": titles},
        metadata={"Title": "Round Midnight", "Year": 1986, "ExternalIds": {"Imdb": "tt0090557", "Tmdb": "14670"}},
        release={"Slug": "2022-criterion-blu-ray"},
    )


def test_parse_duration() -> None:
    assert parse_duration("2:11:34") == 2 * 3600 + 11 * 60 + 34
    assert parse_duration("56:03") == 56 * 60 + 3
    assert parse_duration("") is None
    assert parse_duration("garbage") is None


def test_build_map_joins_by_source_file() -> None:
    match = _match(
        [
            {"SourceFile": "00001.mpls", "Duration": "2:11:34", "Comment": "Main.mkv",
             "Item": {"Title": "Round Midnight", "Type": "MainMovie"}},
            {"SourceFile": "00011.mpls", "Duration": "0:12:00", "Comment": "Making Of.mkv",
             "Item": {"Title": "The Making Of", "Type": "Featurette"}},
        ]
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[
            ScanTitle(index=0, duration_seconds=7894, source_file="00001.mpls"),
            ScanTitle(index=1, duration_seconds=720, source_file="00011.mpls"),
            ScanTitle(index=2, duration_seconds=30, source_file="00029.mpls"),  # not in db
        ],
    )
    result = build_map(match, scan)
    assert result["release_slug"] == "2022-criterion-blu-ray"
    assert result["matched"]["0"] == {
        "type": "MainMovie", "title": "Round Midnight", "season": None, "episode": None,
        "filename": "Main.mkv",
    }
    assert result["matched"]["1"]["type"] == "Featurette"
    assert "2" not in result["matched"]  # unmatched scan title untouched


def test_build_map_series_episode_fields() -> None:
    match = _match(
        [{"SourceFile": "00800.mpls", "Duration": "1:06:55", "Comment": "1883 S01E01.mkv",
          "Item": {"Title": "1883", "Type": "Episode", "Season": "1", "Episode": "1"}}],
        kind="series",
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[ScanTitle(index=5, duration_seconds=4015, source_file="00800.mpls")],
    )
    result = build_map(match, scan)
    assert result["matched"]["5"] == {
        "type": "Episode", "title": "1883", "season": 1, "episode": 1,
        "filename": "1883 S01E01.mkv",
    }


def test_build_map_duration_fallback_when_no_source_file() -> None:
    # DVD scans may lack source_file; duration within ±2s joins.
    match = _match(
        [{"SourceFile": "VTS_01_1.VOB", "Duration": "1:30:00", "Comment": "Movie.mkv",
          "Item": {"Title": "Movie", "Type": "MainMovie"}}]
    )
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=0, duration_seconds=5401, source_file=None)],
    )
    result = build_map(match, scan)
    assert result["matched"]["0"]["type"] == "MainMovie"


def test_build_map_ambiguous_duration_no_join() -> None:
    # Two scan titles inside the window and no source_file -> ambiguous, skip.
    match = _match(
        [{"SourceFile": "VTS_01_1.VOB", "Duration": "1:30:00", "Comment": "Movie.mkv",
          "Item": {"Title": "Movie", "Type": "MainMovie"}}]
    )
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[
            ScanTitle(index=0, duration_seconds=5400, source_file=None),
            ScanTitle(index=1, duration_seconds=5401, source_file=None),
        ],
    )
    assert build_map(match, scan)["matched"] == {}
