"""Phase 7b: complete/fail handlers must release the claimed GPU.

When a task moves to a terminal state, any `gpus.claimed_by_task_id` row
matching that task is flipped back to AVAILABLE so a queued sibling task
can pick it up on the next dispatcher tick.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import AsyncIterator

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import transcoder as transcoder_router  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    DiscType,
    Gpu,
    GpuStatus,
    GpuVendor,
    Job,
    JobStatus,
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)
from tests._fakes import FakeSession  # noqa: E402

_HOSTNAME = "arm-transcode-abc123"
_SERVICE_AUTH = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": _HOSTNAME}


def _seed_running_task_with_claimed_gpu(db: FakeSession) -> None:
    db.rows["jobs"] = [
        Job(
            id="job_x",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title="X",
            year=2020,
            status=JobStatus.RIPPED,
            metadata_json={},
        )
    ]
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_x",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="X (2020)/X.mkv",
            attempts=1,
            progress_pct=80,
            claimed_by=_HOSTNAME,
            claim_heartbeat_at=datetime.now(UTC),
        )
    ]
    db.rows["gpus"] = [
        Gpu(
            id="gpu_1",
            vendor=GpuVendor.VAAPI,
            device_path="/dev/dri/renderD128",
            encoder_kinds=["h264", "h265"],
            status=GpuStatus.BUSY,
            claimed_by_task_id="txt_1",
        )
    ]


def _make_app(db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.ws_hub = WSHub()
    app.include_router(transcoder_router.router)

    async def _override() -> AsyncIterator[FakeSession]:
        yield db

    app.dependency_overrides[get_session] = _override
    return app


def test_complete_releases_gpu() -> None:
    db = FakeSession()
    _seed_running_task_with_claimed_gpu(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/complete",
            json={"output_path": "X (2020)/X.mkv", "size_bytes": 1024000},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    gpu = db.rows["gpus"][0]
    assert gpu.status == GpuStatus.AVAILABLE
    assert gpu.claimed_by_task_id is None


def test_fail_releases_gpu() -> None:
    db = FakeSession()
    _seed_running_task_with_claimed_gpu(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/fail",
            json={"last_error": "GPU vanished mid-encode"},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    gpu = db.rows["gpus"][0]
    assert gpu.status == GpuStatus.AVAILABLE
    assert gpu.claimed_by_task_id is None
