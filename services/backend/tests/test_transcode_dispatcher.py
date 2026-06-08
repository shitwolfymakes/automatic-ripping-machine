"""Tests for `TranscodeDispatcher` — spawn loop, stale-claim sweep,
.arm-inprogress orphan sweep, and cancel-running.

Docker-py is mocked end-to-end. Time-sensitive code paths (`asyncio.sleep`
inside `cancel_running`) are short-circuited via monkeypatch where it
matters; otherwise we just test the awaited awaitable directly.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)
from tests._fakes import FakeSession  # noqa: E402


def _settings(**overrides: Any) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "MAX_PARALLEL_TRANSCODES": 2,
        "ARM_TRANSCODE_STALE_THRESHOLD_SECONDS": 90,
        "ARM_TRANSCODE_MAX_ATTEMPTS": 3,
        "ARM_TRANSCODE_IMAGE": "arm-transcode:latest",
        "ARM_HOST_RAW_PATH": "/host/raw",
        "ARM_HOST_MEDIA_PATH": "/host/media",
        "ARM_HOST_LOGS_PATH": "/host/logs",
        "ARM_HOST_CERTS_PATH": "/host/certs",
        "ARM_DOCKER_NETWORK": "armv3_default",
        "ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS": 5,
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _db_factory(db: FakeSession) -> Any:
    """Stand-in for SessionLocal — yields the same FakeSession every time."""

    class _Factory:
        def __call__(self) -> "_Factory":
            return self

        async def __aenter__(self) -> FakeSession:
            return db

        async def __aexit__(self, *exc: Any) -> None:
            return None

    return _Factory()


def _app_with_one_task(status: TranscodeTaskStatus, **task_kwargs: Any) -> FakeSession:
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    fields: dict[str, Any] = dict(
        id="txt_1",
        session_application_id="sap_x",
        source_track_id="trk_1",
        status=status,
        attempts=0,
        progress_pct=0,
        output_path="Iron Man (2008)/Iron Man.mkv",
    )
    fields.update(task_kwargs)
    db.rows["transcode_tasks"] = [TranscodeTask(**fields)]
    return db


# ---- spawn loop --------------------------------------------------------------


async def test_spawn_pending_calls_docker_run_with_correct_volumes_and_env() -> None:
    db = _app_with_one_task(TranscodeTaskStatus.QUEUED)
    db.rows["transcode_tasks"][0].created_at = datetime.now(UTC)
    docker = MagicMock()
    hub = WSHub()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, hub)

    spawned = await disp.spawn_pending(db)
    assert spawned == 1

    docker.containers.run.assert_called_once()
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["image"] == "arm-transcode:latest"
    assert kwargs["labels"] == {"arm.task_id": "txt_1"}
    assert "/host/raw" in kwargs["volumes"]
    assert kwargs["volumes"]["/host/raw"] == {"bind": "/raw", "mode": "ro"}
    assert kwargs["volumes"]["/host/media"] == {"bind": "/media", "mode": "rw"}
    assert kwargs["environment"]["ARM_TRANSCODE_TASK_ID"] == "txt_1"
    assert kwargs["environment"]["ARM_SERVICE_TOKEN"] == "tok-service"
    assert kwargs["network"] == "armv3_default"
    assert kwargs["detach"] is True


async def test_spawn_caps_at_max_parallel() -> None:
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    # 1 already in_progress + 2 queued; MAX_PARALLEL=2 → 1 spawn slot.
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_running",
            session_application_id="sap_x",
            source_track_id="trk_a",
            status=TranscodeTaskStatus.IN_PROGRESS,
            attempts=1,
            progress_pct=50,
            claimed_by="other-host",
            claim_heartbeat_at=datetime.now(UTC),
            output_path="other.mkv",
        ),
        TranscodeTask(
            id="txt_queued1",
            session_application_id="sap_x",
            source_track_id="trk_b",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="q1.mkv",
            created_at=datetime.now(UTC),
        ),
        TranscodeTask(
            id="txt_queued2",
            session_application_id="sap_x",
            source_track_id="trk_c",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="q2.mkv",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        ),
    ]
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(MAX_PARALLEL_TRANSCODES=2), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
    docker.containers.run.assert_called_once()


async def test_spawn_disabled_when_host_paths_unset() -> None:
    db = _app_with_one_task(TranscodeTaskStatus.QUEUED)
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(ARM_HOST_RAW_PATH=""), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    docker.containers.run.assert_not_called()


async def test_spawn_continues_after_one_failure() -> None:
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    now = datetime.now(UTC)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id=f"txt_{i}",
            session_application_id="sap_x",
            source_track_id=f"trk_{i}",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path=f"q{i}.mkv",
            created_at=now + timedelta(seconds=i),
        )
        for i in range(2)
    ]
    docker = MagicMock()
    docker.containers.run.side_effect = [RuntimeError("docker daemon unreachable"), MagicMock()]
    disp = TranscodeDispatcher(_settings(MAX_PARALLEL_TRANSCODES=2), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1  # second task succeeded; first logged + skipped
    assert docker.containers.run.call_count == 2


# ---- stale-claim sweep -------------------------------------------------------


async def test_stale_claim_resets_to_queued() -> None:
    db = _app_with_one_task(
        TranscodeTaskStatus.IN_PROGRESS,
        claimed_by="dead-host",
        claim_heartbeat_at=datetime.now(UTC) - timedelta(seconds=200),
        attempts=1,
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    touched = await disp.sweep_stale_claims(db)
    assert touched == 1
    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.QUEUED
    assert task.claimed_by is None
    assert task.claim_heartbeat_at is None


async def test_stale_claim_hard_fails_after_max_attempts() -> None:
    db = _app_with_one_task(
        TranscodeTaskStatus.IN_PROGRESS,
        claimed_by="dead-host",
        claim_heartbeat_at=datetime.now(UTC) - timedelta(seconds=200),
        attempts=3,
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(ARM_TRANSCODE_MAX_ATTEMPTS=3), _db_factory(db), docker, WSHub())
    await disp.sweep_stale_claims(db)
    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.FAILED
    assert "exceeded retry limit" in (task.last_error or "")
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.FAILED


async def test_stale_sweep_no_op_when_heartbeat_recent() -> None:
    db = _app_with_one_task(
        TranscodeTaskStatus.IN_PROGRESS,
        claimed_by="alive-host",
        claim_heartbeat_at=datetime.now(UTC) - timedelta(seconds=10),
        attempts=1,
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    touched = await disp.sweep_stale_claims(db)
    assert touched == 0


# ---- .arm-inprogress sweep ---------------------------------------------------


async def test_arm_inprogress_sweep_deletes_orphans(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "Iron Man (2008)").mkdir(parents=True)
    orphan = media / "Iron Man (2008)" / "Iron Man.mkv.arm-inprogress"
    orphan.write_text("orphan")
    live_dir = media / "Live Movie (2024)"
    live_dir.mkdir()
    live_marker = live_dir / "Live Movie.mkv.arm-inprogress"
    live_marker.write_text("live")

    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_live",
            session_application_id="sap_x",
            source_track_id="trk_x",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="Live Movie (2024)/Live Movie.mkv",
            attempts=1,
            progress_pct=50,
        )
    ]
    db.rows["session_applications"] = []

    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    deleted = await disp.sweep_arm_inprogress(media)
    assert deleted == 1
    assert not orphan.exists()
    assert live_marker.exists()


async def test_arm_inprogress_sweep_skips_when_media_root_missing(tmp_path: Path) -> None:
    db = FakeSession()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    deleted = await disp.sweep_arm_inprogress(tmp_path / "does-not-exist")
    assert deleted == 0


# ---- cancel running ----------------------------------------------------------


async def test_cancel_running_emits_ws_then_docker_stop_fallback_then_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _app_with_one_task(
        TranscodeTaskStatus.IN_PROGRESS,
        claimed_by="zombie-host",
        claim_heartbeat_at=datetime.now(UTC),
        attempts=1,
    )
    container = MagicMock()
    docker = MagicMock()
    docker.containers.list.return_value = [container]

    # Skip the 10s sleep so the test is fast.
    import arm_backend.transcode_dispatcher as dispatcher_mod

    async def _fast_sleep(_t: float) -> None:
        return None

    monkeypatch.setattr(dispatcher_mod.asyncio, "sleep", _fast_sleep)

    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.cancel_running("txt_1")

    docker.containers.list.assert_called_once_with(filters={"label": "arm.task_id=txt_1"})
    container.stop.assert_called_once()
    # New semantics: row is gone, not marked FAILED.
    assert db.rows["transcode_tasks"] == []


async def test_cancel_running_skips_docker_stop_but_still_deletes_when_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transcoder honoured the WS cancel during the grace window: row is
    already terminal (DONE/FAILED) so docker-stop is unnecessary, but the
    user's intent was to remove it — delete the row anyway."""
    db = _app_with_one_task(TranscodeTaskStatus.DONE)
    docker = MagicMock()

    import arm_backend.transcode_dispatcher as dispatcher_mod

    async def _fast_sleep(_t: float) -> None:
        return None

    monkeypatch.setattr(dispatcher_mod.asyncio, "sleep", _fast_sleep)

    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.cancel_running("txt_1")
    docker.containers.list.assert_not_called()
    assert db.rows["transcode_tasks"] == []
