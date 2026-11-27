"""Direct tests on `reset_job_for_recovery` and `sweep_in_flight_jobs`."""

from __future__ import annotations


import pytest

from arm_backend.crash_recovery import _sweep, reset_job_for_recovery, should_recover
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


@pytest.mark.asyncio
async def test_reset_handles_done_and_failed_tracks() -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    done = _make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.DONE, attempts=1)
    failed = _make_track(track_id="trk_2", job_id=job.id, status=TrackStatus.FAILED, attempts=2)
    queued = _make_track(track_id="trk_3", job_id=job.id, status=TrackStatus.QUEUED, attempts=0)
    db.rows["tracks"] = [done, failed, queued]

    touched = await reset_job_for_recovery(db, job)  # type: ignore[arg-type]

    assert touched == 2
    assert done.status == TrackStatus.QUEUED
    assert done.attempts == 2
    assert failed.status == TrackStatus.QUEUED
    assert failed.attempts == 3
    assert queued.attempts == 0


@pytest.mark.asyncio
async def test_sweep_no_ripping_jobs_returns_zero() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000007", status=JobStatus.RIPPED)]
    db.rows["tracks"] = []

    swept = await _sweep(db, frozenset())  # type: ignore[arg-type]

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

    swept = await _sweep(db, frozenset())  # type: ignore[arg-type]

    assert swept == 2
    assert ripping_a.resumed_from_crash is True
    assert ripping_b.resumed_from_crash is True
    assert ripped.resumed_from_crash is False
    # Ripped job's track should be untouched.
    ripped_track = db.rows["tracks"][2]
    assert ripped_track.status == TrackStatus.DONE
    assert ripped_track.attempts == 1
    assert db.committed == 1


def test_should_recover_only_when_the_jobs_ripper_is_not_live() -> None:
    job = _make_job()  # drive_id drv_x
    assert should_recover(job, frozenset()) is True
    assert should_recover(job, frozenset({"drv_other"})) is True
    assert should_recover(job, frozenset({"drv_x"})) is False
    job.drive_id = None
    assert should_recover(job, frozenset({"drv_x"})) is True


@pytest.mark.asyncio
async def test_sweep_leaves_a_job_with_a_live_ripper_alone() -> None:
    """A backend restart while the ripper keeps ripping: the adopted drive's
    RIPPING job must keep its in-progress track and not be stamped crashed."""
    db = FakeSession()
    live = _make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000008")
    live.drive_id = "drv_live"
    gone = _make_job(job_id="job_01JZXR7K3M5Q8N4VWA00000009")
    gone.drive_id = "drv_gone"
    db.rows["jobs"] = [live, gone]
    live_track = _make_track(track_id="trk_live", job_id=live.id, status=TrackStatus.IN_PROGRESS, attempts=1)
    gone_track = _make_track(track_id="trk_gone", job_id=gone.id, status=TrackStatus.IN_PROGRESS, attempts=1)
    db.rows["tracks"] = [live_track, gone_track]

    swept = await _sweep(db, frozenset({"drv_live"}))  # type: ignore[arg-type]

    assert swept == 1
    assert live.resumed_from_crash is False
    assert live_track.status == TrackStatus.IN_PROGRESS
    assert live_track.attempts == 1
    assert gone.resumed_from_crash is True
    assert gone_track.status == TrackStatus.QUEUED
    assert gone_track.attempts == 2


@pytest.mark.asyncio
async def test_sweep_skipping_every_job_commits_nothing() -> None:
    db = FakeSession()
    job = _make_job()
    db.rows["jobs"] = [job]
    db.rows["tracks"] = [_make_track(track_id="trk_1", job_id=job.id, status=TrackStatus.IN_PROGRESS)]

    swept = await _sweep(db, frozenset({"drv_x"}))  # type: ignore[arg-type]

    assert swept == 0
    assert db.committed == 0
