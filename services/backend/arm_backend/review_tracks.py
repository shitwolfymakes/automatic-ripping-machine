"""The Track rows a disc held for review shows on its card: every scanned title, the preset's picks ticked (or, for a
disc that missed identification, the titles the miss defaults keep)."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.identity.proposals import preferred_titles, record_preset
from arm_backend.rip_preset_resolution import RipPresetUnavailable, resolve_rip_preset_for_job
from arm_backend.title_map_service import map_onto_tracks
from arm_backend.track_selection import DiscBackupNeedsBluray, select_tracks_for_review, select_tracks_on_miss
from arm_backend.version_policy import selection_policy
from arm_common import Job, RipPreset
from arm_common.enums import MissTitlesKept
from arm_common.models import Track
from arm_common.schemas import ScanResult

logger = logging.getLogger("arm_backend.identify_flow")


async def persist_review_tracks(db: AsyncSession, job: Job, scan: ScanResult) -> None:
    """Persist the scan's titles as Track rows for the timed review gate."""
    await _persist_tracks(
        db, job, scan, lambda preset, policy: select_tracks_for_review(job.id, scan, preset, **policy)
    )


async def persist_miss_tracks(db: AsyncSession, job: Job, scan: ScanResult, titles_kept: MissTitlesKept) -> None:
    """Persist the scan's titles as Track rows for a disc that missed identification."""
    await _persist_tracks(
        db, job, scan, lambda preset, policy: select_tracks_on_miss(job.id, scan, preset, titles_kept, **policy)
    )


async def _persist_tracks(
    db: AsyncSession, job: Job, scan: ScanResult, pick: Callable[[RipPreset, dict[str, Any]], list[Track]]
) -> None:
    """Persist the titles `pick` picks under the job's routed rip preset and selection policy as Track rows.

    Uses the default rip preset for the disc type to compute keep/drop defaults
    (`excluded`); the operator overrides per title in review. Idempotent on
    `(job_id, source_ref)` so a ripper re-POST of identify on the same held disc
    doesn't double-insert — Track rows have no unique constraint. A structure
    scan whose MakeMKV titles are already in (a disc held after the operator
    identified it) gets the title map at once, as a card held at identify gets
    it when the titles arrive.
    """
    try:
        preset = await resolve_rip_preset_for_job(db, job)
    except RipPresetUnavailable as exc:
        logger.warning("skipping review tracks for job_id=%s: %s", job.id, exc.detail)
        return
    existing = list((await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    existing_refs = {t.source_ref for t in existing}
    added: list[Track] = []
    try:
        review_tracks = pick(preset, {"preferred": preferred_titles(job), **await selection_policy(db, job)})
    except DiscBackupNeedsBluray as exc:
        logger.warning("skipping review tracks for job_id=%s: %s", job.id, exc)
        return
    for track in review_tracks:
        if track.source_ref in existing_refs:
            continue
        db.add(track)
        added.append(track)
    if added:
        record_preset(job, added, now=datetime.now(timezone.utc))
        await map_onto_tracks(db, job, existing + added, scan)
    await db.flush()
