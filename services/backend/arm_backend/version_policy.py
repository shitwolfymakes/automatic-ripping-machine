"""The "one version of the film" policy of a video job: what starts ticked when a disc holds the same
film more than once (angles, 3D and 2D, a copy without chapters).

The policy is `Job.tick_one_version`, snapshotted from `Config.tick_one_version` at creation. The ticks
it yields are never written to a track: they are the rip preset's lowest-tier `selected` claims, so an
operator's own tick (a `manual` claim) wins and the resolver turns the claims into `Track.excluded`.
`recompute_ticks` re-records those claims; the callers resolve afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.identity.proposals import preferred_titles, record_preset_selection, revert_manual_track
from arm_backend.rip_preset_resolution import RipPresetUnavailable, load_routed_session, resolve_rip_preset_for_job
from arm_backend.track_selection import preset_ticks, title_classes
from arm_backend.transcode_apply import is_passthrough_preset
from arm_common import DiscType, Job, Session, TranscodePreset
from arm_common.enums import PRE_RIP_JOB_STATUSES, VIDEO_DISC_TYPES
from arm_common.models import Track
from arm_common.schemas import ScanResult
from arm_common.title_classes import TitleClass, TitleVerdict, version_sets


def ticks_one_version(job: Job) -> bool:
    """The job's policy; a job that never snapshotted one (not a video disc) takes the default."""
    return job.tick_one_version is not False


def policy_applies(job: Job) -> bool:
    """A video job whose rip has not started: the only jobs whose ticks the policy decides."""
    return job.disc_type in VIDEO_DISC_TYPES and job.status in PRE_RIP_JOB_STATUSES


async def prefers_stereo_3d(db: AsyncSession, sess: Session | None) -> bool:
    """D60: which dimension of a 2D/3D twin pair is the pick. The session's transcode preset decides:
    an encode drops the 3D view, so it takes 2D (the cheaper read, the same output); a passthrough
    session, or no session, archives the disc and keeps the 3D. `is_passthrough_preset` is the one
    definition of passthrough (no preset, or `TranscodeTool.NONE`)."""
    preset = None
    if sess is not None and sess.transcode_preset_id is not None:
        preset = (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()
    return is_passthrough_preset(preset)


class SelectionPolicy(TypedDict):
    """The keyword arguments of `select_tracks` and `preset_ticks` that carry the policy."""

    tick_one_version: bool
    prefer_stereo_3d: bool | None


async def selection_policy(db: AsyncSession, job: Job, sess: Session | None = None) -> SelectionPolicy:
    """The job's policy for track selection. The 2D/3D rule needs the session only on a Blu-ray (only
    there does the classifier pair a title with its twin); `sess` overrides the job's routed session."""
    prefer = None
    if job.disc_type == DiscType.BLURAY:
        prefer = await prefers_stereo_3d(db, sess or await load_routed_session(db, job))
    return {"tick_one_version": ticks_one_version(job), "prefer_stereo_3d": prefer}


def version_set_refs(tracks: Sequence[Track]) -> frozenset[str]:
    """The `source_ref`s of every member of every version set of the job's tracks (the pick, its
    alternates; all editions and their alternates are one set), derived from the classifier columns."""
    by_ref = {t.source_ref: t for t in tracks if t.title_class is not None}
    verdicts = [
        TitleVerdict(
            t.index,
            t.title_class,
            by_ref[t.title_class_ref].index if t.title_class_ref in by_ref else None,
        )
        for t in by_ref.values()
        if t.title_class is not None
    ]
    by_index = {t.index: t.source_ref for t in by_ref.values()}
    return frozenset(by_index[i] for members in version_sets(verdicts) for i in members)


def withdraw_manual_ticks(job: Job, tracks: Sequence[Track]) -> None:
    """Drop the operator's tick claims on every member of a version set, so the policy decides them again."""
    for ref in version_set_refs(tracks):
        revert_manual_track(job, ref, ["excluded"])


async def recompute_ticks(
    db: AsyncSession,
    job: Job,
    tracks: Sequence[Track],
    scan: ScanResult,
    *,
    rippable: frozenset[str] | None,
    sess: Session | None = None,
) -> set[str]:
    """Re-record the preset's ticks of a Blu-ray job's tracks under its policy, with the title map
    (`rippable`, None before it arrives) and the transcode signal as they are now, and refresh the tracks'
    classifier columns (the 2D/3D pick can move them). `sess` is the session the transcode signal comes
    from; else the job's routed session. Returns the ids of the tracks whose columns changed; the caller
    resolves, which applies the claims."""
    if scan.disc_type != DiscType.BLURAY:
        return set()
    try:
        preset = await resolve_rip_preset_for_job(db, job)
    except RipPresetUnavailable:
        return set()
    policy = await selection_policy(db, job, sess)
    preferred = preferred_titles(job)
    ticks = preset_ticks(scan, preset, preferred=preferred, rippable=rippable, **policy)
    if ticks is None:
        return set()
    record_preset_selection(job, {t.source_ref: t.source_ref in ticks for t in tracks}, now=datetime.now(timezone.utc))
    return _refresh_classes(
        tracks, title_classes(scan, preferred=preferred, prefer_stereo_3d=policy["prefer_stereo_3d"])
    )


def _refresh_classes(tracks: Sequence[Track], columns: dict[str, tuple[TitleClass | None, str | None]]) -> set[str]:
    changed: set[str] = set()
    for track in tracks:
        found = columns.get(track.source_ref)
        if found is not None and found != (track.title_class, track.title_class_ref):
            track.title_class, track.title_class_ref = found
            changed.add(track.id)
    return changed
