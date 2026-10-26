"""Real-session (aiosqlite) regression test for the parked-application drain
after a failed fan-out (D-065).

A real `AsyncSession.rollback()` expires every loaded instance
(`expire_on_commit=False` does not cover rollback), and reading an expired
attribute outside an awaited load raises `MissingGreenlet`. FakeSession's
no-op rollback cannot show this, hence a real session here, as in
`test_dispatcher_real_session.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import arm_common.models  # noqa: F401  (populate SQLModel.metadata)
from arm_backend import auto_session
from arm_backend.routers import config as config_router
from arm_common import DiscType, Job, JobStatus, SessionApplication, SessionApplicationStatus


def _retype_pg_columns_to_json() -> list[tuple[object, object]]:
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


async def test_redrain_survives_a_failed_job_and_drains_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-065: the first job's fan-out fails and its drain rolls back. The log
    line must not read the expired job, the PATCH path must not raise, and
    the second parked job is still re-drained."""
    saved_types = _retype_pg_columns_to_json()
    try:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with factory() as db:
                for n in (1, 2):
                    db.add(Job(id=f"job_{n}", drive_id=None, disc_type=DiscType.DVD, status=JobStatus.RIPPED))
                    db.add(
                        SessionApplication(
                            id=f"sap_{n}",
                            session_id="ses_x",
                            job_id=f"job_{n}",
                            status=SessionApplicationStatus.WAITING_IDENTIFY,
                            overwrite=False,
                        )
                    )
                await db.commit()

            drained: list[str] = []

            async def fan_out(db: AsyncSession, *, job: Job, hub: Any) -> list[Any]:
                drained.append(job.id)
                if job.id == "job_1":
                    job.title = "dirty"  # something to roll back
                    await db.flush()
                    raise RuntimeError("fan-out failed")
                return []

            monkeypatch.setattr(auto_session, "fan_out_waiting_identify_applications", fan_out)
            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(ws_hub=None)))
            async with factory() as db:
                await config_router._redrain_parked_applications(db, request)  # type: ignore[arg-type]
                assert drained == ["job_1", "job_2"]
                # The failed job was reloaded, not left expired: reading it is safe.
                job_1 = (await db.execute(select(Job).where(Job.id == "job_1"))).scalar_one()
                assert job_1.title is None
        finally:
            await engine.dispose()
    finally:
        _restore_column_types(saved_types)


async def test_after_rip_keeps_using_the_job_after_a_failed_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-065: after_rip goes on to the auto-apply half with the same job
    object the failed drain rolled back; it must have been reloaded."""
    saved_types = _retype_pg_columns_to_json()
    try:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/y.db")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with factory() as db:
                db.add(Job(id="job_1", drive_id=None, disc_type=DiscType.DVD, status=JobStatus.RIPPED))
                await db.commit()

            async def fan_out(db: AsyncSession, *, job: Job, hub: Any) -> list[Any]:
                raise RuntimeError("fan-out failed")

            seen: list[str] = []

            async def auto_apply(db: AsyncSession, job: Job, hub: Any) -> None:
                seen.append(job.id)  # a plain attribute read on the reloaded job

            monkeypatch.setattr(auto_session, "fan_out_waiting_identify_applications", fan_out)
            monkeypatch.setattr(auto_session, "maybe_auto_apply_session", auto_apply)
            async with factory() as db:
                job = (await db.execute(select(Job).where(Job.id == "job_1"))).scalar_one()
                assert await auto_session.after_rip(db, job, None) == []  # type: ignore[arg-type]
            assert seen == ["job_1"]
        finally:
            await engine.dispose()
    finally:
        _restore_column_types(saved_types)
