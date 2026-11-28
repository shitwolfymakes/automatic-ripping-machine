"""The title map of a structure-scan Blu-ray job: MakeMKV's titles, once they arrive, mapped onto the playlist
structure's title refs.

A structure scan is posted before MakeMKV has read the disc, so the job's tracks are keyed by title ref
(`00334.mpls:2`). MakeMKV's own titles come later (`POST /api/ripper/jobs/{id}/titles`) and are stored in the
scan; the map from refs to MakeMKV title numbers is recomputed from the stored scan whenever it is needed, so a
resume reads the same answer.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.identity.events import emit_identity_resolved
from arm_backend.identity.pipeline import ResolveOutcome, resolve_job
from arm_backend.identity.proposals import record_preset_drop, revert_manual_track
from arm_backend.version_policy import recompute_ticks
from arm_backend.ws import WSHub
from arm_common import Job
from arm_common.disc_titles import MAKEMKV_FAILURE_KEY, is_structure_scan, scan_candidates, title_ref
from arm_common.models import Track
from arm_common.schemas import ScanFailure, ScanResult, ScanTitle, TitlesReadView, TitlesReport
from arm_common.title_map import TitleMap, map_titles

logger = logging.getLogger("arm_backend.title_map_service")

TITLES_PENDING = "titles_pending: MakeMKV has not finished reading the disc"


class NotAStructureScan(Exception):
    """The job has no stored structure scan for MakeMKV's titles to join."""


def stored_scan(job: Job) -> ScanResult | None:
    """The scan stored on the job, or None when it has none."""
    scan_dict = (job.metadata_json or {}).get("scan_result")
    return ScanResult.model_validate(scan_dict) if scan_dict else None


def makemkv_failure(job: Job) -> ScanFailure | None:
    """Why MakeMKV could not read the job's disc, when it could not."""
    failure = (job.metadata_json or {}).get(MAKEMKV_FAILURE_KEY)
    return ScanFailure.model_validate(failure) if failure else None


def title_map_of(scan: ScanResult) -> TitleMap | None:
    """The map from the scan's refs to MakeMKV's title numbers; None until MakeMKV's titles are in (and for any
    scan that is not a structure scan)."""
    if not is_structure_scan(scan) or not scan.titles:
        return None
    return map_titles(scan_candidates(scan), scan.titles)


def rippable_refs(scan: ScanResult) -> frozenset[str] | None:
    """The refs MakeMKV can rip; None when nothing restricts them (no map yet, or not a structure scan)."""
    title_map = title_map_of(scan)
    return None if title_map is None else frozenset(title_map.numbers)


def unrippable_refs(scan: ScanResult) -> frozenset[str]:
    """The refs MakeMKV did not list."""
    title_map = title_map_of(scan)
    return frozenset() if title_map is None else frozenset(title_map.unexposed)


def start_blocker(job: Job) -> str | None:
    """Why the rip cannot run yet, as the detail the ripper's rip-start answers with; None when it can. Only a
    structure scan without MakeMKV's titles is blocked: pending while MakeMKV reads, or failed."""
    scan = stored_scan(job)
    if scan is None or not is_structure_scan(scan) or scan.titles:
        return None
    failure = makemkv_failure(job)
    return TITLES_PENDING if failure is None else f"makemkv_failed: {failure.reason.value}"


def titles_read_view(job: Job) -> TitlesReadView:
    """The card's view of MakeMKV's title read: ready, pending, or failed with the reason."""
    scan = stored_scan(job)
    if scan is None or not is_structure_scan(scan) or scan.titles:
        return TitlesReadView(state="ready")
    failure = makemkv_failure(job)
    return TitlesReadView(state="pending") if failure is None else TitlesReadView(state="failed", failure=failure)


def stereo_3d_refs(scan: ScanResult) -> frozenset[str]:
    """The refs of a structure scan's titles that play a 3D view."""
    if not is_structure_scan(scan):
        return frozenset()
    return frozenset(title_ref(t.source_file or "", t.angle) for t in scan_candidates(scan) if t.stereo_3d)


def job_stereo_3d_refs(job: Job) -> frozenset[str]:
    """`stereo_3d_refs` of the job's stored scan; empty when it has none."""
    scan = stored_scan(job)
    return frozenset() if scan is None else stereo_3d_refs(scan)


def keep_3d_refs(scan: ScanResult | None, tracks: Sequence[Track], prefers_3d: bool) -> list[str]:
    """The `source_ref`s of the rip's tracks whose MVC dependent view the ripper must keep: 3D titles of a job that
    keeps 3D (D60: no transcode), in track order. MakeMKV leaves the dependent view out unless told otherwise."""
    if scan is None or not prefers_3d:
        return []
    stereo = stereo_3d_refs(scan)
    return [t.source_ref for t in tracks if t.source_ref in stereo]


def title_numbers(scan: ScanResult | None, tracks: Sequence[Track]) -> dict[str, int]:
    """`source_ref` -> MakeMKV title number for the rip-start response: the title map's for a structure scan, else
    each numeric ref as itself."""
    title_map = None if scan is None else title_map_of(scan)
    if title_map is not None:
        return dict(title_map.numbers)
    return {t.source_ref: int(t.source_ref) for t in tracks if t.source_ref.isdigit()}


def _refresh_from_makemkv(tracks: Sequence[Track], title_map: TitleMap, titles: Sequence[ScanTitle]) -> set[str]:
    """Replace the structure's estimates with MakeMKV's size and playlist name; the ids of the tracks that changed."""
    by_number = {t.index: t for t in titles}
    changed: set[str] = set()
    for track in tracks:
        number = title_map.numbers.get(track.source_ref)
        if number is None:
            continue
        found = by_number[number]
        before = (track.expected_size_bytes, track.playlist_name)
        if found.size_bytes is not None:
            track.expected_size_bytes = found.size_bytes
        if found.playlist_name is not None:
            track.playlist_name = found.playlist_name
        if (track.expected_size_bytes, track.playlist_name) != before:
            changed.add(track.id)
    return changed


def _drop_unrippable(job: Job, tracks: Sequence[Track], title_map: TitleMap) -> None:
    """Unticks the refs MakeMKV cannot rip: the preset proposes their drop, and an operator tick made before the
    map arrived is withdrawn."""
    refs = [t.source_ref for t in tracks if t.source_ref in title_map.unexposed]
    if not refs:
        return
    record_preset_drop(job, refs, now=datetime.now(timezone.utc))
    for ref in refs:
        revert_manual_track(job, ref, ["excluded"])


async def map_onto_tracks(db: AsyncSession, job: Job, tracks: Sequence[Track], scan: ScanResult) -> set[str]:
    """Bring `tracks` in line with the scan's title map: MakeMKV's sizes and names, the refs it cannot rip unticked
    and the version ticks recomputed. The ids of the tracks that changed; none until MakeMKV's titles are in."""
    title_map = title_map_of(scan)
    if title_map is None:
        return set()
    refreshed = _refresh_from_makemkv(tracks, title_map, scan.titles)
    _drop_unrippable(job, tracks, title_map)
    refreshed |= await recompute_ticks(db, job, tracks, scan, rippable=frozenset(title_map.numbers))
    logger.info(
        "titles job_id=%s mapped=%d unexposed=%d makemkv_only=%d",
        job.id,
        len(title_map.numbers),
        len(title_map.unexposed),
        len(title_map.makemkv_only),
    )
    return refreshed


async def apply_titles_report(db: AsyncSession, hub: WSHub, job: Job, report: TitlesReport) -> None:
    """Store MakeMKV's titles (or why it failed) on the job, map them, and tell the card.

    Raises NotAStructureScan when the job's scan is not a structure scan.
    """
    scan = stored_scan(job)
    if scan is None or not is_structure_scan(scan):
        raise NotAStructureScan(job.id)
    metadata = {k: v for k, v in (job.metadata_json or {}).items() if k != MAKEMKV_FAILURE_KEY}
    if report.failure is not None:
        metadata[MAKEMKV_FAILURE_KEY] = report.failure.model_dump(mode="json")
        logger.warning(
            "titles job_id=%s: makemkv could not read the disc reason=%s detail=%s",
            job.id,
            report.failure.reason.value,
            report.failure.detail,
        )
    else:
        scan = scan.model_copy(update={"titles": report.titles})
        metadata["scan_result"] = scan.model_dump(mode="json")
    job.metadata_json = metadata
    db.add(job)
    tracks = list((await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    refreshed = await map_onto_tracks(db, job, tracks, scan)
    resolved = await resolve_job(db, job)
    await db.commit()
    outcome = ResolveOutcome(changed=resolved.changed, track_ids=resolved.track_ids | refreshed)
    await emit_identity_resolved(db, hub, job, outcome, sources={})
    await db.commit()
