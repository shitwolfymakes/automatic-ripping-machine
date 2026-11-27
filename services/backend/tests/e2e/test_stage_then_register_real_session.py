"""Real-session (aiosqlite) walk through the staging gate: a fan-out queues a stage row, the dispatcher skips
the task until the copy is STAGED, and `/register` then returns the staged path.

The copy itself is faked by flipping the row to STAGED; `tests/test_stager*.py` cover the real copier."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_backend import auto_session
from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.routers import transcoder as transcoder_router
from arm_backend.transcode_apply import ResolvedTask
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.ws import WSHub
from arm_common import (
    ContainerFormat,
    MediaType,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    StageStatus,
    TrackStage,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
)
from tests._stage_env import JOB, Env, add_job, add_track

_PRESET = TranscodePreset(
    id="tpr_enc",
    name="Plex 1080p",
    media_type=MediaType.MOVIE,
    is_builtin=True,
    tool=TranscodeTool.HANDBRAKE,
    preset_ref="H.265 MKV 1080p30",
    container=ContainerFormat.MKV,
    encoder="preset",
)
_AUTH = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": "arm-transcode-e2e"}


async def _fan_out(env: Env) -> None:
    """The rows `apply` leaves behind for one encode task, with its stage queued the way fan-out queues it."""
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        db.add_all(
            [
                _PRESET,
                Session(
                    id="ses_enc",
                    name="Movie to Plex",
                    media_type=MediaType.MOVIE,
                    is_builtin=True,
                    rip_preset_id="rpr",
                    transcode_preset_id="tpr_enc",
                    output_path_template="{title}.mkv",
                ),
                SessionApplication(
                    id="sap_enc",
                    session_id="ses_enc",
                    job_id=JOB,
                    status=SessionApplicationStatus.QUEUED,
                    overwrite=False,
                ),
                TranscodeTask(
                    id="txt_enc",
                    session_application_id="sap_enc",
                    source_track_id=track.id,
                    status=TranscodeTaskStatus.QUEUED,
                    attempts=0,
                    progress_pct=0,
                    output_path="Movie/Movie.mkv",
                ),
            ]
        )
        await auto_session._stage_resolved_tracks(db, env.hub, _PRESET, [track], [ResolvedTask(track.id, "Movie.mkv")])  # type: ignore[arg-type]
        await db.commit()


def _client(env: Env) -> TestClient:
    app = FastAPI()
    app.state.ws_hub = WSHub()
    app.state.handbrake_schema_store = SchemaStore()
    app.include_router(transcoder_router.router)

    async def _session() -> AsyncIterator[AsyncSession]:
        async with env.factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


async def test_a_task_is_skipped_until_staged_and_then_registers_the_staged_path(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auto_session, "settings", env.settings)
    monkeypatch.setattr(auto_session, "wake_active_stager", lambda: None)
    monkeypatch.setattr(transcoder_router, "request_settings", lambda: env.settings)
    await _fan_out(env)
    cfg = env.settings.model_copy(
        update={
            "ARM_HOST_MEDIA_PATH": "/media",
            "ARM_HOST_LOGS_PATH": "/logs",
            "ARM_HOST_CERTS_PATH": "/certs",
            "ARM_TRANSCODE_IMAGE": "arm-transcode:latest",
            "ARM_TRANSCODE_BACKEND_URL": "",
            "ARM_TRANSCODE_DOCKER_HOST": "",
            "MAX_PARALLEL_TRANSCODES": 2,
        }
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(cfg, env.factory, docker, WSHub())  # type: ignore[arg-type]

    async with env.factory() as db:
        stage = (await db.execute(select(TrackStage))).scalar_one()
        assert stage.status == StageStatus.PENDING
        assert await disp.spawn_pending(db) == 0
    docker.containers.run.assert_not_called()

    with _client(env) as client:
        body = {"task_id": "txt_enc", "hostname": "arm-transcode-e2e", "hw_caps": {"cpu_count": 4}}
        assert client.post("/api/transcoder/register", json=body, headers=_AUTH).status_code == 409

        async with env.factory() as db:  # the copy lands
            row = (await db.execute(select(TrackStage))).scalar_one()
            row.status = StageStatus.STAGED
            await db.commit()

        registered = client.post("/api/transcoder/register", json=body, headers=_AUTH)
        assert registered.status_code == 200, registered.text
        assert registered.json()["source_path"] == f"/staging/{JOB}/trk_a.mkv"

    async with env.factory() as db:
        assert await disp.spawn_pending(db) == 1
    docker.containers.run.assert_called_once()
