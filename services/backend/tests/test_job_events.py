"""Backend job-log event builders and emitters."""

from __future__ import annotations

import pytest

from arm_backend import job_events
from arm_common import DiscType, Job, JobStatus, MediaType
from tests._logs import LineCapture


def _job(**kw: object) -> Job:
    base: dict[str, object] = {
        "id": "job_1",
        "drive_id": "d",
        "disc_type": DiscType.CD,
        "status": JobStatus.IDENTIFIED,
        "title": "The Essential Electric Light Orchestra",
        "year": 2011,
        "media_type": MediaType.MUSIC,
    }
    return Job(**{**base, **kw})  # type: ignore[arg-type]


def test_identified_message_names_title_year_and_method() -> None:
    msg = job_events.identified_message("The Essential Electric Light Orchestra", 2011, "musicbrainz", "disc_id")
    assert msg == "identified: The Essential Electric Light Orchestra (2011), MusicBrainz disc ID"


@pytest.mark.parametrize(
    ("title", "year", "provider", "method", "expected"),
    [
        (None, None, "tmdb", "title", "identified: untitled, TMDB title search"),
        ("Iron Man", None, "tmdb", "imdb", "identified: Iron Man, TMDB IMDb lookup"),
        ("Heat", 1995, "arm_server", "fingerprint", "identified: Heat (1995), ARM server fingerprint"),
        ("Heat", 1995, "thediscdb", "release", "identified: Heat (1995), TheDiscDB release"),
        ("Heat", 1995, "newsrc", "other", "identified: Heat (1995), newsrc other"),
    ],
)
def test_identified_message_variants(
    title: str | None, year: int | None, provider: str, method: str, expected: str
) -> None:
    assert job_events.identified_message(title, year, provider, method) == expected


def test_not_identified_message_carries_the_reason() -> None:
    msg = job_events.not_identified_message("musicbrainz", "no release fits the track layout")
    assert msg == "not identified: MusicBrainz: no release fits the track layout; waiting for identification"


def test_not_identified_message_without_a_provider() -> None:
    assert job_events.not_identified_message(None, "no source configured") == (
        "not identified: no source configured; waiting for identification"
    )


def test_episodes_matched_message() -> None:
    msg = job_events.episodes_matched_message(5, 1, "Kolchak: The Night Stalker", 1)
    assert msg == "matched 5 titles to Kolchak: The Night Stalker S1 (1 unmatched)"


def test_episodes_matched_message_singular_and_unknown_show() -> None:
    assert job_events.episodes_matched_message(1, 0, None, None) == "matched 1 title to an unnamed show (0 unmatched)"


def test_log_identified_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_identified(_job(), "musicbrainz", "disc_id")
    [line] = job_log.lines(event="identify.resolved")
    assert line["msg"] == "identified: The Essential Electric Light Orchestra (2011), MusicBrainz disc ID"
    assert line["fields"] == {
        "title": "The Essential Electric Light Orchestra",
        "year": 2011,
        "media_type": "music",
        "provider": "musicbrainz",
        "method": "disc_id",
    }


def test_log_not_identified_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_not_identified(_job(), "musicbrainz", "no release fits the track layout")
    [line] = job_log.lines(event="identify.missed")
    assert line["fields"] == {"provider": "musicbrainz", "reason": "no release fits the track layout"}
    assert "no release fits the track layout" in line["msg"]


def test_log_identify_held_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_identify_held(_job(), "already ripped as job_0")
    [line] = job_log.lines(event="identify.held")
    assert line["msg"] == "held: already ripped as job_0"
    assert line["fields"] == {"reason": "already ripped as job_0"}


def test_log_episodes_matched_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_episodes_matched(_job(), 5, 1, "Kolchak", 1)
    [line] = job_log.lines(event="episodes.matched")
    assert line["fields"] == {"matched": 5, "unmatched": 1, "series": "Kolchak", "season": 1}


@pytest.mark.parametrize(
    ("ambiguous", "why"),
    [(True, "several releases fit the track layout"), (False, "auto-apply off")],
)
def test_held_hit_reason(ambiguous: bool, why: str) -> None:
    assert job_events.held_hit_reason("music", "Greatest Hits", ambiguous) == (
        f"music hit 'Greatest Hits' held for confirmation ({why})"
    )


def test_previously_ripped_reason() -> None:
    assert job_events.previously_ripped_reason("job_0") == "disc already ripped as job_0"


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        (None, (None, "no source answered")),
        (
            {
                "source": "musicbrainz",
                "step": "disc_id",
                "outcome": "miss",
                "detail": "no release fits the track layout",
            },
            ("musicbrainz", "no release fits the track layout"),
        ),
        ({"source": "tmdb", "step": "title", "outcome": "miss", "detail": "MY_DISC"}, ("tmdb", "no match for MY_DISC")),
        ({"source": "tmdb", "step": "title", "outcome": "timeout", "detail": None}, ("tmdb", "timeout")),
        (
            {"source": None, "step": "title", "outcome": "timeout", "detail": "lookup took longer than 30 s"},
            (None, "lookup took longer than 30 s"),
        ),
    ],
)
def test_miss_cause(attempt: dict[str, object] | None, expected: tuple[str | None, str]) -> None:
    assert job_events.miss_cause(attempt) == expected
