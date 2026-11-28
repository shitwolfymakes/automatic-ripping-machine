"""Real-session (aiosqlite) test that the identify review gate persists the
Blu-ray classifier's verdicts on the tracks and the job detail serves them."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import arm_common.models  # noqa: F401  (populate SQLModel.metadata)
from arm_backend import review_tracks
from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import jobs as jobs_router
from arm_common import (
    DiscType,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RipPreset,
    TrackSelection,
    User,
)
from arm_common.schemas import ScanResult, ScanTitle
from tests.e2e.test_dispatcher_real_session import (
    _restore_column_types,
    _retype_pg_columns_to_json,
)

_JOB = "job_01JZXR7K3M5Q8N4VWA00000003"
_DECOY_JSON = (
    Path(__file__).resolve().parents[4] / "packages/arm_common/tests/fixtures/scan_titles/bd_decoy_playlists.json"
)


async def test_review_tracks_carry_the_scan_fields_and_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = RipPreset(
        id="rpr_test",
        name="test",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )

    async def _preset(_db: AsyncSession, _job: Job) -> RipPreset:
        return preset

    monkeypatch.setattr(review_tracks, "resolve_rip_preset_for_job", _preset)
    titles = [ScanTitle.model_validate(t) for t in json.loads(_DECOY_JSON.read_text())]
    scan = ScanResult(disc_type=DiscType.BLURAY, titles=titles)

    saved_types = _retype_pg_columns_to_json()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as db:
            job = Job(
                id=_JOB,
                drive_id="drv_x",
                disc_type=DiscType.BLURAY,
                title="Disc",
                status=JobStatus.IDENTIFIED,
                metadata_json={},
            )
            db.add_all([User(id="usr_admin", username="admin", password_hash="x", password_must_change=False), job])
            await db.flush()
            await review_tracks.persist_review_tracks(db, job, scan)
            await db.commit()

        app = FastAPI()
        app.state.signing_key = secrets.token_bytes(32)
        app.include_router(jobs_router.router)

        async def _session() -> AsyncIterator[AsyncSession]:
            async with factory() as s:
                yield s

        app.dependency_overrides[get_session] = _session
        token, _ = issue_access_token("usr_admin", "admin", app.state.signing_key)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.get(f"/api/jobs/{_JOB}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
    finally:
        await engine.dispose()
        _restore_column_types(saved_types)

    tracks = {t["index"]: t for t in r.json()["tracks"]}
    assert len(tracks) == 309
    assert tracks[0]["title_class"] == "primary"
    assert tracks[0]["title_class_ref"] is None
    assert tracks[0]["source_file"] == "00202.mpls"
    assert tracks[0]["playlist_name"] == "FPL_MainFeature"
    assert tracks[2]["title_class"] == "variant"
    assert tracks[2]["title_class_ref"] == "0"
    assert sum(t["title_class"] == "decoy" for t in tracks.values()) == 298
