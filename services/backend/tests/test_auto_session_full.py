"""Residual auto_session coverage: missing-preset 500s, the auto-source
failed-task retry/reset, and maybe_auto_apply_session's pending-session
path + its exception swallows.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from arm_backend import auto_session as asx  # noqa: E402
from arm_backend.auto_session import apply_session_internal, maybe_auto_apply_session  # noqa: E402
from arm_backend.path_template import TemplateValidationError  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    Drive,
    DriveStatus,
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)

from tests._fakes import FakeSession  # noqa: E402
from tests.test_auto_session import CapturingHub, _seed  # noqa: E402


def _media_root(tmp: Path) -> None:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp)


async def test_missing_rip_preset_500(tmp_path: Path) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    _seed(db)
    db.rows["rip_presets"] = []
    with pytest.raises(HTTPException) as ei:
        await apply_session_internal(
            db, job=db.rows["jobs"][0], session_id="ses_x", created_by_user_id=None, source="manual"
        )
    assert ei.value.status_code == 500
    assert "missing rip_preset_id" in ei.value.detail


async def test_missing_transcode_preset_500(tmp_path: Path) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"] = []
    with pytest.raises(HTTPException) as ei:
        await apply_session_internal(
            db, job=db.rows["jobs"][0], session_id="ses_x", created_by_user_id=None, source="manual"
        )
    assert ei.value.status_code == 500
    assert "missing transcode_preset_id" in ei.value.detail


async def test_session_without_transcode_preset_proceeds(tmp_path: Path) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    _seed(db)
    db.rows["sessions"][0].transcode_preset_id = None
    db.rows["sessions"][0].output_path_template = "{title}.mkv"
    out = await apply_session_internal(
        db, job=db.rows["jobs"][0], session_id="ses_x", created_by_user_id=None, source="manual"
    )
    assert out.application is not None


async def test_auto_source_resets_failed_tasks_on_existing_app(tmp_path: Path) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_old",
            session_id="ses_x",
            job_id=job.id,
            status=SessionApplicationStatus.FAILED,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_failed",
            session_application_id="sap_old",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.FAILED,
            output_path="x.mkv",
            progress_pct=50,
            attempts=1,
            last_error="boom",
        )
    ]
    out = await apply_session_internal(
        db, job=job, session_id="ses_x", created_by_user_id=None, source="auto", hub=CapturingHub()
    )
    assert out.application is db.rows["session_applications"][0]
    assert out.idempotent is False  # a failed task was retried
    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.QUEUED
    assert task.last_error is None
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING


async def test_maybe_auto_apply_uses_pending_session_id(tmp_path: Path) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    job.metadata_json = {"pending_session_id": "ses_x"}
    db.rows["jobs"] = [job]
    hub = CapturingHub()
    await maybe_auto_apply_session(db, job, hub)
    assert any(e["event_type"] == "session.queued" for e in hub.events)


def _drive_default(db: FakeSession) -> None:
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="h",
            device_path="/dev/sr0",
            status=DriveStatus.ONLINE,
            default_session_id="ses_x",
        )
    ]
    db.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=True,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=__import__(
                "arm_common", fromlist=["RetentionPolicy"]
            ).RetentionPolicy.PRUNE_AFTER_SESSION,
        )
    ]


@pytest.mark.parametrize(
    "exc",
    [
        TemplateValidationError("bad template"),
        IntegrityError("stmt", {}, Exception("dup")),
        RuntimeError("kaboom"),
    ],
)
async def test_maybe_auto_apply_swallows_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    _drive_default(db)

    async def _raise(*_a: Any, **_k: Any) -> None:
        raise exc

    monkeypatch.setattr(asx, "apply_session_internal", _raise)
    # Must not raise — the hook swallows everything and logs.
    await maybe_auto_apply_session(db, job, CapturingHub())


async def test_auto_retry_nonterminal_status_skips_reset(tmp_path: Path) -> None:
    """retried>0 but the existing app is still RUNNING (not terminal) → the
    status-reset block is skipped (141->148)."""
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_run",
            session_id="ses_x",
            job_id=job.id,
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_f",
            session_application_id="sap_run",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.FAILED,
            output_path="x.mkv",
            progress_pct=0,
            attempts=1,
        )
    ]
    out = await apply_session_internal(
        db, job=job, session_id="ses_x", created_by_user_id=None, source="auto", hub=CapturingHub()
    )
    assert out.idempotent is False
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING


_COLLIDE_PATH = "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv"


async def test_overwrite_fs_only_collision_no_db_row(tmp_path: Path) -> None:
    """overwrite=True, output path exists on disk but no evictable DB task →
    _evict_colliding_tasks returns early (343)."""
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    target = tmp_path / _COLLIDE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stale")
    out = await apply_session_internal(
        db, job=job, session_id="ses_x", overwrite=True, created_by_user_id=None, source="manual"
    )
    assert out.application is not None
    assert out.skipped_reason is None


async def test_overwrite_evicts_but_app_keeps_remaining_task(tmp_path: Path) -> None:
    """The colliding DONE task is evicted; its app still has another task,
    so the app is not deleted (357: `remaining is not None` → continue)."""
    _media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_other",
            session_id="ses_other",
            job_id="job_01JZXR7K3M5Q8N4VWA0000000J",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_collide",
            session_application_id="sap_other",
            source_track_id="trk_o1",
            status=TranscodeTaskStatus.DONE,
            output_path=_COLLIDE_PATH,
            progress_pct=100,
            attempts=1,
        ),
        TranscodeTask(
            id="txt_keep",
            session_application_id="sap_other",
            source_track_id="trk_o2",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Other/keep.mkv",
            progress_pct=0,
            attempts=0,
        ),
    ]
    out = await apply_session_internal(
        db, job=job, session_id="ses_x", overwrite=True, created_by_user_id=None, source="manual"
    )
    assert out.application is not None
    # The other app survived because it still has txt_keep.
    assert any(a.id == "sap_other" for a in db.rows["session_applications"])
