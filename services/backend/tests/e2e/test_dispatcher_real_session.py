"""Real-session (aiosqlite) regression test for `spawn_pending`'s
stale-identity-map hazard.

`tests._fakes.FakeSession` cannot express SQLAlchemy's real
expire-on-rollback / identity-map-staleness semantics: its `rollback()` is
a no-op and every `select()` just re-reads whatever is currently sitting in
its plain Python dict, so it can never reproduce what a real
`AsyncSession` does after a `rollback()` mid-tick. The bug this test pins:

    A persistently-failing encode spawn (missing image, dead SSH host,
    ...) makes `spawn_pending`'s encode `except` block call
    `await db.rollback()`. That expires every object in the session's
    identity map -- including the batch-select `TranscodeTask` objects the
    `for task in queued:` loop was still iterating. The very next
    iteration's `task.session_application_id` attribute read (on an
    expired object) triggers an async lazy load outside any `await` we
    control, raising `sqlalchemy.exc.MissingGreenlet` -- unprotected,
    aborting `spawn_pending`, the tick, and (via `_tick`'s
    `async with self._db_factory() as db:`) rolling back the whole tick's
    session. A passthrough task queued behind the failing encode task
    would then NEVER run, breaking the feature's core promise (passthrough
    always runs, independent of encode's health).

The fix (see `transcode_dispatcher.py::spawn_pending`) re-loads each row
fresh, locked, and `populate_existing`-forced at the top of every
iteration instead of reusing the batch-select object, so this is exactly
the scenario a fake session's no-op rollback hides and only a real,
started `AsyncSession` reproduces.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from sqlalchemy import JSON  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlmodel import SQLModel, select  # noqa: E402

import arm_common.models  # noqa: E402,F401  (populate SQLModel.metadata)
from arm_backend.config import Settings  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    MediaType,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
)
from arm_common.enums import TrackKind  # noqa: E402


def _retype_pg_columns_to_json() -> list[tuple[object, object]]:
    """Duplicated from `tests/e2e/conftest.py`'s helper of the same name,
    kept self-contained here rather than importing another test module's
    internals. Swaps Postgres-only `JSONB`/`ARRAY` column *types* to plain
    `JSON` in the live, process-global `SQLModel.metadata` so SQLite gets a
    working bind/result processor. Must run before the ORM mapper compiles
    its first statement against this engine; the caller restores the
    originals on teardown."""
    saved: list[tuple[object, object]] = []
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, (JSONB, ARRAY)):
                saved.append((column, column.type))
                column.type = JSON()
    return saved


def _restore_column_types(saved: list[tuple[object, object]]) -> None:
    for column, original in saved:
        column.type = original  # type: ignore[attr-defined]


async def test_persistently_failing_encode_spawn_does_not_abort_passthrough(tmp_path: Path) -> None:
    """The scenario the reviewer's repro pinned: an encode task queued
    ahead of a passthrough task, with `docker.containers.run` raising on
    every attempt (a missing image, an unreachable remote host, ...).

    `spawn_pending` must not raise, the encode task stays `QUEUED` (never
    successfully spawned; it's retried on later ticks), and the passthrough
    task behind it still completes -- it must never be blocked by an
    unrelated encode task's persistent failure.
    """
    saved_types = _retype_pg_columns_to_json()
    try:
        db_dir = tmp_path
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_dir}/x.db")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

            raw = db_dir / "raw" / "p.mkv"
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"passthrough-data")
            now = datetime.now(UTC)

            async with session_factory() as db:
                db.add_all(
                    [
                        TranscodePreset(
                            id="tpr_enc",
                            name="enc",
                            media_type=MediaType.MOVIE,
                            is_builtin=True,
                            tool=TranscodeTool.HANDBRAKE,
                            preset_ref="x",
                            container=ContainerFormat.MKV,
                        ),
                        TranscodePreset(
                            id="tpr_none",
                            name="none",
                            media_type=MediaType.MOVIE,
                            is_builtin=True,
                            tool=TranscodeTool.NONE,
                            preset_ref="",
                            container=ContainerFormat.MKV,
                        ),
                        Session(
                            id="ses_enc",
                            name="Movie to Plex",
                            media_type=MediaType.MOVIE,
                            is_builtin=True,
                            rip_preset_id="rpr",
                            transcode_preset_id="tpr_enc",
                            output_path_template="{title}.mkv",
                        ),
                        Session(
                            id="ses_pt",
                            name="ISO dump",
                            media_type=MediaType.MOVIE,
                            is_builtin=True,
                            rip_preset_id="rpr",
                            transcode_preset_id="tpr_none",
                            output_path_template="{title}.mkv",
                        ),
                        SessionApplication(
                            id="sap_enc",
                            session_id="ses_enc",
                            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
                            status=SessionApplicationStatus.QUEUED,
                            overwrite=False,
                        ),
                        SessionApplication(
                            id="sap_pt",
                            session_id="ses_pt",
                            job_id="job_01JZXR7K3M5Q8N4VWA00000002",
                            status=SessionApplicationStatus.QUEUED,
                            overwrite=False,
                        ),
                        Track(
                            id="trk_p",
                            job_id="job_01JZXR7K3M5Q8N4VWA00000002",
                            kind=TrackKind.VIDEO_TITLE,
                            index=1,
                            source_ref="t0",
                            output_path=str(raw),
                        ),
                        TranscodeTask(
                            id="txt_enc",
                            session_application_id="sap_enc",
                            source_track_id="trk_e",
                            status=TranscodeTaskStatus.QUEUED,
                            attempts=0,
                            progress_pct=0,
                            output_path="Movie (2020)/Movie.mkv",
                            created_at=now,
                        ),
                        TranscodeTask(
                            id="txt_pt",
                            session_application_id="sap_pt",
                            source_track_id="trk_p",
                            status=TranscodeTaskStatus.QUEUED,
                            attempts=0,
                            progress_pct=0,
                            output_path="Docs/p.mkv",
                            created_at=now + timedelta(seconds=1),
                        ),
                    ]
                )
                await db.commit()

            settings = Settings.model_construct(
                DATABASE_URL="x",
                ARM_SERVICE_TOKEN="tok-service",
                MAX_PARALLEL_TRANSCODES=2,
                ARM_TRANSCODE_IMAGE="arm-transcode:latest",
                ARM_HOST_RAW_PATH="/raw",
                ARM_HOST_MEDIA_PATH="/media",
                ARM_HOST_LOGS_PATH="/logs",
                ARM_HOST_CERTS_PATH="/certs",
                ARM_DOCKER_NETWORK="armv3_default",
                ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS=5,
                MEDIA_ROOT=str(db_dir / "media"),
                ARM_TRANSCODE_DOCKER_HOST="",
                ARM_TRANSCODE_BACKEND_URL="",
                ARM_LOG_LEVEL="INFO",
                ARM_TRANSCODE_PUID="",
                ARM_TRANSCODE_PGID="",
                ARM_RENDER_GID="",
            )
            docker = MagicMock()
            docker.containers.run.side_effect = RuntimeError("image not found")
            disp = TranscodeDispatcher(settings, session_factory, docker, WSHub())

            async with session_factory() as db:
                spawned = await disp.spawn_pending(db)  # must not raise

            assert spawned == 0

            async with session_factory() as db:
                enc = (await db.execute(select(TranscodeTask).where(TranscodeTask.id == "txt_enc"))).scalar_one()
                pt = (await db.execute(select(TranscodeTask).where(TranscodeTask.id == "txt_pt"))).scalar_one()

            # The encode task's spawn attempt failed every time (docker
            # always raises); it stays QUEUED for a later tick to retry.
            assert enc.status == TranscodeTaskStatus.QUEUED
            # The passthrough task queued behind it was never blocked.
            assert pt.status == TranscodeTaskStatus.DONE
        finally:
            await engine.dispose()
    finally:
        _restore_column_types(saved_types)
