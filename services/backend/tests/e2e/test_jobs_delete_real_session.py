"""Real-session (aiosqlite) test for `DELETE /api/jobs/{id}?delete_raw=true`.

`_resolve_media_outputs` joins `transcode_tasks` to `tracks` and filters on
status; `tests._fakes.FakeSession` can express neither a join nor an
`IS NOT NULL`, so the query is pinned here against a real engine.

The hazard: a task's `output_path` is recorded at fan-out, before the file
lands. A disc backup task whose move was refused (its destination folder
already existed: another job's, or the user's) ends FAILED still naming
that folder. Deleting the failed job with its files must not remove it.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import arm_common.models  # noqa: E402,F401  (populate SQLModel.metadata)
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import (  # noqa: E402
    DiscType,
    Job,
    JobStatus,
    Track,
    TrackKind,
    TranscodeTask,
    TranscodeTaskStatus,
    User,
)
from tests.e2e.test_dispatcher_real_session import (  # noqa: E402
    _restore_column_types,
    _retype_pg_columns_to_json,
)

_JOB = "job_01JZXR7K3M5Q8N4VWA00000002"


async def test_deleting_a_failed_backup_job_keeps_the_folder_it_never_filed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_root = tmp_path / "raw"
    (raw_root / _JOB).mkdir(parents=True)
    media_root = tmp_path / "media"
    # Pre-existing library folder: the move was refused onto it.
    foreign = media_root / "Iron Man (2008)"
    (foreign / "BDMV").mkdir(parents=True)
    (foreign / "BDMV" / "index.bdmv").write_bytes(b"theirs")
    # A finished output of the same job is still removed.
    done_file = media_root / "Extras" / "extra.mkv"
    done_file.parent.mkdir(parents=True)
    done_file.write_bytes(b"ours")
    monkeypatch.setattr(jobs_router.settings, "RAW_ROOT", str(raw_root))
    monkeypatch.setattr(jobs_router.settings, "MEDIA_ROOT", str(media_root))

    saved_types = _retype_pg_columns_to_json()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as db:
            db.add_all(
                [
                    User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
                    Job(
                        id=_JOB,
                        drive_id="drv_x",
                        disc_type=DiscType.BLURAY,
                        title="Iron Man",
                        year=2008,
                        status=JobStatus.RIPPED,
                        metadata_json={},
                    ),
                    Track(id="trk_b", job_id=_JOB, kind=TrackKind.DISC_BACKUP, index=1, source_ref="backup"),
                    Track(id="trk_e", job_id=_JOB, kind=TrackKind.VIDEO_TITLE, index=2, source_ref="2"),
                    TranscodeTask(
                        id="txt_failed",
                        session_application_id="sap_x",
                        source_track_id="trk_b",
                        status=TranscodeTaskStatus.FAILED,
                        attempts=1,
                        progress_pct=0,
                        output_path="Iron Man (2008)",
                    ),
                    TranscodeTask(
                        id="txt_done",
                        session_application_id="sap_x",
                        source_track_id="trk_e",
                        status=TranscodeTaskStatus.DONE,
                        attempts=1,
                        progress_pct=100,
                        output_path="Extras/extra.mkv",
                    ),
                ]
            )
            await db.commit()

        async with factory() as db:
            outputs = await jobs_router._resolve_media_outputs(db, _JOB)
        assert outputs == [media_root / "Extras" / "extra.mkv"]

        app = FastAPI()
        app.state.signing_key = secrets.token_bytes(32)
        app.include_router(jobs_router.router)

        async def _session() -> AsyncIterator[AsyncSession]:
            async with factory() as s:
                yield s

        app.dependency_overrides[get_session] = _session
        token, _ = issue_access_token("usr_admin", "admin", app.state.signing_key)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.delete(f"/api/jobs/{_JOB}?delete_raw=true", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 204, r.text
    finally:
        await engine.dispose()
        _restore_column_types(saved_types)

    assert (foreign / "BDMV" / "index.bdmv").read_bytes() == b"theirs"
    assert not done_file.exists()
    assert not (raw_root / _JOB).exists()
