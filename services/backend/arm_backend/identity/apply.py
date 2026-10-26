"""Applying, holding and re-applying a confident identify hit.

`apply_identity_result` is the one place a `MetadataResult` becomes the
job's identity (title, year, kind, poster, the typed `identity` section,
the music disc number). Identify calls it when the kind's auto-apply switch
is on; `POST /jobs/{id}/identity/accept` calls it when the operator confirms
a hit identify held (`suggest_identity`). Spec: identification-sources D-10.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from arm_backend.metadata.base import (
    MetadataResult,
    external_ids_of,
    extract_poster_url,
    first_str,
    metadata_with_identity,
)
from arm_common import Job
from arm_common.enums import MediaType
from arm_common.schemas.job_metadata import IdentitySuggestion, with_flags


def apply_identity_result(job: Job, result: MetadataResult, *, now: datetime) -> None:
    """Make `result` the job's identity (what identify did inline before PR 3)."""
    job.title = result.title
    job.year = result.year
    # G-03: keep the identified kind — it is the routing input.
    # result.kind is a subset of MediaType's values by construction.
    job.media_type = MediaType(result.kind)
    job.poster_url = extract_poster_url(result)
    # §3.4: identity + provider_raw, never a top-level payload merge.
    job.metadata_json = metadata_with_identity(job.metadata_json, result, identified_at=now)
    # A MusicBrainz medium position is this disc's number; the {disc}
    # naming token reads the column (G-14).
    if result.kind == "music" and job.disc_number is None:
        raw_disc = (result.payload or {}).get("disc")
        if isinstance(raw_disc, int) and not isinstance(raw_disc, bool):
            job.disc_number = raw_disc


def suggest_identity(metadata_json: dict[str, Any] | None, result: MetadataResult, *, now: datetime) -> dict[str, Any]:
    """Store `result` for the operator to confirm instead of applying it.

    The job stays unidentified (flag set: a rip started without confirming
    parks after the rip like any placeholder) and nothing from the hit reaches
    the `identity` section. The caller may still take the hit's kind into
    `job.media_type` — that is the routing key, not an identity claim (see the
    identify route's auto-apply-off branch)."""
    payload = result.payload or {}
    suggestion = IdentitySuggestion(
        provider=result.provider or "unknown",
        title=result.title,
        year=result.year,
        kind=result.kind,
        poster_url=extract_poster_url(result),
        external_ids=external_ids_of(result),
        overview=first_str(payload.get("overview"), payload.get("Plot")),
        payload=dict(payload),
        suggested_at=now,
    )
    md = with_flags(metadata_json, unidentified=True)
    md["identity_suggestion"] = suggestion.model_dump(mode="json", exclude_none=True)
    return md


def suggestion_to_result(suggestion: IdentitySuggestion) -> MetadataResult:
    """The held hit as identify saw it, for `apply_identity_result`."""
    return MetadataResult(
        title=suggestion.title,
        year=suggestion.year,
        kind=suggestion.kind,
        payload=dict(suggestion.payload),
        provider=suggestion.provider,
    )
