"""Matcher: duration parse, SourceFile join, map build, track stamping."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest

from arm_backend.thediscdb.matcher import apply_map, build_map, external_imdb_id, parse_duration  # noqa: E402
from arm_backend.thediscdb.snapshot import DiscMatch  # noqa: E402
from arm_common import Job, Track  # noqa: E402
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


def test_build_map_duration_fallback_ignores_with_source_file() -> None:
    # Duration fallback only considers scan titles with source_file=None.
    # A scan title WITH a source_file within the duration window must NOT
    # be joined by duration fallback.
    match = _match(
        [{"SourceFile": "VTS_01_1.VOB", "Duration": "1:30:00", "Comment": "Movie.mkv",
          "Item": {"Title": "Movie", "Type": "MainMovie"}}]
    )
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[
            # This has a source_file, so duration fallback should skip it.
            ScanTitle(index=0, duration_seconds=5401, source_file="VTS_02_1.VOB"),
        ],
    )
    result = build_map(match, scan)
    # No join by duration fallback since the title has a source_file.
    assert result["matched"] == {}


def test_build_map_skips_non_dict_title_entry() -> None:
    # Malformed third-party JSON: a non-dict entry in Titles must be skipped,
    # not raise (AttributeError on entry.get would otherwise 500 identify).
    match = _match(
        [
            "not a dict",
            {
                "SourceFile": "00001.mpls",
                "Duration": "2:11:34",
                "Comment": "Main.mkv",
                "Item": {"Title": "Round Midnight", "Type": "MainMovie"},
            },
        ]
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[ScanTitle(index=0, duration_seconds=7894, source_file="00001.mpls")],
    )
    result = build_map(match, scan)
    assert result["matched"]["0"]["type"] == "MainMovie"


def test_build_map_non_dict_item_treated_as_missing() -> None:
    # Item present but not a dict (upstream layout drift) -> treated as {}.
    match = _match(
        [
            {
                "SourceFile": "00001.mpls",
                "Duration": "2:11:34",
                "Comment": "Main.mkv",
                "Item": "also not a dict",
            }
        ]
    )
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        titles=[ScanTitle(index=0, duration_seconds=7894, source_file="00001.mpls")],
    )
    result = build_map(match, scan)
    assert result["matched"]["0"]["type"] == "Unknown"
    assert result["matched"]["0"]["title"] is None


def test_external_imdb_id_returns_id() -> None:
    match = _match([])
    assert external_imdb_id(match) == "tt0090557"


def test_external_imdb_id_malformed_external_ids_returns_none() -> None:
    # ExternalIds as a non-dict (malformed third-party JSON) must not raise.
    match = DiscMatch(
        kind="movie",
        title_slug="x",
        release_slug="y",
        disc={"ContentHash": "X", "Titles": []},
        metadata={"ExternalIds": "garbage"},
        release={},
    )
    assert external_imdb_id(match) is None


class FakeAsyncSession:
    """Minimal fake async session for testing apply_map without a database."""

    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = tracks
        self.added: list[Track] = []

    async def execute(self, query: Any) -> Any:
        """Fake execute that returns scalars."""
        return MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=self.tracks))))

    def add(self, track: Track) -> None:
        """Track added for session."""
        self.added.append(track)

    async def flush(self) -> None:
        """Noop flush."""
        pass


@pytest.mark.asyncio
async def test_apply_map_fills_empty_fields() -> None:
    # apply_map fills empty fields and sets role/role_source.
    track = Track(
        id=1,
        job_id=1,
        source_ref="0",
        role=None,
        role_source=None,
        episode_name=None,
        season=None,
        episode_number=None,
        custom_filename=None,
        excluded=True,
    )
    job = Job(
        id=1,
        metadata_json={
            "thediscdb": {
                "matched": {
                    "0": {
                        "type": "MainMovie",
                        "title": "The Movie",
                        "season": 2,
                        "episode": 5,
                        "filename": "output.mkv",
                    }
                }
            }
        },
    )
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 1
    assert track.role == "MainMovie"
    assert track.role_source == "thediscdb"
    assert track.episode_name == "The Movie"
    assert track.season == 2
    assert track.episode_number == 5
    assert track.custom_filename == "output.mkv"
    assert track.excluded is False  # MainMovie selected


@pytest.mark.asyncio
async def test_apply_map_not_overwrite_preset_fields() -> None:
    # apply_map never overwrites pre-set season/episode_number/episode_name/custom_filename.
    track = Track(
        id=1,
        job_id=1,
        source_ref="0",
        role=None,
        role_source=None,
        episode_name="Original Name",
        season=10,
        episode_number=99,
        custom_filename="original.mkv",
        excluded=False,
    )
    job = Job(
        id=1,
        metadata_json={
            "thediscdb": {
                "matched": {
                    "0": {
                        "type": "Episode",
                        "title": "New Title",
                        "season": 2,
                        "episode": 5,
                        "filename": "new.mkv",
                    }
                }
            }
        },
    )
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 1
    # Preset fields unchanged
    assert track.episode_name == "Original Name"
    assert track.season == 10
    assert track.episode_number == 99
    assert track.custom_filename == "original.mkv"
    # But role and excluded should still update
    assert track.role == "Episode"
    assert track.excluded is False  # Already False, stays False


@pytest.mark.asyncio
async def test_apply_map_malformed_data_no_raise() -> None:
    # apply_map never raises on malformed map data (e.g. "garbage" for season).
    track = Track(
        id=1,
        job_id=1,
        source_ref="0",
        role=None,
        role_source=None,
        episode_name=None,
        season=None,
        episode_number=None,
        custom_filename=None,
        excluded=True,
    )
    job = Job(
        id=1,
        metadata_json={
            "thediscdb": {
                "matched": {
                    "0": {
                        "type": "MainMovie",
                        "title": "The Movie",
                        "season": "garbage",  # Invalid season
                        "episode": "also_garbage",  # Invalid episode
                        "filename": "output.mkv",
                    }
                }
            }
        },
    )
    session = FakeAsyncSession([track])
    # Should not raise; invalid season/episode are skipped
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 1
    assert track.role == "MainMovie"
    assert track.episode_name == "The Movie"
    assert track.season is None  # Not set due to invalid conversion
    assert track.episode_number is None  # Not set due to invalid conversion
    assert track.custom_filename == "output.mkv"


@pytest.mark.asyncio
async def test_apply_map_featurette_not_selected() -> None:
    # apply_map only sets excluded=False for MainMovie/Episode, not Featurette.
    track = Track(
        id=1,
        job_id=1,
        source_ref="0",
        role=None,
        role_source=None,
        episode_name=None,
        season=None,
        episode_number=None,
        custom_filename=None,
        excluded=True,
    )
    job = Job(
        id=1,
        metadata_json={
            "thediscdb": {
                "matched": {
                    "0": {
                        "type": "Featurette",
                        "title": "Behind the Scenes",
                        "season": None,
                        "episode": None,
                        "filename": "bonus.mkv",
                    }
                }
            }
        },
    )
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 1
    assert track.role == "Featurette"
    assert track.excluded is True  # Featurette not selected


@pytest.mark.asyncio
async def test_apply_map_missing_thediscdb_record() -> None:
    # apply_map returns 0 when metadata_json has no "thediscdb" key.
    track = Track(id=1, job_id=1, source_ref="0", role=None, role_source=None)
    job = Job(id=1, metadata_json={})  # No thediscdb
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 0


@pytest.mark.asyncio
async def test_apply_map_empty_matched_dict() -> None:
    # apply_map returns 0 when matched dict is empty.
    track = Track(id=1, job_id=1, source_ref="0", role=None, role_source=None)
    job = Job(id=1, metadata_json={"thediscdb": {"matched": {}}})
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 0


@pytest.mark.asyncio
async def test_apply_map_non_dict_record() -> None:
    # apply_map returns 0 when "thediscdb" is not a dict.
    track = Track(id=1, job_id=1, source_ref="0", role=None, role_source=None)
    job = Job(id=1, metadata_json={"thediscdb": "not a dict"})
    session = FakeAsyncSession([track])
    updated = await apply_map(session, job)  # type: ignore[arg-type]
    assert updated == 0
