"""The end-on-completion setting reaches the ripper on the rip-start and resume responses, resolved per request: the
drive's override over the global, NULL on the drive following it."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.routers import ripper as ripper_router
from arm_common import (
    Config,
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    RetentionPolicy,
    Track,
    TrackKind,
    TrackStatus,
)

from tests._fakes import FakeSession

_JOB = "job_01JZXR7K3M5Q8N4VWA00000001"
_HEADERS = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": "ripper-host"}


class _Hub:
    async def emit(self, *_a: object, **_k: object) -> None:
        return None


def _db(*, global_value: bool, drive_value: bool | None, status: JobStatus, with_config: bool = True) -> FakeSession:
    db = FakeSession()
    db.rows["config"] = (
        [
            Config(
                id=1,
                auto_transcode_on_idle=False,
                auto_rip_on_insert=True,
                block_on_miss=True,
                rip_end_on_completion_message=global_value,
                default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            )
        ]
        if with_config
        else []
    )
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="ripper-host",
            device_path="/dev/sr0",
            status=DriveStatus.ONLINE,
            rip_end_on_completion_message=drive_value,
        )
    ]
    db.rows["jobs"] = [
        Job(id=_JOB, drive_id="drv_x", disc_type=DiscType.DVD, title="X", year=2000, status=status, metadata_json={})
    ]
    db.rows["tracks"] = [
        Track(
            id="trk_1",
            job_id=_JOB,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
            status=TrackStatus.QUEUED if status is JobStatus.AWAITING_REVIEW else TrackStatus.IN_PROGRESS,
            attempts=1,
        )
    ]
    return db


def _post(db: FakeSession, path: str) -> dict:
    app = FastAPI()
    app.state.ws_hub = _Hub()
    app.include_router(ripper_router.router)

    async def _session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as client:
        r = client.post(f"/api/ripper/jobs/{_JOB}/{path}", headers=_HEADERS)
    assert r.status_code == 200, r.text
    body: dict = r.json()
    return body


_CASES = [
    (False, None, False),
    (True, None, True),
    (False, True, True),
    (True, False, False),
]


@pytest.mark.parametrize(("global_value", "drive_value", "expected"), _CASES)
def test_rip_start_of_a_held_job_carries_the_resolved_setting(global_value, drive_value, expected) -> None:
    db = _db(global_value=global_value, drive_value=drive_value, status=JobStatus.AWAITING_REVIEW)
    assert _post(db, "rip-start")["end_on_completion_message"] is expected


@pytest.mark.parametrize(("global_value", "drive_value", "expected"), _CASES)
def test_resume_carries_the_resolved_setting(global_value, drive_value, expected) -> None:
    db = _db(global_value=global_value, drive_value=drive_value, status=JobStatus.RIPPING)
    assert _post(db, "resume")["end_on_completion_message"] is expected


def test_resume_reads_the_setting_as_it_is_now_not_as_it_was_at_the_first_start() -> None:
    db = _db(global_value=True, drive_value=None, status=JobStatus.RIPPING)
    assert _post(db, "resume")["end_on_completion_message"] is True
    db.rows["config"][0].rip_end_on_completion_message = False
    assert _post(db, "resume")["end_on_completion_message"] is False


def test_a_missing_config_row_reads_as_off() -> None:
    db = _db(global_value=True, drive_value=None, status=JobStatus.RIPPING, with_config=False)
    assert _post(db, "resume")["end_on_completion_message"] is False
