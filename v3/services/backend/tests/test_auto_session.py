"""Phase 8: direct tests for `apply_session_internal` covering both source values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.auto_session import (  # noqa: E402
    SessionNotFoundError,
    apply_session_internal,
)
from arm_common import (  # noqa: E402
    ContainerFormat,
    DiscType,
    HwPreference,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackKind,
    TrackSelection,
    TrackStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
)

from tests._fakes import FakeSession  # noqa: E402


class CapturingHub:
    """Records emit calls without touching websockets or the events table."""

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
        self.events.append(
            {
                "topic": topic,
                "event_type": event_type,
                "payload": payload,
                "job_id": job_id,
                "track_id": track_id,
            }
        )


def _seed(db: FakeSession, *, job_status: JobStatus = JobStatus.RIPPED) -> Job:
    job = Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="Iron Man",
        year=2008,
        status=job_status,
        metadata_json={},
    )
    db.rows["jobs"] = [job]
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
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
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
async def test_manual_source_emits_session_queued(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    hub = CapturingHub()

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_x",
        overwrite=False,
        created_by_user_id=None,
        source="manual",
        hub=hub,  # type: ignore[arg-type]
    )

    assert outcome.application is not None
    assert outcome.application.status == SessionApplicationStatus.QUEUED
    assert len(outcome.tasks) == 1
    assert outcome.idempotent is False
    assert outcome.skipped_reason is None
    assert len(hub.events) == 1
    evt = hub.events[0]
    assert evt["topic"] == "session.events"
    assert evt["event_type"] == "session.queued"
    assert evt["payload"]["source"] == "manual"
    assert evt["payload"]["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert evt["payload"]["task_count"] == 1


@pytest.mark.asyncio
async def test_auto_source_emits_with_auto_marker(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    hub = CapturingHub()

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_x",
        overwrite=False,
        created_by_user_id=None,
        source="auto",
        hub=hub,  # type: ignore[arg-type]
    )

    assert outcome.application is not None
    assert hub.events[0]["payload"]["source"] == "auto"


@pytest.mark.asyncio
async def test_idempotent_reapply_does_not_re_emit(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_existing",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_existing",
            session_application_id="sap_existing",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    hub = CapturingHub()

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_x",
        overwrite=False,
        created_by_user_id=None,
        # Auto-source keeps the (session, job) idempotency contract — repeated
        # rip-complete events for the same disc shouldn't fan out duplicate
        # applications. Manual is intentionally non-idempotent (covered in
        # test_apply_session.py).
        source="auto",
        hub=hub,  # type: ignore[arg-type]
    )

    assert outcome.idempotent is True
    assert outcome.application is not None
    assert outcome.application.id == "sap_existing"
    assert hub.events == []


@pytest.mark.asyncio
async def test_collision_returns_skipped_reason_without_raising(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
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

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_x",
        overwrite=False,
        created_by_user_id=None,
        source="auto",
        hub=hub,  # type: ignore[arg-type]
    )

    assert outcome.application is None
    assert outcome.skipped_reason == "collisions"
    assert len(outcome.collisions) == 1
    assert hub.events == []


@pytest.mark.asyncio
async def test_unknown_session_raises(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)

    with pytest.raises(SessionNotFoundError):
        await apply_session_internal(
            db,
            job=job,
            session_id="ses_does_not_exist",
            overwrite=False,
            created_by_user_id=None,
            source="auto",
            hub=None,
        )


@pytest.mark.asyncio
async def test_awaiting_user_id_parks_as_waiting_identify(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, job_status=JobStatus.AWAITING_USER_ID)
    hub = CapturingHub()

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_x",
        overwrite=False,
        created_by_user_id=None,
        source="manual",
        hub=hub,  # type: ignore[arg-type]
    )

    assert outcome.application is not None
    assert outcome.application.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert outcome.tasks == []
    # No transcode tasks fanned out → no session.queued emit (the dropdown
    # value sits idle until the user resolves identity).
    assert hub.events == []
