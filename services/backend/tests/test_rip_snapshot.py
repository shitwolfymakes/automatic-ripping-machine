"""A per-title rip is frozen at Start: its unticked, queued video titles become SKIPPED and are never read."""

from __future__ import annotations

import pytest

from arm_backend.rip_snapshot import skip_unticked, tracks_to_skip
from arm_common import DiscType, Job, JobStatus, RipInvocation, Track, TrackKind, TrackStatus

from tests._fakes import FakeSession

_JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000001"


def _track(
    track_id: str,
    *,
    excluded: bool = True,
    status: TrackStatus = TrackStatus.QUEUED,
    kind: TrackKind = TrackKind.VIDEO_TITLE,
) -> Track:
    return Track(
        id=track_id,
        job_id=_JOB_ID,
        kind=kind,
        index=1,
        source_ref="1",
        status=status,
        excluded=excluded,
    )


def _ids(tracks: list[Track]) -> list[str]:
    return [t.id for t in tracks]


def test_per_title_skips_an_unticked_queued_video_title() -> None:
    unticked = _track("t_unticked")
    assert tracks_to_skip([unticked, _track("t_ticked", excluded=False)], RipInvocation.PER_TITLE) == [unticked]


@pytest.mark.parametrize(
    "track",
    [
        _track("t_done", status=TrackStatus.DONE),
        _track("t_running", status=TrackStatus.IN_PROGRESS),
        _track("t_failed", status=TrackStatus.FAILED),
        _track("t_skipped", status=TrackStatus.SKIPPED),
        _track("t_audio", kind=TrackKind.AUDIO_TRACK),
        _track("t_backup", kind=TrackKind.DISC_BACKUP),
        _track("t_dump", kind=TrackKind.DATA_DUMP),
        _track("t_ticked", excluded=False),
    ],
    ids=lambda t: t.id,
)
def test_per_title_leaves_every_other_track_alone(track: Track) -> None:
    assert tracks_to_skip([track], RipInvocation.PER_TITLE) == []


def test_mkv_all_skips_nothing() -> None:
    assert tracks_to_skip([_track("t_unticked")], RipInvocation.MKV_ALL) == []


def _db(*tracks: Track) -> FakeSession:
    db = FakeSession()
    db.rows["tracks"] = list(tracks)
    return db


def _job() -> Job:
    return Job(
        id=_JOB_ID,
        drive_id="drv_x",
        disc_type=DiscType.BLURAY,
        title="X",
        year=2000,
        status=JobStatus.AWAITING_REVIEW,
        metadata_json={},
        resumed_from_crash=False,
    )


@pytest.mark.asyncio
async def test_skip_unticked_marks_the_unticked_titles_skipped() -> None:
    unticked, ticked = _track("t_unticked"), _track("t_ticked", excluded=False)
    db = _db(unticked, ticked)
    skipped = await skip_unticked(db, _job(), RipInvocation.PER_TITLE)  # type: ignore[arg-type]
    assert _ids(skipped) == ["t_unticked"]
    assert unticked.status == TrackStatus.SKIPPED
    assert ticked.status == TrackStatus.QUEUED


@pytest.mark.asyncio
async def test_skip_unticked_is_idempotent() -> None:
    unticked = _track("t_unticked")
    db = _db(unticked)
    await skip_unticked(db, _job(), RipInvocation.PER_TITLE)  # type: ignore[arg-type]
    assert await skip_unticked(db, _job(), RipInvocation.PER_TITLE) == []  # type: ignore[arg-type]
    assert unticked.status == TrackStatus.SKIPPED


@pytest.mark.asyncio
async def test_skip_unticked_leaves_mkv_all_alone() -> None:
    unticked = _track("t_unticked")
    db = _db(unticked)
    assert await skip_unticked(db, _job(), RipInvocation.MKV_ALL) == []  # type: ignore[arg-type]
    assert unticked.status == TrackStatus.QUEUED
