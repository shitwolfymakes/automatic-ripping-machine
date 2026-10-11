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

from arm_backend.auto_session import after_rip, apply_session_internal, maybe_auto_apply_session  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    ContainerFormat,
    DiscType,
    Drive,
    DriveStatus,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RetentionPolicy,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
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
        id="job_01JZXR7K3M5Q8N4VWA00000001",
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
            auto_rip_on_insert=True,
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
            encoder="preset",
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
async def test_ripped_with_default_and_auto_creates_application(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    apps = [r for r in db.added if isinstance(r, SessionApplication)]
    assert len(apps) == 1
    assert apps[0].session_id == "ses_x"
    assert apps[0].job_id == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert any(e["event_type"] == "session.queued" for e in hub.events)
    assert hub.events[0]["payload"]["source"] == "auto"


@pytest.mark.asyncio
async def test_auto_apply_succeeds_for_job_with_no_year_when_year_is_optional(tmp_path: Path) -> None:
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db)
    job.year = None
    db.rows["sessions"][0].output_path_template = "{title} ({year?})/{title} - {transcode_slug}.{ext}"
    hub = CapturingHub()

    await maybe_auto_apply_session(db, job, hub)  # type: ignore[arg-type]

    tasks = db.rows["transcode_tasks"]
    assert len(tasks) == 1
    assert tasks[0].output_path.startswith("Iron Man/Iron Man - ")


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


@pytest.mark.asyncio
async def test_after_rip_drains_session_parked_on_held_disc_exactly_once(tmp_path: Path) -> None:
    """Review focus 3: session parked while the disc was held; the countdown
    then started the rip. At rip-complete exactly one application fans out and
    the drive default does not also apply."""
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, job_status=JobStatus.AWAITING_REVIEW, drive_default_session_id="ses_x", auto_transcode_on_idle=True)
    # Identify's hold_for_review path persisted review Track rows, so the
    # held disc already has tracks; they are only ripped once the hold ends.
    for track in db.rows["tracks"]:
        track.status = TrackStatus.QUEUED
    assert db.rows["tracks"], "review tracks must be present for this regression"
    db.rows["session_applications"] = []
    db.rows["transcode_tasks"] = []
    # Session Y (distinct template) is what the operator parks on the held
    # disc; the drive default X must then NOT also apply at rip-complete.
    db.rows["rip_presets"].append(
        RipPreset(
            id="rpr_y",
            name="Movie archive",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    )
    db.rows["sessions"].append(
        Session(
            id="ses_y",
            name="Archive copy",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_y",
            transcode_preset_id="tpr_x",
            output_path_template="Archive/{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    )
    hub = CapturingHub()

    outcome = await apply_session_internal(
        db,
        job=job,
        session_id="ses_y",
        overwrite=False,
        created_by_user_id=None,
        source="manual",
        hub=hub,  # type: ignore[arg-type]
    )
    assert outcome.skipped_reason == "no_tracks"
    assert db.rows["transcode_tasks"] == []

    # The rip runs: the review tracks are ripped, status goes to RIPPED, and
    # rip-complete calls after_rip.
    for track in db.rows["tracks"]:
        track.status = TrackStatus.DONE
    job.status = JobStatus.RIPPED
    outcomes = await after_rip(db, job, hub)  # type: ignore[arg-type]

    assert [o.skipped_reason for o in outcomes] == [None]
    apps = db.rows["session_applications"]
    assert len(apps) == 1
    assert apps[0].session_id == "ses_y"
    assert apps[0].status == SessionApplicationStatus.QUEUED
    assert not [a for a in apps if a.session_id == "ses_x"]
    tasks = db.rows["transcode_tasks"]
    assert len(tasks) == 1
    assert tasks[0].output_path.startswith("Archive/")  # Y's template, not X's


@pytest.mark.asyncio
async def test_after_rip_strict_token_surfaces_as_parked_failure_not_exception(tmp_path: Path) -> None:
    """Spec section 4: a still-strict required token (`{year}`, job year None)
    cannot be checked pre-rip (the apply parks), so it surfaces at drain time.
    At rip-complete the drain reports a `template` outcome with the error
    detail and the application stays WAITING_IDENTIFY; nothing raises and no
    tasks are queued."""
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, job_status=JobStatus.AWAITING_REVIEW, drive_default_session_id=None)
    job.year = None
    for track in db.rows["tracks"]:
        track.status = TrackStatus.QUEUED
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
    assert outcome.skipped_reason == "no_tracks"

    for track in db.rows["tracks"]:
        track.status = TrackStatus.DONE
    job.status = JobStatus.RIPPED
    outcomes = await after_rip(db, job, hub)  # type: ignore[arg-type]

    assert [o.skipped_reason for o in outcomes] == ["template"]
    assert outcomes[0].error_detail is not None and "{year}" in outcomes[0].error_detail
    apps = db.rows["session_applications"]
    assert len(apps) == 1
    assert apps[0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []
    assert not any(e["event_type"] == "session.queued" for e in hub.events)


@pytest.mark.asyncio
async def test_after_rip_promoted_parked_application_suppresses_drive_default(tmp_path: Path) -> None:
    """Fix 75-4: a parked application Y (explicit, applied before rip-start)
    that the drain successfully promotes to queued IS the operator's choice
    winning -- the drive default X must NOT also auto-apply, even though
    auto_transcode_on_idle is on. Before the fix, after_rip always ran
    maybe_auto_apply_session unconditionally after the drain, so both Y's
    and X's tasks would exist side by side.
    """
    _set_media_root(tmp_path)
    db = FakeSession()
    job = _seed(db, drive_default_session_id="ses_x", auto_transcode_on_idle=True)

    # Session Y: a second session/preset pair, parked as waiting_identify on
    # this job (as if applied manually before the rip started). Its template
    # differs from X's so their output paths -- and therefore which tasks
    # exist afterward -- are trivially distinguishable.
    db.rows["rip_presets"].append(
        RipPreset(
            id="rpr_y",
            name="Movie archive",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    )
    db.rows["sessions"].append(
        Session(
            id="ses_y",
            name="Archive copy",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_y",
            transcode_preset_id="tpr_x",
            output_path_template="Archive/{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    )
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_y",
            session_id="ses_y",
            job_id=job.id,
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
        )
    ]
    hub = CapturingHub()

    outcomes = await after_rip(db, job, hub)  # type: ignore[arg-type]

    assert len(outcomes) == 1
    assert outcomes[0].skipped_reason is None
    assert outcomes[0].application.session_id == "ses_y"

    apps = db.rows["session_applications"]
    assert {a.session_id for a in apps} == {"ses_y"}  # no ses_x application created
    assert apps[0].status == SessionApplicationStatus.QUEUED

    tasks = db.rows["transcode_tasks"]
    assert len(tasks) == 1
    assert tasks[0].output_path.startswith("Archive/")  # Y's template, not X's
    queued_events = [e for e in hub.events if e["event_type"] == "session.queued"]
    assert len(queued_events) == 1
    assert queued_events[0]["payload"]["session_id"] == "ses_y"
