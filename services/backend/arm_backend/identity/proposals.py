"""Load/store identity claims on a Job, plus the recorders for the two
sources that live inside the backend (manual edits, rip-preset selection)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from arm_common import Job, Track
from arm_common.schemas.identity import (
    JOB_CLAIM_FIELDS,
    TRACK_CLAIM_FIELDS,
    IdentityClaims,
    JobClaim,
    SourceClaims,
    TrackClaim,
)

logger = logging.getLogger(__name__)

MANUAL = "manual"
PRESET = "preset"

_TRACK_ATTR_TO_CLAIM = {attr: field for field, attr in TRACK_CLAIM_FIELDS.items()}
_JOB_ATTR_TO_CLAIM = {attr: field for field, attr in JOB_CLAIM_FIELDS.items()}


def claims_of(job: Job) -> IdentityClaims:
    raw = (job.metadata_json or {}).get("identity_claims")
    if raw is None:
        return IdentityClaims()
    try:
        return IdentityClaims.model_validate(raw)
    except ValidationError as e:
        logger.warning("identity_claims invalid job_id=%s; treating as empty: %s", job.id, e)
        return IdentityClaims()


def _store(job: Job, claims: IdentityClaims) -> None:
    # Reassign a NEW dict: SQLAlchemy's plain JSON column only notices
    # attribute assignment, not in-place mutation.
    job.metadata_json = {
        **(job.metadata_json or {}),
        "identity_claims": claims.model_dump(mode="json", exclude_unset=True),
    }


def put_source(job: Job, source_id: str, source_claims: SourceClaims) -> None:
    claims = claims_of(job)
    existing = claims.sources.get(source_id)
    if (
        source_claims.status == "error"
        and existing is not None
        and existing.status == "ok"
        and source_claims.inputs == existing.inputs
    ):
        # A failed re-run on the same inputs keeps the last good proposals (a
        # provider outage must not wipe episode numbers); the failure is
        # recorded for the UI. Claims made for different inputs are not kept.
        at = source_claims.run_at.isoformat() if source_claims.run_at else None
        existing.extra = {**existing.extra, "last_error": {"at": at, "detail": source_claims.detail}}
        source_claims = existing
    claims.sources = {**claims.sources, source_id: source_claims}
    _store(job, claims)


def _claim_value(attr: str, value: Any) -> tuple[str, Any]:
    field = _TRACK_ATTR_TO_CLAIM[attr]
    if field == "selected":
        return field, None if value is None else not value
    return field, value


def _manual(claims: IdentityClaims) -> SourceClaims:
    return claims.sources.get(MANUAL) or SourceClaims()


def _restated(obj: Job | Track, attr: str, value: Any) -> bool:
    """True when an edit only restates the object's current value and that
    value is not already the operator's. UIs re-send unchanged fields; turning
    those into manual claims would pin automatic values (and blanks) forever."""
    if (obj.identity_provenance or {}).get(attr) == MANUAL:
        return False
    return bool(getattr(obj, attr) == value)


def record_manual_track(job: Job, track: Track, edits: dict[str, Any]) -> bool:
    """Record the operator's track edits as `manual` claims, skipping restated
    values. Returns whether any claim was recorded."""
    edits = {attr: value for attr, value in edits.items() if not _restated(track, attr, value)}
    if not edits:
        return False
    source_ref = track.source_ref
    claims = claims_of(job)
    manual = _manual(claims)
    current = manual.tracks.get(source_ref)
    merged = current.model_dump(exclude_unset=True) if current is not None else {}
    for attr, value in edits.items():
        field, claim_value = _claim_value(attr, value)
        merged[field] = claim_value
    manual.tracks = {**manual.tracks, source_ref: TrackClaim(**merged)}
    claims.sources = {**claims.sources, MANUAL: manual}
    _store(job, claims)
    return True


def revert_manual_track(job: Job, source_ref: str, attrs: Iterable[str]) -> None:
    claims = claims_of(job)
    manual = claims.sources.get(MANUAL)
    if manual is None or source_ref not in manual.tracks:
        return
    remaining = manual.tracks[source_ref].model_dump(exclude_unset=True)
    for attr in attrs:
        remaining.pop(_TRACK_ATTR_TO_CLAIM[attr], None)
    tracks = dict(manual.tracks)
    if remaining:
        tracks[source_ref] = TrackClaim(**remaining)
    else:
        del tracks[source_ref]
    manual.tracks = tracks
    claims.sources = {**claims.sources, MANUAL: manual}
    _store(job, claims)


def record_manual_job(job: Job, edits: dict[str, Any], *, keep_restated: bool = False) -> bool:
    """Record the operator's job edits as `manual` claims, skipping restated
    values unless `keep_restated` (an explicit operator choice, e.g. the
    `/identity/match` season, that must pin even a value an automatic source
    already set). Returns whether any claim was recorded."""
    if not keep_restated:
        edits = {attr: value for attr, value in edits.items() if not _restated(job, attr, value)}
    if not edits:
        return False
    claims = claims_of(job)
    manual = _manual(claims)
    merged = manual.job.model_dump(exclude_unset=True)
    for attr, value in edits.items():
        merged[_JOB_ATTR_TO_CLAIM[attr]] = value
    manual.job = JobClaim(**merged)
    claims.sources = {**claims.sources, MANUAL: manual}
    _store(job, claims)
    return True


# Episode-match source ids share this prefix (sources.registry).
_EPISODE_SOURCE_PREFIX = "episodes_"


def forget_episode_show_ids(job: Job) -> None:
    """Set `inputs["show_id"]` to None in every stored episode-match entry
    (R2): once the job names a different show, a stored entry must never
    again look like "the same request", so an error or backoff re-run can
    not keep claims made for the previous show."""
    claims = claims_of(job)
    changed = False
    for source_id, entry in claims.sources.items():
        if source_id.startswith(_EPISODE_SOURCE_PREFIX) and entry.inputs.get("show_id") is not None:
            entry.inputs = {**entry.inputs, "show_id": None}
            changed = True
    if changed:
        _store(job, claims)


def set_pin(job: Job, capability: str, source_id: str) -> None:
    """Pin `source_id` as the operator's chosen source for `capability`
    (e.g. "episode") -- it then outranks its tier-mates in the resolver."""
    claims = claims_of(job)
    claims.pin = {**claims.pin, capability: source_id}
    _store(job, claims)


def clear_pin(job: Job, capability: str) -> None:
    """Remove any pin for `capability`. A no-op when nothing is pinned."""
    claims = claims_of(job)
    if capability not in claims.pin:
        return
    claims.pin = {k: v for k, v in claims.pin.items() if k != capability}
    _store(job, claims)


def record_preset(job: Job, tracks: Iterable[Track], *, now: datetime) -> None:
    """The rip preset's keep/drop decision is the lowest-tier proposal for
    `excluded`, so a disc map (or the operator) can override it by rule."""
    claims = claims_of(job)
    preset = claims.sources.get(PRESET) or SourceClaims()
    preset.tracks = {**preset.tracks, **{t.source_ref: TrackClaim(selected=not t.excluded) for t in tracks}}
    preset.run_at = now
    claims.sources = {**claims.sources, PRESET: preset}
    _store(job, claims)
