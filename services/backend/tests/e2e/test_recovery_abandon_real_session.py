"""Real-session (aiosqlite) test for `POST /api/ripper/jobs/{id}/recovery-abandon`.

The ripper calls this at boot for a held disc that was counting down when it
restarted, so the drive frees and the seated disc re-enters review. A request
session that is never committed rolls back when the request ends, which
`tests._fakes.FakeSession` cannot show: here the abandon is read back from a
fresh session after the request has finished.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select

import arm_common.models  # noqa: F401  (populate SQLModel.metadata)
from arm_backend.db import get_session
from arm_backend.routers import ripper as ripper_router
from arm_backend.ws import WSHub
from arm_common import DiscType, Job, JobStatus, SessionApplication, SessionApplicationStatus
from arm_common.models import Event
from tests.e2e.test_dispatcher_real_session import (
    _restore_column_types,
    _retype_pg_columns_to_json,
)

_JOB = "job_01JZXR7K3M5Q8N4VWA0000H05"
_SERVICE_AUTH = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": "arm-ripper-x"}


async def test_recovery_abandon_is_saved_after_the_request_ends(tmp_path: Path) -> None:
    saved_types = _retype_pg_columns_to_json()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as db:
            db.add_all(
                [
                    Job(
                        id=_JOB,
                        drive_id="drv_x",
                        disc_type=DiscType.DVD,
                        title="X",
                        year=2000,
                        status=JobStatus.AWAITING_REVIEW,
                        metadata_json={},
                    ),
                    SessionApplication(
                        id="sap_parked",
                        session_id="ses_x",
                        job_id=_JOB,
                        status=SessionApplicationStatus.WAITING_IDENTIFY,
                        overwrite=False,
                    ),
                ]
            )
            await db.commit()

        app = FastAPI()
        app.state.ws_hub = WSHub()
        app.include_router(ripper_router.router)

        async def _session() -> AsyncIterator[AsyncSession]:
            async with factory() as s:
                yield s

        app.dependency_overrides[get_session] = _session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(f"/api/ripper/jobs/{_JOB}/recovery-abandon", headers=_SERVICE_AUTH)
        assert r.status_code == 200, r.text

        async with factory() as db:
            job = (await db.execute(select(Job).where(col(Job.id) == _JOB))).scalar_one()
            application = (
                await db.execute(select(SessionApplication).where(col(SessionApplication.id) == "sap_parked"))
            ).scalar_one()
            events = (await db.execute(select(Event).where(col(Event.job_id) == _JOB))).scalars().all()
    finally:
        await engine.dispose()
        _restore_column_types(saved_types)

    assert job.status == JobStatus.ABANDONED
    assert application.status != SessionApplicationStatus.WAITING_IDENTIFY
    assert [e.event_type for e in events] == ["rip.abandoned"]
