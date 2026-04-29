"""Phase 8: rip-complete auto-session hook (`maybe_auto_apply_session`).

Tests the hook in isolation — the surrounding rip-complete route is unchanged
from Phase 3 and already exercised through the higher-level integration paths.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.auto_session import maybe_auto_apply_session  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    ContainerFormat,
    DiscType,
    Drive,
    DriveStatus,
    HwPreference,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RetentionPolicy,
    RipPreset,
    Session,
    SessionApplication,
    Track,
    TrackKind,
    TrackSelection,
    TrackStatus,
    TranscodePreset,
    TranscodeTool,
)

from tests._fakes import FakeSession  # noqa: E402


class CapturingHub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


def _seed(
    db: FakeSession,
    *,
    job_status: JobStatus = JobStatus.RIPPED,
    drive_default_session_id: str | None = "ses_x",
    auto_transcode_on_idle: bool = True,
) -> Job:
    job = Job(
        id="job_x",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="Iron Man",
        year=2008,
        status=job_status,
        metadata_json={},
    )
    db.rows["jobs"] = [job]
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="ripper-host",
            device_path="/dev/sr0",
            status=DriveStatus.ONLINE,
            default_session_id=drive_default_session_id,
        )
    ]
    db.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=auto_transcode_on_idle,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        )
    ]
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_x",
            name="Movie main",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_x",
            name="Plex 1080p H.265",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="My Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    ]
    db.rows["tracks"] = [
        Track(
            id="trk_1",
            job_id="job_x",
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
            expected_duration_seconds=8000,
            status=TrackStatus.DONE,
        )
    ]
    db.rows["transcode_tasks"] = []
    db.rows["session_applications"] = []
    return job


def _set_media_root(tmp_path: Path) -> None:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp_path)


@pytest.mark.asyncio
async def test_ripped_with_default_and_auto_creates_application(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    apps = [r for r in db.added if isinstance(r, SessionApplication)]
    assert len(apps) == 1
    assert apps[0].session_id == "ses_x"
    assert apps[0].job_id == "job_x"
    assert any(e["event_type"] == "session.queued" for e in hub.events)
    assert hub.events[0]["payload"]["source"] == "auto"


@pytest.mark.asyncio
async def test_ripped_partial_also_triggers(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, job_status=JobStatus.RIPPED_PARTIAL)
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    apps = [r for r in db.added if isinstance(r, SessionApplication)]
    assert len(apps) == 1


@pytest.mark.asyncio
async def test_drive_without_default_session_no_op(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, drive_default_session_id=None)
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    assert [r for r in db.added if isinstance(r, SessionApplication)] == []
    assert hub.events == []


@pytest.mark.asyncio
async def test_auto_transcode_disabled_no_op(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, auto_transcode_on_idle=False)
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    assert [r for r in db.added if isinstance(r, SessionApplication)] == []
    assert hub.events == []


@pytest.mark.asyncio
async def test_default_session_missing_logs_warning_and_no_op(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    # FK ON DELETE SET NULL would prevent this in production, but the helper
    # checks defensively. Simulate by deleting the session row directly.
    db.rows["sessions"] = []
    hub = CapturingHub()

    with caplog.at_level(logging.WARNING, logger="arm_backend.auto_session"):
        await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    assert [r for r in db.added if isinstance(r, SessionApplication)] == []
    assert hub.events == []
    assert any("session_id=ses_x missing" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_collision_logs_skipped_reason_and_no_op(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    # Pre-existing task with the same output path the auto-apply would generate.
    from arm_common import TranscodeTask, TranscodeTaskStatus

    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    hub = CapturingHub()

    with caplog.at_level(logging.WARNING, logger="arm_backend.auto_session"):
        await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    assert [r for r in db.added if isinstance(r, SessionApplication)] == []
    assert hub.events == []
    assert any("skipped reason=collisions" in rec.message for rec in caplog.records)
