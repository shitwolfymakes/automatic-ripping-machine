"""Volume-label hints: season / disc / total extraction and the LabelSource."""

from datetime import datetime, timezone

import pytest
from arm_common import DiscType, Job, JobStatus
from arm_common.schemas import ScanResult

from arm_backend.identity.sources.base import JobContext
from arm_backend.identity.sources.label_hints import LABEL, LabelHints, parse_label

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("WEST_WING_S3D2", LabelHints("west wing", 3, 2, None)),
        ("WEST_WING_S03_D02", LabelHints("west wing", 3, 2, None)),
        ("FRIENDS_S1_DISC_4", LabelHints("friends", 1, 4, None)),
        ("THE_OFFICE_SEASON_2", LabelHints("the office", 2, None, None)),
        ("THE_OFFICE_SEASON2", LabelHints("the office", 2, None, None)),
        ("LOST_S4", LabelHints("lost", 4, None, None)),
        ("LOTR_FELLOWSHIP_D2", LabelHints("lotr fellowship", None, 2, None)),
        ("LOTR_FELLOWSHIP_P1", LabelHints("lotr fellowship", None, 1, None)),
        ("BAND_OF_BROTHERS_DISC_3_OF_6", LabelHints("band of brothers", None, 3, 6)),
        ("PLANET_EARTH_DISC_TWO", LabelHints("planet earth", None, 2, None)),
        ("MOVIE_16X9_SKU1234", LabelHints("movie", None, None, None)),
        ("Some Movie - Blu-rayTM", LabelHints("some movie", None, None, None)),
    ],
)
def test_parse_label_extracts_hints(raw: str, expected: LabelHints) -> None:
    assert parse_label(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["APOLLO_13", "ROCKY_4", "BLADE_RUNNER_2049", "OCEANS_11", "STAR_WARS_EPISODE_IV", "THE_GODFATHER_PART_2", "SEVEN"],
)
def test_parse_label_movie_numbers_are_not_hints(raw: str) -> None:
    hints = parse_label(raw)
    assert (hints.season, hints.disc_number, hints.disc_total) == (None, None, None)


def test_parse_label_empty() -> None:
    assert parse_label("") == LabelHints("", None, None, None)


def test_parse_label_rejects_total_below_number() -> None:
    assert parse_label("SET_DISC_4_OF_2") == LabelHints("set", None, 4, None)


def _ctx(label: str | None, disc_type: DiscType = DiscType.DVD) -> JobContext:
    job = Job(id="job_1", drive_id="d", disc_type=disc_type, status=JobStatus.CREATED, metadata_json={})
    return JobContext(job=job, scan=ScanResult(disc_type=disc_type, volume_label=label), now=NOW)


def test_label_source_claims_job_fields_present_only() -> None:
    claims = LABEL.run(_ctx("WEST_WING_S3D2"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {"season": 3, "disc_number": 2, "title": "west wing"}
    assert claims.inputs == {"volume_label": "WEST_WING_S3D2"}


def test_label_source_miss_when_nothing_parsed() -> None:
    """No season/disc marker parsed -> no fields at all, not even a title:
    a marker-less label title is a worse search candidate than the
    dispatcher's own normalized-volume-label pass (fix round 1, item 2)."""
    claims = LABEL.run(_ctx("APOLLO_13"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize(("label", "disc_type"), [(None, DiscType.DVD), ("", DiscType.DVD), ("X_S1D1", DiscType.CD)])
def test_label_source_skips(label: str | None, disc_type: DiscType) -> None:
    assert LABEL.applies_to(_ctx(label, disc_type)) is not None


def test_label_source_applies_to_bluray() -> None:
    assert LABEL.applies_to(_ctx("X_S1D1", DiscType.BLURAY)) is None


def test_label_source_sets_disc_total() -> None:
    # A label like "DISC 3 OF 6" should set disc_total=6 in the claims
    claims = LABEL.run(_ctx("BAND_OF_BROTHERS_DISC_3_OF_6"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {"disc_number": 3, "disc_total": 6, "title": "band of brothers"}
    assert claims.inputs == {"volume_label": "BAND_OF_BROTHERS_DISC_3_OF_6"}
