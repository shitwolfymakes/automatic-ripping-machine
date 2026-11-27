"""Shared fixtures for the staging tests: a real aiosqlite database (a join, a Core UPDATE and a
row lock can't be expressed on `tests._fakes.FakeSession`), a recording hub, and seeding helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import arm_common.models  # noqa: F401  (populate SQLModel.metadata)
from arm_backend.config import Settings, settings as base_settings
from arm_common import DiscType, Job, JobStatus, StageStatus, Track, TrackKind, TrackStage, TrackStatus
from tests.e2e.test_dispatcher_real_session import _restore_column_types, _retype_pg_columns_to_json

JOB = "job_01JZXR7K3M5Q8N4VWA00000002"


@dataclass
class RecordingHub:
    """Stands in for `WSHub`: records every emit, in order."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    fail_progress: bool = False

    async def emit(self, topic: str, event_type: str, payload: dict[str, Any], **kwargs: Any) -> None:
        if self.fail_progress and event_type == "stage.progress":
            raise RuntimeError("ws down")
        self.calls.append({"topic": topic, "event_type": event_type, "payload": payload, **kwargs})

    def types(self) -> list[str]:
        return [c["event_type"] for c in self.calls]


@dataclass
class Env:
    factory: Callable[[], AsyncSession]
    settings: Settings
    raw: Path
    hub: RecordingHub


async def make_env(tmp_path: Path) -> tuple[Env, Callable[[], Any]]:
    """An engine on a fresh SQLite file plus settings rooted in `tmp_path`; returns the env and a closer."""
    saved = _retype_pg_columns_to_json()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/stage.db")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    raw = tmp_path / "raw"
    raw.mkdir()
    cfg = base_settings.model_copy(
        update={
            "RAW_ROOT": str(raw),
            "ARM_HOST_RAW_PATH": str(raw),
            "ARM_HOST_STAGING_PATH": "",
            "ARM_STAGE_STALL_SECONDS": 300,
            "ARM_STAGE_MAX_ATTEMPTS": 3,
        }
    )

    async def close() -> None:
        await engine.dispose()
        _restore_column_types(saved)

    return Env(factory=factory, settings=cfg, raw=raw, hub=RecordingHub()), close


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    environment, close = await make_env(tmp_path)
    try:
        yield environment
    finally:
        await close()


async def add_job(db: AsyncSession, job_id: str = JOB) -> None:
    db.add(
        Job(
            id=job_id,
            drive_id="drv_x",
            disc_type=DiscType.BLURAY,
            title="Iron Man",
            year=2008,
            status=JobStatus.RIPPED,
            metadata_json={},
        )
    )
    await db.flush()


async def add_track(
    env: Env,
    db: AsyncSession,
    track_id: str = "trk_a",
    *,
    content: bytes | None = b"ripped bytes",
    status: TrackStatus = TrackStatus.DONE,
    job_id: str = JOB,
    kind: TrackKind = TrackKind.VIDEO_TITLE,
) -> Track:
    """A track whose file (when `content` is given) sits at `<raw>/<job>/<track>.mkv`."""
    path = env.raw / job_id / f"{track_id}.mkv"
    if content is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    track = Track(
        id=track_id,
        job_id=job_id,
        kind=kind,
        index=1,
        source_ref="1",
        status=status,
        output_path=str(path) if content is not None else None,
    )
    db.add(track)
    await db.flush()
    return track


async def add_stage(
    env: Env,
    db: AsyncSession,
    track: Track,
    *,
    status: StageStatus = StageStatus.PENDING,
    **fields: Any,
) -> TrackStage:
    stage = TrackStage(
        track_id=track.id,
        job_id=track.job_id,
        status=status,
        source_path=str(track.output_path),
        dest_path=str(env.settings.RAW_ROOT + f"/.staging/{track.job_id}/{track.id}.mkv"),
        **fields,
    )
    db.add(stage)
    await db.flush()
    return stage


async def seed_stage(
    env: Env, *, status: StageStatus = StageStatus.PENDING, content: bytes | None = b"ripped bytes", **fields: Any
) -> str:
    """Seed a job, a DONE track and a stage row; returns the stage id."""
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db, content=content)
        stage = await add_stage(env, db, track, status=status, **fields)
        await db.commit()
        return stage.id


async def load_stage(env: Env, stage_id: str) -> TrackStage:
    async with env.factory() as db:
        stage = await db.get(TrackStage, stage_id)
        assert stage is not None
        return stage
