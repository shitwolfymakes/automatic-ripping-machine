"""Transcode task milestones and the once-per-wait GPU log."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from arm_backend import transcode_task_events as events
from arm_backend.track_labels import TrackLabel
from arm_common import (
    ContainerFormat,
    DiscType,
    Job,
    JobStatus,
    MediaType,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackKind,
    TrackStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
)
from tests._fakes import FakeSession
from tests._logs import LineCapture

_LABEL = TrackLabel(1, 19, "Don't Bring Me Down")


def _job() -> Job:
    return Job(
        id="job_1",
        drive_id="d",
        disc_type=DiscType.CD,
        status=JobStatus.RIPPED,
        title="Album",
        media_type=MediaType.MUSIC,
        metadata_json={},
    )


def _tracks() -> list[Track]:
    return [
        Track(
            id=f"trk_{i}",
            job_id="job_1",
            kind=TrackKind.AUDIO_TRACK,
            index=i,
            source_ref=str(i),
            status=TrackStatus.DONE,
            attempts=0,
        )
        for i in (1, 2, 3)
    ]


def _task(**kw: Any) -> TranscodeTask:
    base: dict[str, Any] = {
        "id": "txt_1",
        "session_application_id": "sap_1",
        "source_track_id": "trk_2",
        "status": TranscodeTaskStatus.IN_PROGRESS,
        "attempts": 1,
        "progress_pct": 0,
    }
    return TranscodeTask(**{**base, **kw})


def _db(*, application: bool = True, job: bool = True) -> FakeSession:
    db = FakeSession()
    db.rows["session_applications"] = (
        [
            SessionApplication(
                id="sap_1",
                session_id="ses_1",
                job_id="job_1",
                status=SessionApplicationStatus.RUNNING,
                overwrite=False,
            )
        ]
        if application
        else []
    )
    db.rows["jobs"] = [_job()] if job else []
    db.rows["tracks"] = _tracks()
    db.rows["sessions"] = [
        Session(
            id="ses_1",
            name="Music to FLAC",
            media_type=MediaType.MUSIC,
            is_builtin=False,
            rip_preset_id="rpr_1",
            transcode_preset_id="tpr_1",
            output_path_template="{title}.{ext}",
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_1",
            name="FLAC",
            media_type=MediaType.MUSIC,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.FLAC,
            encoder="preset",
        )
    ]
    db.rows["transcode_tasks"] = [_task(status=TranscodeTaskStatus.QUEUED)]
    return db


# --- message builders -----------------------------------------------------


def test_started_message_names_the_preset() -> None:
    assert events.transcode_started_message(_LABEL, "FLAC") == "transcoding track 1/19 to FLAC"


def test_started_message_without_a_preset_is_a_passthrough_copy() -> None:
    assert events.transcode_started_message(_LABEL, None) == "copying track 1/19 as is (no transcode preset)"


def test_progress_message() -> None:
    assert events.transcode_progress_message(_LABEL, 50) == "track 1/19: 50%"


@pytest.mark.parametrize(
    ("output", "shown"),
    [
        ("ELO/Essential/01 - Don't Bring Me Down - flac.flac", ".../01 - Don't Bring Me Down - flac.flac"),
        ("01.flac", "01.flac"),
    ],
)
def test_completed_message_shows_the_file_name_and_size(output: str, shown: str) -> None:
    msg = events.transcode_completed_message(_LABEL, output, 32_610_713)
    assert msg == f"track 1/19 transcoded: {shown} (31.1 MB)"


def test_failed_message() -> None:
    assert events.transcode_failed_message(_LABEL, "exit 1") == "track 1/19 transcode failed: exit 1"


@pytest.mark.parametrize(
    ("state", "encoder", "track", "expected"),
    [
        ("waiting", "any_h265", "track 3/6", "transcode waiting for a GPU encoder (any_h265): track 3/6"),
        ("resumed", "any_h265", "track 3/6", "transcode no longer waiting for a GPU encoder (any_h265): track 3/6"),
        ("waiting", None, None, "transcode waiting for a GPU encoder"),
    ],
)
def test_gpu_wait_message(state: str, encoder: str | None, track: str | None, expected: str) -> None:
    assert events.gpu_wait_message(state, encoder, track) == expected


# --- emitters --------------------------------------------------------------


def test_log_transcode_started(job_log: LineCapture) -> None:
    events.log_transcode_started(_task(), _job(), _tracks(), preset="FLAC")
    (line,) = job_log.lines(event="transcode.started")
    assert line["msg"] == "transcoding track 2/3 to FLAC"
    assert (line["job_id"], line["track_id"], line["session_application_id"]) == ("job_1", "trk_2", "sap_1")
    assert line["fields"] == {"task_id": "txt_1", "track_index": 2, "track_total": 3, "preset": "FLAC"}


def test_log_transcode_progress_logs_only_a_crossed_quarter(job_log: LineCapture) -> None:
    for previous, current in ((0, 10), (10, 30), (30, 30), (30, 80), (80, 100)):
        events.log_transcode_progress(_task(), _job(), _tracks(), previous, current)
    lines = job_log.lines(event="transcode.progress")
    assert [line["fields"]["percent"] for line in lines] == [25, 75, 100]
    assert lines[0]["msg"] == "track 2/3: 25%" and lines[0]["fields"]["task_id"] == "txt_1"


def test_log_transcode_completed(job_log: LineCapture) -> None:
    events.log_transcode_completed(_task(), _job(), _tracks(), "a/b.flac", 2048, 12.5)
    (line,) = job_log.lines(event="transcode.completed")
    assert line["msg"] == "track 2/3 transcoded: .../b.flac (2.0 KB)"
    assert line["fields"] == {"task_id": "txt_1", "output": "a/b.flac", "size_bytes": 2048, "elapsed_seconds": 12.5}


def test_log_transcode_failed_is_an_error(job_log: LineCapture) -> None:
    events.log_transcode_failed(_task(), _job(), _tracks(), "exit 1")
    (line,) = job_log.lines(event="transcode.failed")
    assert line["level"] == "error" and line["msg"] == "track 2/3 transcode failed: exit 1"
    assert line["fields"] == {"task_id": "txt_1", "error": "exit 1"}


# --- announcers (load the job, then log) -----------------------------------


async def test_announce_started_names_the_sessions_preset(job_log: LineCapture) -> None:
    await events.announce_started(_db(), _task())
    (line,) = job_log.lines(event="transcode.started")
    assert line["fields"]["preset"] == "FLAC"


async def test_announce_started_without_a_preset(job_log: LineCapture) -> None:
    db = _db()
    db.rows["sessions"][0].transcode_preset_id = None
    await events.announce_started(db, _task())
    (line,) = job_log.lines(event="transcode.started")
    assert line["fields"]["preset"] is None


@pytest.mark.parametrize("missing", ["application", "job"])
async def test_announcers_skip_a_task_without_a_job(job_log: LineCapture, missing: str) -> None:
    db = _db(**{missing: False})
    await events.announce_started(db, _task())
    await events.announce_progress(db, _task(), 0, 50)
    await events.announce_completed(db, _task(), "a.flac", 1)
    await events.announce_failed(db, _task(), "boom")
    assert job_log.lines(logger_prefix="arm_backend.transcode_task_events") == []


async def test_announce_progress_reads_nothing_without_a_crossed_quarter(job_log: LineCapture) -> None:
    db = _db()
    await events.announce_progress(db, _task(), 10, 20)
    assert db.call_log == [] and job_log.lines(event="transcode.progress") == []


async def test_announce_progress_logs_the_quarter(job_log: LineCapture) -> None:
    await events.announce_progress(_db(), _task(), 20, 55)
    (line,) = job_log.lines(event="transcode.progress")
    assert line["fields"]["percent"] == 50


async def test_announce_completed_measures_from_the_claim(job_log: LineCapture) -> None:
    task = _task(started_at=datetime.now(UTC) - timedelta(seconds=90))
    await events.announce_completed(_db(), task, "a.flac", 10)
    (line,) = job_log.lines(event="transcode.completed")
    assert 90 <= line["fields"]["elapsed_seconds"] < 120


async def test_announce_completed_without_a_claim_time(job_log: LineCapture) -> None:
    await events.announce_completed(_db(), _task(started_at=None), "a.flac", None)
    (line,) = job_log.lines(event="transcode.completed")
    assert line["fields"]["elapsed_seconds"] is None and line["msg"].endswith("(unknown size)")


async def test_announce_failed(job_log: LineCapture) -> None:
    await events.announce_failed(_db(), _task(), "boom")
    (line,) = job_log.lines(event="transcode.failed")
    assert line["fields"]["error"] == "boom"


async def test_log_safely_logs_a_failed_milestone_instead_of_raising(job_log: LineCapture) -> None:
    async def _broken() -> None:
        raise RuntimeError("db gone")

    await events.log_safely("transcode.started", _broken())
    (line,) = job_log.lines(level="error")
    assert line["msg"] == "could not log the transcode.started milestone" and "db gone" in line["exc"]


async def test_log_safely_runs_the_work() -> None:
    ran: list[bool] = []

    async def _work() -> None:
        ran.append(True)

    await events.log_safely("transcode.started", _work())
    assert ran == [True]


# --- once-per-wait GPU log -------------------------------------------------


async def test_gpu_wait_logs_once_until_it_resumes(job_log: LineCapture) -> None:
    waits = events.GpuWaitLog()
    db = _db()
    task = db.rows["transcode_tasks"][0]
    for _ in range(3):
        await waits.waiting(db, task, "any_h265", "every eligible GPU is busy")
    waits.resumed("txt_1")
    waits.resumed("txt_1")
    lines = job_log.lines(event="transcode.waiting")
    assert [line["fields"]["state"] for line in lines] == ["waiting", "resumed"]
    assert lines[0]["msg"] == "transcode waiting for a GPU encoder (any_h265): track 2/3"
    assert lines[1]["msg"] == "transcode no longer waiting for a GPU encoder (any_h265): track 2/3"
    assert lines[0]["fields"] == {
        "task_id": "txt_1",
        "encoder": "any_h265",
        "reason": "every eligible GPU is busy",
        "state": "waiting",
    }
    assert all(
        (line["job_id"], line["track_id"], line["session_application_id"]) == ("job_1", "trk_2", "sap_1")
        for line in lines
    )


async def test_gpu_wait_without_a_job_still_logs(job_log: LineCapture) -> None:
    waits = events.GpuWaitLog()
    db = _db(application=False)
    await waits.waiting(db, db.rows["transcode_tasks"][0], None, None)
    (line,) = job_log.lines(event="transcode.waiting")
    assert line["msg"] == "transcode waiting for a GPU encoder" and line["job_id"] is None


async def test_settle_resumes_a_wait_whose_task_left_the_queue(job_log: LineCapture) -> None:
    waits = events.GpuWaitLog()
    db = _db()
    db.rows["transcode_tasks"].append(_task(id="txt_2", status=TranscodeTaskStatus.QUEUED))
    for task in db.rows["transcode_tasks"]:
        await waits.waiting(db, task, "any_h265", None)
    db.rows["transcode_tasks"] = [t for t in db.rows["transcode_tasks"] if t.id != "txt_1"]  # cancelled
    await waits.settle(db)
    await waits.settle(db)
    resumed = job_log.lines(event="transcode.waiting")[2:]
    assert [(line["fields"]["task_id"], line["fields"]["state"]) for line in resumed] == [("txt_1", "resumed")]


async def test_settle_without_waits_reads_nothing() -> None:
    db = FakeSession()
    await events.GpuWaitLog().settle(db)
    assert db.call_log == []
