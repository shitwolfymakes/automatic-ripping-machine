"""Job-log events the backend emits: small pure message builders and the thin emitters that log them."""

from __future__ import annotations

import logging
from typing import Any

from arm_common import Job
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


def identified_message(title: str | None, year: int | None, provider: str, method: str) -> str:
    """`identified: <title> (<year>), <Provider> <method>`, naming how the disc was recognised."""
    name = title or "untitled"
    shown = f"{name} ({year})" if year else name
    return f"identified: {shown}, {_provider_name(provider)} {_METHOD_NAMES.get(method, method)}"


def not_identified_message(provider: str | None, reason: str) -> str:
    """`not identified: <Provider>: <reason>; waiting for identification`."""
    cause = f"{_provider_name(provider)}: {reason}" if provider else reason
    return f"not identified: {cause}; waiting for identification"


def episodes_matched_message(matched: int, unmatched: int, series: str | None, season: int | None) -> str:
    """`matched 5 titles to <series> S1 (1 unmatched)`."""
    noun = "title" if matched == 1 else "titles"
    target = series or "an unnamed show"
    return f"matched {matched} {noun} to {target}{f' S{season}' if season is not None else ''} ({unmatched} unmatched)"


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


def log_identified(job: Job, provider: str, method: str) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "identify.resolved",
            identified_message(job.title, job.year, provider, method),
            title=job.title,
            year=job.year,
            media_type=job.media_type.value if job.media_type else None,
            provider=provider,
            method=method,
        )


def log_not_identified(job: Job, provider: str | None, reason: str) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "identify.missed",
            not_identified_message(provider, reason),
            provider=provider,
            reason=reason,
        )


def log_identify_held(job: Job, reason: str) -> None:
    with with_log_context(job_id=job.id):
        log_event(logger, "identify.held", f"held: {reason}", reason=reason)


def log_episodes_matched(job: Job, matched: int, unmatched: int, series: str | None, season: int | None) -> None:
    with with_log_context(job_id=job.id):
        log_event(
            logger,
            "episodes.matched",
            episodes_matched_message(matched, unmatched, series, season),
            matched=matched,
            unmatched=unmatched,
            series=series,
            season=season,
        )
