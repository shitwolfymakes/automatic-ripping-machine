"""Job-log events the backend emits: small pure message builders and the thin emitters that log them."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from arm_backend.track_labels import TrackLabel, track_label
from arm_common import Job, Track
from arm_common.log_format import elapsed, human_duration, human_size
from arm_common.logging import log_event, with_log_context

logger = logging.getLogger("arm_backend.job_events")

_PROVIDER_NAMES: dict[str, str] = {
    "musicbrainz": "MusicBrainz",
    "tmdb": "TMDB",
    "omdb": "OMDb",
    "tvmaze": "TVmaze",
    "tvdb": "TVDB",
    "arm_server": "ARM server",
    "thediscdb": "TheDiscDB",
}
_METHOD_NAMES: dict[str, str] = {
    "disc_id": "disc ID",
    "fingerprint": "fingerprint",
    "title": "title search",
    "imdb": "IMDb lookup",
    "release": "release",
}


def _provider_name(provider: str) -> str:
    return _PROVIDER_NAMES.get(provider, provider)


def identified_message(
    title: str | None, year: int | None, provider: str, method: str, artist: str | None = None
) -> str:
    """`identified: <artist> - <title> (<year>), <Provider> <method>`, naming how the disc was recognised."""
    name = title or "untitled"
    named = f"{artist} - {name}" if artist else name
    shown = f"{named} ({year})" if year else named
    return f"identified: {shown}, {_provider_name(provider)} {_METHOD_NAMES.get(method, method)}"


def not_identified_message(provider: str | None, reason: str, *, waiting: bool = True) -> str:
    """`not identified: <Provider>: <reason>; <what happens next>`: the job waits, or rips as unidentified."""
    cause = f"{_provider_name(provider)}: {reason}" if provider else reason
    outcome = "waiting for identification" if waiting else "ripping as unidentified"
    return f"not identified: {cause}; {outcome}"


def _season_label(season: int | None, episodes: tuple[int, int] | None) -> str:
    """` S1E1-E5` (` S1E3` for one episode, ` S1` without episode numbers, empty without a season)."""
    if season is None:
        return ""
    if episodes is None:
        return f" S{season}"
    first, last = episodes
    return f" S{season}E{first}" + (f"-E{last}" if last != first else "")


def episodes_matched_message(
    matched: int, unmatched: int, series: str | None, season: int | None, episodes: tuple[int, int] | None = None
) -> str:
    """`matched 5 titles to <series> S1E1-E5 (1 unmatched)`; `episodes` is the first and last episode number."""
    noun = "title" if matched == 1 else "titles"
    target = series or "an unnamed show"
    return f"matched {matched} {noun} to {target}{_season_label(season, episodes)} ({unmatched} unmatched)"


_KEYED_STEPS = frozenset({"title", "fingerprint", "imdb"})


def miss_cause(attempt: dict[str, Any] | None) -> tuple[str | None, str]:
    """The provider and reason of the lookup attempt a miss ended on; no attempt means no source answered."""
    if attempt is None:
        return None, "no source answered"
    detail = attempt["detail"] or attempt["outcome"]
    if attempt["outcome"] == "miss" and attempt["step"] in _KEYED_STEPS:
        detail = f"no match for {detail}"
    return attempt["source"], detail


def held_hit_reason(kind: str, title: str, ambiguous_toc: bool) -> str:
    """Why a hit waits for the operator instead of being applied."""
    why = "several releases fit the track layout" if ambiguous_toc else "auto-apply off"
    return f"{kind} hit {title!r} held for confirmation ({why})"


def previously_ripped_reason(previous_job_id: str) -> str:
    """Why a disc waits: an earlier job already ripped it."""
    return f"disc already ripped as {previous_job_id}"


def _track_name(label: TrackLabel) -> str:
    """`track 1/19` with the quoted title when the job's identity gives one."""
    base = f"track {label.index}/{label.total}"
    return f'{base} "{label.title}"' if label.title else base


def track_ripped_message(label: TrackLabel, size_bytes: int | None, duration_seconds: int | None) -> str:
    """`track 1/19 "<title>" ripped (41.1 MB, 4:04)`."""
    return f"{_track_name(label)} ripped ({human_size(size_bytes)}, {human_duration(duration_seconds)})"


def track_failed_message(label: TrackLabel, error: str) -> str:
    """`track 7/19 "<title>" failed: <error>`."""
    return f"{_track_name(label)} failed: {error}"


def rip_completed_message(done: int, failed: int, total: int, elapsed_seconds: float | None) -> str:
    """`rip complete: 19/19 tracks in 6m42s`; no `in …` without a start time. `failed` rides in the fields."""
    suffix = "" if elapsed_seconds is None else f" in {elapsed(elapsed_seconds)}"
    return f"rip complete: {done}/{total} tracks{suffix}"


def log_identified(job: Job, provider: str, method: str, artist: str | None = None) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "identify.resolved",
            identified_message(job.title, job.year, provider, method, artist),
            artist=artist,
            title=job.title,
            year=job.year,
            media_type=job.media_type.value if job.media_type else None,
            provider=provider,
            method=method,
        )


def log_not_identified(job: Job, provider: str | None, reason: str, *, waiting: bool = True) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "identify.missed",
            not_identified_message(provider, reason, waiting=waiting),
            provider=provider,
            reason=reason,
        )


def log_identify_held(job: Job, reason: str) -> None:
    with with_log_context(job_id=job.id):
        log_event(logger, "identify.held", f"held: {reason}", reason=reason)


def log_episodes_matched(
    job: Job,
    matched: int,
    unmatched: int,
    series: str | None,
    season: int | None,
    episodes: tuple[int, int] | None = None,
) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "episodes.matched",
            episodes_matched_message(matched, unmatched, series, season, episodes),
            matched=matched,
            unmatched=unmatched,
            series=series,
            season=season,
        )


def log_track_ripped(job: Job, track: Track, tracks: Sequence[Track]) -> None:
    label = track_label(job, track, tracks)
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "track.ripped",
            track_ripped_message(label, track.size_bytes, track.duration_seconds),
            track_index=label.index,
            track_total=label.total,
            title=label.title,
            size_bytes=track.size_bytes,
            duration_seconds=track.duration_seconds,
        )


def log_track_failed(job: Job, track: Track, tracks: Sequence[Track]) -> None:
    label = track_label(job, track, tracks)
    error = track.last_error or "unknown error"
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "track.failed",
            track_failed_message(label, error),
            level=logging.WARNING,
            track_index=label.index,
            track_total=label.total,
            title=label.title,
            error=error,
        )


def log_rip_completed(job: Job, done: int, failed: int, total: int) -> None:
    elapsed_seconds = None if job.started_at is None else (datetime.now(timezone.utc) - job.started_at).total_seconds()
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "rip.completed",
            rip_completed_message(done, failed, total, elapsed_seconds),
            done=done,
            failed=failed,
            total=total,
            status=job.status.value,
            elapsed_seconds=elapsed_seconds,
        )
