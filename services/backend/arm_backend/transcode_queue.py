"""Read-only queries over the transcode queue.

The parallelism cap, the preset a task runs with, and the encode backlog.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_common import (
    Config,
    Session,
    SessionApplication,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
)


async def max_parallel_transcodes(db: AsyncSession, *, default: int | None = None) -> int:
    """The dispatcher parallelism cap from operator config (Settings >
    Transcoding). Falls back to `default` (the caller's env-derived value)
    only while the config row predates the column (the seeder backfills it
    on the next boot)."""

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None or cfg.max_parallel_transcodes is None:
        return default if default is not None else settings.MAX_PARALLEL_TRANSCODES
    return cfg.max_parallel_transcodes


async def resolve_preset_for_task(db: AsyncSession, task: TranscodeTask) -> TranscodePreset | None:
    """The preset a task runs with: its application's session's preset."""
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one_or_none()
    if application is None:
        return None
    sess = (await db.execute(select(Session).where(col(Session.id) == application.session_id))).scalar_one_or_none()
    if sess is None or sess.transcode_preset_id is None:
        return None
    return (
        await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
    ).scalar_one_or_none()


async def count_queued_encode_tasks(db: AsyncSession) -> int:
    """QUEUED tasks that need an encoder (not a passthrough move). On a box
    that cannot transcode these are held by `spawn_pending` indefinitely."""
    from arm_backend.transcode_apply import is_passthrough_preset

    # One query per table, not per task: the Transcoder page polls this.
    queued = (
        (await db.execute(select(TranscodeTask).where(col(TranscodeTask.status) == TranscodeTaskStatus.QUEUED)))
        .scalars()
        .all()
    )
    if not queued:
        return 0
    app_ids = {task.session_application_id for task in queued}
    session_by_app = {
        app.id: app.session_id
        for app in (await db.execute(select(SessionApplication).where(col(SessionApplication.id).in_(app_ids))))
        .scalars()
        .all()
    }
    preset_by_session = {
        sess.id: sess.transcode_preset_id
        for sess in (await db.execute(select(Session).where(col(Session.id).in_(set(session_by_app.values())))))
        .scalars()
        .all()
    }
    preset_ids = {pid for pid in preset_by_session.values() if pid is not None}
    presets = {
        preset.id: preset
        for preset in (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id).in_(preset_ids))))
        .scalars()
        .all()
    }
    count = 0
    for task in queued:
        session_id = session_by_app.get(task.session_application_id)
        preset_id = preset_by_session.get(session_id) if session_id is not None else None
        if not is_passthrough_preset(presets.get(preset_id) if preset_id is not None else None):
            count += 1
    return count
