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
        ("LOTR_FELLOWSHIP_P1", LabelHints("lotr fellowship", None, 1, None, True)),
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


def test_parse_label_drops_unbounded_season() -> None:
    """An absurd digit run must be dropped, not overflow Postgres's int4
    season column (or raise on int()'s digit-count limit)."""
    hints = parse_label("X_S99999999999")
    assert hints.season is None


def test_parse_label_drops_out_of_range_disc_number() -> None:
    """`D0` is outside the valid 1-999 disc-number range, so it yields no
    disc hint at all (rather than a nonsensical disc 0)."""
    hints = parse_label("MOVIE_D0")
    assert hints.disc_number is None


def test_parse_label_sku_requires_word_boundary() -> None:
    """`_SKU_RE` must not eat into a real word that happens to start with
    the same three letters as SKU ("Skull") — only a standalone SKU token
    (optionally followed by digits) is a code to strip."""
    assert parse_label("Kong: Skull Island").title == "kong: skull island"
    # The original SKU-code-stripping behaviour must still work.
    assert parse_label("MOVIE_16X9_SKU1234") == LabelHints("movie", None, None, None)


def test_parse_label_normalizes_unicode() -> None:
    """NFKC folds compatibility glyphs (e.g. the trademark sign) before the
    Blu-ray-suffix strip runs, so a real disc label with a literal ™ still
    loses the branding suffix."""
    assert parse_label("Avatar Blu-ray™").title == "avatar"


def test_parse_label_part_marker_only() -> None:
    """A lone `P<n>` with no season/DISC/D marker flags part_marker_only —
    the text before it is one part of a single film and is not a safe
    search title (e.g. it could match the wrong part)."""
    hints = parse_label("HARRY_POTTER_DEATHLY_HALLOWS_P2")
    assert (hints.disc_number, hints.part_marker_only) == (2, True)


def test_parse_label_disc_marker_is_not_part_marker_only() -> None:
    """A `D<n>` marker is an explicit disc marker, not a part split, so
    part_marker_only stays False and the title is still a safe hint."""
    hints = parse_label("LOTR_FELLOWSHIP_D2")
    assert (hints.disc_number, hints.part_marker_only, hints.title) == (2, False, "lotr fellowship")


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


def test_label_source_part_marker_only_keeps_disc_drops_title() -> None:
    """A lone P<n> marker (one part of a single film) keeps the disc claim
    but must not propose a search title — the stripped text could match
    the wrong part of the film."""
    claims = LABEL.run(_ctx("HARRY_POTTER_DEATHLY_HALLOWS_P2"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {"disc_number": 2}


def test_label_source_disc_marker_still_emits_title() -> None:
    """A D<n> marker (not a bare P) is an explicit disc marker, so the
    title hint is still proposed."""
    claims = LABEL.run(_ctx("LOTR_FELLOWSHIP_D2"))
    assert claims.status == "ok"
    assert claims.job.model_dump(exclude_unset=True) == {"disc_number": 2, "title": "lotr fellowship"}
