"""Direct tests on `reset_job_for_recovery` and `sweep_in_flight_jobs`."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_backend.crash_recovery import _sweep, reset_job_for_recovery
from arm_common import (
    DiscType,
    Job,
    JobStatus,
    Track,
    TrackKind,
    TrackStatus,
)

from tests._fakes import FakeSession


def _make_job(*, job_id: str = "job_01JZXR7K3M5Q8N4VWA00000001", status: JobStatus = JobStatus.RIPPING) -> Job:
    return Job(
        id=job_id,
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="Iron Man",
        year=2008,
        status=status,
        metadata_json={},
        resumed_from_crash=False,
    )


def _make_track(*, track_id: str, job_id: str, status: TrackStatus, attempts: int = 1) -> Track:
    return Track(
        id=track_id,
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=1,
        source_ref="1",
        status=status,
        attempts=attempts,
    )


@pytest.mark.asyncio
async def test_reset_flips_in_progress_to_queued_and_increments_attempts() -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    track = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.IN_PROGRESS, attempts=2)
    db.rows["tracks"] = [track]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 1
    assert job.resumed_from_crash is True
    assert track.status == TrackStatus.QUEUED
    assert track.attempts == 3


@pytest.mark.asyncio
async def test_reset_idempotent_on_already_queued_tracks() -> None:
    db = FakeSession()
    job = _make_job()
    job.resumed_from_crash = True  # Pretend we already swept once.
    db.rows["jobs"] = [job]
    track = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.QUEUED, attempts=2)
    db.rows["tracks"] = [track]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 0
    assert track.attempts == 2  # Not inflated.
    assert job.resumed_from_crash is True


def _finished_file(tmp_path: Path, name: str, size: int) -> str:
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return str(path)


@pytest.mark.asyncio
async def test_reset_keeps_a_done_track_whose_file_is_at_its_recorded_size(tmp_path: Path) -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    done = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.DONE, attempts=1)
    done.output_path = _finished_file(tmp_path, "title_t00.mkv", 16)
    done.size_bytes = 16
    db.rows["tracks"] = [done]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 0
    assert done.status == TrackStatus.DONE
    assert done.attempts == 1
    assert job.resumed_from_crash is True


@pytest.mark.asyncio
async def test_reset_requeues_a_done_track_whose_file_is_short(tmp_path: Path) -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    done = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.DONE, attempts=1)
    done.output_path = _finished_file(tmp_path, "title_t00.mkv", 8)
    done.size_bytes = 16
    db.rows["tracks"] = [done]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 1
    assert done.status == TrackStatus.QUEUED
    assert done.attempts == 2


@pytest.mark.asyncio
async def test_reset_requeues_a_done_track_whose_file_is_missing_or_unrecorded(tmp_path: Path) -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    missing = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.DONE, attempts=1)
    missing.output_path = str(tmp_path / "gone.mkv")
    missing.size_bytes = 16
    unrecorded = _make_track(track_id="trk_2", job_id=job.id, status=TrackStatus.DONE, attempts=1)
    db.rows["tracks"] = [missing, unrecorded]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 2
    assert missing.status == TrackStatus.QUEUED
    assert unrecorded.status == TrackStatus.QUEUED


@pytest.mark.asyncio
async def test_reset_requeues_failed_tracks() -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    failed = _make_track(track_id="trk_2", job_id=job.id, status=TrackStatus.FAILED, attempts=2)
    queued = _make_track(track_id="trk_3", job_id=job.id, status=TrackStatus.QUEUED, attempts=0)
    db.rows["tracks"] = [failed, queued]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 1
    assert failed.status == TrackStatus.QUEUED
    assert failed.attempts == 3
    assert queued.attempts == 0


@pytest.mark.asyncio
async def test_sweep_no_ripping_jobs_returns_zero() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000007", status=JobStatus.RIPPED)]
    db.rows["tracks"] = []

    swept = await _sweep(db)  # type: ignore[arg-type]

    assert swept == 0
    assert db.committed == 0


@pytest.mark.asyncio
async def test_sweep_resets_only_ripping_jobs() -> None:
    db = FakeSession()
    ripping_a = _make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)
    ripping_b = _make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000003", status=JobStatus.RIPPING)
    ripped = _make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000004", status=JobStatus.RIPPED)
    db.rows["jobs"] = [ripping_a, ripping_b, ripped]
    db.rows["tracks"] = [
        _make_track(track_id="trk_a", job_id="job_01JZXR7K3M5Q8N4VWA00000002", status=TrackStatus.IN_PROGRESS),
        _make_track(track_id="trk_b", job_id="job_01JZXR7K3M5Q8N4VWA00000003", status=TrackStatus.IN_PROGRESS),
        _make_track(track_id="trk_c", job_id="job_01JZXR7K3M5Q8N4VWA00000004", status=TrackStatus.DONE, attempts=1),
    ]

    swept = await _sweep(db)  # type: ignore[arg-type]

    assert swept == 2
    assert ripping_a.resumed_from_crash is True
    assert ripping_b.resumed_from_crash is True
    assert ripped.resumed_from_crash is False
    # Ripped job's track should be untouched.
    ripped_track = db.rows["tracks"][2]
    assert ripped_track.status == TrackStatus.DONE
    assert ripped_track.attempts == 1
    assert db.committed == 1
