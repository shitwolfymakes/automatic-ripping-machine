"""Stage rows: the DB side of copying ripped tracks from /raw into staging.

Pure DB helpers. The copy itself is `arm_backend.stager`."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import Settings, staging_root
from arm_common import StageStatus, Track, TrackKind, TrackStage
from arm_common.models._columns import enum_value_str

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.staging")

STAGING_EVENTS_TOPIC = "staging.events"


def dest_path_for(settings: Settings, track: Track) -> Path:
    """`<staging root>/<job_id>/<the track's path under its raw job dir>`.

    Raises ValueError when the track has no output path or it lies outside `<raw>/<job_id>`."""
    if not track.output_path:
        raise ValueError(f"track {track.id} has no output_path")
    relative = Path(track.output_path).relative_to(Path(settings.RAW_ROOT) / track.job_id)
    return staging_root(settings) / track.job_id / relative


def stage_payload(stage: TrackStage) -> dict[str, Any]:
    """The payload every `staging.events` event carries."""
    return {
        "track_id": stage.track_id,
        "job_id": stage.job_id,
        "stage_id": stage.id,
        "status": enum_value_str(stage.status),
        "attempts": stage.attempts,
        "last_error": stage.last_error,
        "bytes_durable": stage.bytes_durable,
        "linked": stage.linked,
    }


async def emit_stage_event(hub: WSHub, db: AsyncSession, event_type: str, stage: TrackStage) -> None:
    """Persist and publish a `staging.events` event for `stage` on `db`'s transaction."""
    await hub.emit(
        topic=STAGING_EVENTS_TOPIC,
        event_type=event_type,
        payload=stage_payload(stage),
        job_id=stage.job_id,
        track_id=stage.track_id,
        session=db,
    )


async def stage_for_track(db: AsyncSession, track_id: str) -> TrackStage | None:
    """The track's stage row, if it has one."""
    return (await db.execute(select(TrackStage).where(col(TrackStage.track_id) == track_id))).scalar_one_or_none()


def _new_stage_row(settings: Settings, track: Track) -> TrackStage | None:
    """A PENDING row for `track`, or None when the track can't be staged (no file, a folder, a stray path)."""
    if not track.output_path or track.kind == TrackKind.DISC_BACKUP:
        return None
    try:
        dest = dest_path_for(settings, track)
    except ValueError:
        logger.warning("stage skipped track_id=%s: output_path %s is outside its raw dir", track.id, track.output_path)
        return None
    return TrackStage(
        track_id=track.id,
        job_id=track.job_id,
        status=StageStatus.PENDING,
        source_path=track.output_path,
        dest_path=str(dest),
    )


async def _staged_track_ids(db: AsyncSession, track_ids: list[str]) -> set[str]:
    """The ids among `track_ids` that already have a stage row, whatever its status."""
    rows = await db.execute(select(TrackStage.track_id).where(col(TrackStage.track_id).in_(track_ids)))
    return {str(r) for r in rows.scalars().all()}


async def ensure_stage_rows(
    db: AsyncSession, settings: Settings, tracks: Sequence[Track], hub: WSHub | None = None
) -> list[TrackStage]:
    """Insert a PENDING row for each track that has none; existing rows (any status) are left alone.

    Skips tracks without an output file. Flushes and emits `stage.queued` per new row; does not commit.
    Returns the rows it created."""
    existing = await _staged_track_ids(db, [t.id for t in tracks])
    created = [row for t in tracks if t.id not in existing and (row := _new_stage_row(settings, t)) is not None]
    if not created:
        return []
    db.add_all(created)
    await db.flush()
    if hub is not None:
        for stage in created:
            await emit_stage_event(hub, db, "stage.queued", stage)
    return created
