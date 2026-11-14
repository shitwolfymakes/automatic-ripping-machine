"""Applying an operator's identity resolve to a job and running the post-resolve pass:
the typed metadata merge, the commit, the after-rip / fan-out pass and the events."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.identity.ids import current_ids
from arm_backend.identity.pipeline import resolve_job
from arm_backend.identity.proposals import forget_episode_show_ids, record_manual_job
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.session_drain import ResolveFanOutOutcome, after_rip, fan_out_waiting_identify_applications
from arm_backend.ws import WSHub
from arm_common import Job, JobStatus, MediaType
from arm_common.enums import RESOLVABLE_PROMOTE_JOB_STATUSES
from arm_common.schemas import JobView, ResolveFanOutOutcomeView, ResolveMatch, ResolveRequest, ResolveResponse
from arm_common.schemas.job_metadata import ExternalIds, JobIdentity, JobMetadata, flag_is_set

logger = logging.getLogger(__name__)


def identity_snapshot(job: Job) -> tuple[int | None, int | None, MediaType | None, str | None, dict[str, Any]]:
    """`season`, `disc_number`, `media_type`, title and the show ids — the
    fields the background episode stage cares about. Compared before/after a
    mutating request to decide whether to (re)schedule it; a change to
    the show ids reschedules too."""
    return (job.season, job.disc_number, job.media_type, job.title, current_ids(job).model_dump())


# Two reasons a user may resolve identity:
#   1. Auto-identify failed and the job parked at AWAITING_USER_ID / RIPPED_AWAITING_IDENTIFY.
#      Resolving promotes it to IDENTIFIED and fan-out kicks any WAITING_IDENTIFY apps.
#   2. Auto-identify "succeeded" but landed wrong metadata (MakeMKV volume-label fallback,
#      stale TMDB entry, etc.) and the user wants to correct title/year/metadata after the
#      fact — possibly post-rip. The status MUST NOT change in this case; fan-out is a no-op
#      because there are no WAITING_IDENTIFY apps on an already-identified job.
# Show ids the /resolve merge path accepts; tvmaze is never accepted there,
# but a picked match (`match`) stores it (see _MATCH_ID_FIELDS).
_SHOW_ID_FIELDS: tuple[str, ...] = ("imdb", "tmdb", "tvdb")
# Ids a picked match states; the rest (musicbrainz_release, anidb) are kept.
_MATCH_ID_FIELDS: tuple[str, ...] = ("imdb", "tmdb", "tmdb_kind", "tvdb", "tvmaze")


def _same_show(old: ExternalIds, sent: ExternalIds) -> bool:
    """Whether a picked match names the show already stored: at least one show
    id agrees and none disagrees. An id only one side knows proves nothing
    either way (TMDb has no TVmaze id, OMDb only an IMDb one)."""
    agree = False
    for name in ("imdb", "tmdb", "tvdb", "tvmaze"):
        a, b = getattr(old, name), getattr(sent, name)
        if a is None or b is None:
            continue
        if a != b:
            return False
        agree = True
    return agree


def _apply_match(md: JobMetadata, req: ResolveRequest, now: datetime) -> bool:
    """A picked search result states the whole show:
    a different show's ids replace the stored show ids wholesale, tvmaze
    included; the same show re-picked from another provider only fills in,
    so the ids that provider lacks are kept. The identity records the
    provider and a facts snapshot. Returns whether a stored show id was
    replaced or cleared (a show change)."""
    assert req.match is not None
    sent = req.external_ids or ExternalIds()
    old = md.identity.external_ids if md.identity is not None else ExternalIds()
    ids = old.model_copy()
    if _same_show(old, sent):
        show_changed = False
        for name in _MATCH_ID_FIELDS:
            if getattr(sent, name) is not None:
                setattr(ids, name, getattr(sent, name))
    else:
        show_changed = any(
            getattr(old, name) is not None and getattr(old, name) != getattr(sent, name)
            for name in ("imdb", "tmdb", "tvdb", "tvmaze")
        )
        for name in _MATCH_ID_FIELDS:
            setattr(ids, name, getattr(sent, name))
    facts = req.match.facts
    md.identity = JobIdentity(
        provider=req.match.provider,
        external_ids=ids,
        overview=facts.overview if facts is not None else None,
        identified_at=now,
        facts=facts,
        facts_fetched_at=now if facts is not None else None,
    )
    return show_changed


def _names_another_show(existing: ExternalIds, sent: ExternalIds) -> bool:
    # A different imdb / tmdb / tvdb names a different show, so every
    # show id belonging to the old one and not sent now is stale: clear
    # tvmaze, and imdb / tmdb / tvdb when absent from the request (a
    # kept old imdb would let providers re-resolve the old show). An
    # explicit null only clears that one id; it names no other show.
    # Filling a blank id names no different show, so only a stored,
    # non-null id replaced by a different value triggers the clear.
    ids_set = sent.model_fields_set
    return any(
        name in ids_set
        and getattr(sent, name) is not None
        and getattr(existing, name) is not None
        and getattr(sent, name) != getattr(existing, name)
        for name in _SHOW_ID_FIELDS
    )


def _clear_old_show_ids(existing: ExternalIds, ids_set: set[str]) -> None:
    for name in ("tvmaze", "tmdb_kind", *_SHOW_ID_FIELDS):
        if name not in ids_set:
            setattr(existing, name, None)


def _overlay_sent_ids(existing: ExternalIds, sent: ExternalIds) -> None:
    ids_set = sent.model_fields_set
    if "imdb" in ids_set:
        existing.imdb = sent.imdb
    if "tmdb_kind" in ids_set:
        existing.tmdb_kind = sent.tmdb_kind
    elif "tmdb" in ids_set and sent.tmdb != existing.tmdb:
        existing.tmdb_kind = None  # a new TMDb id of unknown kind
    if "tmdb" in ids_set:
        existing.tmdb = sent.tmdb
    if "tvdb" in ids_set:
        existing.tvdb = sent.tvdb
    if "musicbrainz_release" in ids_set:
        existing.musicbrainz_release = sent.musicbrainz_release


def _merge_external_ids(md: JobMetadata, sent: ExternalIds) -> bool:
    if md.identity is None:
        md.identity = JobIdentity(provider="manual")
    # Per-field overlay, not a wholesale replace: a request that only
    # sets tmdb must not wipe a previously stored imdb/tvdb/etc.
    # Re-assigned (not just mutated) so exclude_unset picks up
    # external_ids as set even when identity was just freshly created.
    existing_ids = md.identity.external_ids
    ids_set = sent.model_fields_set
    show_changed = _names_another_show(existing_ids, sent)
    if show_changed:
        _clear_old_show_ids(existing_ids, ids_set)
    _overlay_sent_ids(existing_ids, sent)
    md.identity.external_ids = existing_ids
    return show_changed


def _merge_identity_metadata(job: Job, req: ResolveRequest) -> tuple[dict[str, Any], bool]:
    # Typed merge: req.music / req.external_ids overlay the
    # matching typed sections of the existing metadata_json; everything else
    # (scan_result, provider_raw, etc.) round-trips untouched. The
    # partial-edit case ("just fix the title") sends neither field and must
    # NOT wipe auto-identified sections.
    md = JobMetadata.model_validate(job.metadata_json or {})
    show_changed = False
    if req.music is not None:
        md.music = req.music
    # "external_ids" sent (even as {} or with some fields null) is
    # the operator editing identity; each MEMBER field then follows
    # omitted=keep / explicit-null=clears, via model_fields_set rather than
    # `is not None` (which can't tell "sent null" from "not sent" once
    # Pydantic has already collapsed both to None).
    if req.match is not None:
        show_changed = _apply_match(md, req, datetime.now(UTC))
    elif req.external_ids is not None:
        show_changed = _merge_external_ids(md, req.external_ids)
    new_metadata = md.model_dump(mode="json", exclude_unset=True)
    return new_metadata, show_changed


def _apply_match_poster(job: Job, match: ResolveMatch, show_changed: bool) -> None:
    # A picked match's poster is the automatic one; an operator-edited
    # URL is a manual override. A match with no
    # poster keeps the stored one unless it belongs to the old show, and
    # never clears an override.
    if match.poster_url is not None or show_changed:
        job.poster_url = match.poster_url
    if match.poster_is_manual:
        job.poster_url_manual = match.poster_url_manual
    elif match.poster_url is not None:
        job.poster_url_manual = None


def _clear_spent_markers(new_metadata: dict[str, Any]) -> None:
    # The spent `unidentified` flag (flags section + the legacy
    # top-level key) must be cleared on BOTH branches, not just PROMOTE. A
    # resolved RIPPED_PARTIAL placeholder stays in PRESERVE (partiality wins
    # over the placeholder status — see rip-complete) but has just as much
    # identity landed as a PROMOTE job; leaving flags.unidentified=true
    # forever would misreport it after the operator has already identified
    # it.
    new_metadata.pop("unidentified", None)
    # A resolve by any route is the operator identifying the disc: a held suggestion is moot.
    new_metadata.pop("identity_suggestion", None)
    # ...and the automatic match's miss reasons no longer apply.
    new_metadata.pop("identify_attempts", None)
    if isinstance(new_metadata.get("flags"), dict):
        new_metadata["flags"] = {k: v for k, v in new_metadata["flags"].items() if k != "unidentified"}


def _record_manual_disc_fields(job: Job, req: ResolveRequest) -> None:
    # Disc position and season are identity fields: they go through the
    # resolver as manual proposals so provenance is recorded and later
    # sources (episode matching, disc hints) never override them. This must
    # run AFTER resolve_identity's job.metadata_json = new_metadata -- record_manual_job
    # writes into metadata_json too, and assigning new_metadata first would
    # wipe the claim it just wrote.
    #
    # disc_number/disc_total/season are now classifications like media_type
    # omitted keeps the stored value (a title-only fix in
    # the identify dialog must not wipe a disc-hint-filled disc_number), an
    # EXPLICIT null is the operator clearing it. model_fields_set is the
    # only way to tell "sent null" from "not sent" here.
    manual_job: dict[str, Any] = {}
    for name in ("disc_number", "disc_total", "season"):
        if name in req.model_fields_set:
            manual_job[name] = getattr(req, name)
    if manual_job:
        record_manual_job(job, manual_job)


async def _emit_identify_resolved(session: AsyncSession, hub: WSHub, job: Job) -> None:
    payload = {
        "job_id": job.id,
        "drive_id": job.drive_id,
        "title": job.title,
        "year": job.year,
    }
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="identify.resolved",
        payload=payload,
        job_id=job.id,
        session=session,
    )
    await hub.emit(
        topic="ripper.events",
        event_type="rip.identify_resolved",
        payload=payload,
        job_id=job.id,
        session=session,
    )


def _resolve_response(job: Job, fan_out_outcomes: list[ResolveFanOutOutcome]) -> ResolveResponse:
    return ResolveResponse(
        job=JobView.model_validate(job),
        fan_out=[
            ResolveFanOutOutcomeView(
                session_application_id=outcome.application.id,
                session_id=outcome.application.session_id,
                status=outcome.application.status,
                task_count=len(outcome.tasks),
                skipped_reason=outcome.skipped_reason,
                error_detail=outcome.error_detail,
            )
            for outcome in fan_out_outcomes
        ],
    )


async def resolve_identity(
    session: AsyncSession,
    job: Job,
    req: ResolveRequest,
    *,
    hub: WSHub,
    stage_runner: EpisodeStageRunner | None,
    before_identity: tuple[int | None, int | None, MediaType | None, str | None, dict[str, Any]] | None = None,
) -> ResolveResponse:
    """The resolve route's body, shared with the suggestion accept route.

    `before_identity` lets a caller that already changed the job's identity
    (accept) still get the episode stage scheduled: the snapshot is taken
    here only when the caller passes none."""
    if before_identity is None:
        before_identity = identity_snapshot(job)

    new_metadata, show_changed = _merge_identity_metadata(job, req)

    job.title = req.title
    job.year = req.year
    if req.match is not None:
        _apply_match_poster(job, req.match, show_changed)
    # media_type is a classification, not part of the identity
    # statement -- omitted keeps the stored value, but an EXPLICIT null
    # clears it (the operator saying "clear the kind"). model_fields_set is
    # the only way to tell "sent null" from "not sent" here, since both
    # collapse to req.media_type is None.
    if "media_type" in req.model_fields_set:
        job.media_type = req.media_type
    was_ripped_placeholder = job.status == JobStatus.RIPPED_AWAITING_IDENTIFY
    # The rip already finished but rip-complete skipped after_rip because the
    # disc was unidentified: a ripped placeholder, or a partial one (which
    # keeps RIPPED_PARTIAL). Read the flag now; it is cleared just below.
    rip_waited_for_identity = was_ripped_placeholder or (
        job.status == JobStatus.RIPPED_PARTIAL and flag_is_set(job.metadata_json, "unidentified")
    )
    _clear_spent_markers(new_metadata)
    if job.status in RESOLVABLE_PROMOTE_JOB_STATUSES:
        # A placeholder whose rip already finished becomes RIPPED, not
        # IDENTIFIED — its rip is done.
        job.status = JobStatus.RIPPED if was_ripped_placeholder else JobStatus.IDENTIFIED
    job.metadata_json = new_metadata
    if show_changed:
        # The stored episode entries were matched against the previous
        # show; forgetting their show id means no keep-path can hold them.
        forget_episode_show_ids(job)
    _record_manual_disc_fields(job, req)
    await resolve_job(session, job)
    session.add(job)

    # Commit the resolve's job mutations (title/year/status/etc.)
    # BEFORE running after_rip / fan_out_waiting_identify_applications.
    # after_rip's drain half (drain_parked_applications_after_rip) rolls back
    # the session on any exception -- committing after would let that rollback
    # silently discard the operator's just-applied resolve, yet the
    # endpoint would still return 200 built from the (rolled-back, but
    # still-mutated-in-Python) job object. Committing first mirrors
    # rip-complete, which also commits its status change before invoking
    # after_rip; a subsequent after_rip failure can then only affect fan-out,
    # never the resolve itself.
    await session.commit()
    await session.refresh(job)

    if rip_waited_for_identity:
        # Rip done + identity just landed: run the same post-rip pass
        # rip-complete runs for identified jobs — drain parked applications
        # (fan-out uses the just-resolved title) and then the auto-apply
        # hook. `after_rip` commits its own work and never raises.
        fan_out_outcomes = await after_rip(session, job, hub)
    else:
        fan_out_outcomes = await fan_out_waiting_identify_applications(session, job=job, hub=hub)

    logger.info(
        "resolve job_id=%s -> identified title=%s fan_out=%d",
        job.id,
        job.title,
        len(fan_out_outcomes),
    )

    await _emit_identify_resolved(session, hub, job)

    # Second commit lands the fan-out's task rows (when after_rip/fan-out did
    # not already commit or roll back on its own) plus the
    # identify.resolved + rip.identify_resolved events. The resolve itself is
    # already durable from the commit above.
    await session.commit()
    await session.refresh(job)
    for outcome in fan_out_outcomes:
        await session.refresh(outcome.application)

    if stage_runner is not None and identity_snapshot(job) != before_identity:
        stage_runner.schedule(job.id)

    return _resolve_response(job, fan_out_outcomes)
