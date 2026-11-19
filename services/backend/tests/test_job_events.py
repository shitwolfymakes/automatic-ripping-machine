"""Backend job-log event builders and emitters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arm_backend import job_events
from arm_backend.track_labels import TrackLabel
from arm_common import DiscType, Job, JobStatus, MediaType, Track, TrackKind, TrackStatus
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


def _track(index: int, **kw: object) -> Track:
    return Track(
        id=f"t{index}",
        job_id="job_1",
        kind=TrackKind.AUDIO_TRACK,
        index=index,
        source_ref=str(index),
        status=TrackStatus.DONE,
        attempts=0,
        **kw,  # type: ignore[arg-type]
    )


def test_identified_message_names_title_year_and_method() -> None:
    msg = job_events.identified_message("The Essential Electric Light Orchestra", 2011, "musicbrainz", "disc_id")
    assert msg == "identified: The Essential Electric Light Orchestra (2011), MusicBrainz disc ID"


def test_identified_message_leads_with_the_artist() -> None:
    msg = job_events.identified_message(
        "The Essential Electric Light Orchestra", 2011, "musicbrainz", "disc_id", "Electric Light Orchestra"
    )
    assert msg == (
        "identified: Electric Light Orchestra - The Essential Electric Light Orchestra (2011), MusicBrainz disc ID"
    )


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


def test_not_identified_message_for_a_placeholder_rip() -> None:
    msg = job_events.not_identified_message("tmdb", "no match for MY_DISC", waiting=False)
    assert msg == "not identified: TMDB: no match for MY_DISC; ripping as unidentified"


def test_not_identified_message_without_a_provider() -> None:
    assert job_events.not_identified_message(None, "no source configured") == (
        "not identified: no source configured; waiting for identification"
    )


def test_episodes_matched_message() -> None:
    msg = job_events.episodes_matched_message(5, 1, "Kolchak: The Night Stalker", 1)
    assert msg == "matched 5 titles to Kolchak: The Night Stalker S1 (1 unmatched)"


def test_episodes_matched_message_with_the_episode_range() -> None:
    msg = job_events.episodes_matched_message(5, 1, "Kolchak: The Night Stalker", 1, (1, 5))
    assert msg == "matched 5 titles to Kolchak: The Night Stalker S1E1-E5 (1 unmatched)"


def test_episodes_matched_message_with_a_single_episode() -> None:
    assert job_events.episodes_matched_message(1, 0, "Show", 2, (4, 4)) == "matched 1 title to Show S2E4 (0 unmatched)"


def test_episodes_matched_message_range_needs_a_season() -> None:
    assert job_events.episodes_matched_message(2, 0, "Show", None, (1, 2)) == "matched 2 titles to Show (0 unmatched)"


def test_episodes_matched_message_singular_and_unknown_show() -> None:
    assert job_events.episodes_matched_message(1, 0, None, None) == "matched 1 title to an unnamed show (0 unmatched)"


def test_log_identified_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_identified(_job(), "musicbrainz", "disc_id", "Electric Light Orchestra")
    [line] = job_log.lines(event="identify.resolved")
    assert line["msg"] == (
        "identified: Electric Light Orchestra - The Essential Electric Light Orchestra (2011), MusicBrainz disc ID"
    )
    assert line["fields"] == {
        "artist": "Electric Light Orchestra",
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
    assert line["msg"].endswith("waiting for identification")


def test_log_not_identified_for_a_placeholder_rip(job_log: LineCapture) -> None:
    job_events.log_not_identified(_job(), "tmdb", "no match for MY_DISC", waiting=False)
    [line] = job_log.lines(event="identify.missed")
    assert line["msg"].endswith("ripping as unidentified")


def test_log_identify_held_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_identify_held(_job(), "already ripped as job_0")
    [line] = job_log.lines(event="identify.held")
    assert line["msg"] == "held: already ripped as job_0"
    assert line["fields"] == {"reason": "already ripped as job_0"}


def test_log_episodes_matched_emits_the_event(job_log: LineCapture) -> None:
    job_events.log_episodes_matched(_job(), 5, 1, "Kolchak", 1, (1, 5))
    [line] = job_log.lines(event="episodes.matched")
    assert line["msg"] == "matched 5 titles to Kolchak S1E1-E5 (1 unmatched)"
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


def test_track_ripped_message_with_and_without_title() -> None:
    label = TrackLabel(1, 19, "Don't Bring Me Down")
    assert (
        job_events.track_ripped_message(label, 43_100_000, 244)
        == 'track 1/19 "Don\'t Bring Me Down" ripped (41.1 MB, 4:04)'
    )
    assert job_events.track_ripped_message(TrackLabel(3, 6, None), 9_800_000_000, 3093) == (
        "track 3/6 ripped (9.1 GB, 51:33)"
    )


def test_track_failed_message() -> None:
    assert job_events.track_failed_message(TrackLabel(7, 19, "Xanadu"), "cdparanoia returned code 1") == (
        'track 7/19 "Xanadu" failed: cdparanoia returned code 1'
    )
    assert job_events.track_failed_message(TrackLabel(7, 19, None), "boom") == "track 7/19 failed: boom"


def test_rip_completed_message_with_and_without_elapsed() -> None:
    assert job_events.rip_completed_message(19, 0, 19, 402.0) == "rip complete: 19/19 tracks in 6m42s"
    assert job_events.rip_completed_message(5, 1, 6, None) == "rip complete: 5/6 tracks"


def test_log_track_ripped_emits_the_event(job_log: LineCapture) -> None:
    tracks = [_track(1, size_bytes=10, duration_seconds=65)]
    job_events.log_track_ripped(_job(), tracks[0], tracks)
    (line,) = job_log.lines(event="track.ripped")
    assert line["job_id"] == "job_1"
    assert line["level"] == "info"
    assert line["fields"] == {
        "track_index": 1,
        "track_total": 1,
        "title": None,
        "size_bytes": 10,
        "duration_seconds": 65,
    }


def test_log_track_failed_emits_a_warning(job_log: LineCapture) -> None:
    tracks = [_track(1, last_error="bad")]
    job_events.log_track_failed(_job(), tracks[0], tracks)
    (line,) = job_log.lines(event="track.failed")
    assert line["level"] == "warning"
    assert line["msg"] == "track 1/1 failed: bad"
    assert line["fields"] == {"track_index": 1, "track_total": 1, "title": None, "error": "bad"}


def test_log_track_failed_without_an_error_says_unknown(job_log: LineCapture) -> None:
    tracks = [_track(1)]
    job_events.log_track_failed(_job(), tracks[0], tracks)
    assert job_log.lines(event="track.failed")[0]["msg"] == "track 1/1 failed: unknown error"


def test_log_rip_completed_measures_from_started_at(job_log: LineCapture) -> None:
    job = _job()
    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=402)
    job.status = JobStatus.RIPPED
    job_events.log_rip_completed(job, 19, 0, 19)
    (line,) = job_log.lines(event="rip.completed")
    assert line["msg"].startswith("rip complete: 19/19 tracks in 6m4")
    assert line["fields"]["status"] == "ripped"
    assert 401 <= line["fields"]["elapsed_seconds"] <= 410
    assert {k: line["fields"][k] for k in ("done", "failed", "total")} == {"done": 19, "failed": 0, "total": 19}


def test_log_rip_completed_without_started_at(job_log: LineCapture) -> None:
    job_events.log_rip_completed(_job(), 1, 0, 1)
    (line,) = job_log.lines(event="rip.completed")
    assert line["msg"] == "rip complete: 1/1 tracks"
    assert line["fields"]["elapsed_seconds"] is None
