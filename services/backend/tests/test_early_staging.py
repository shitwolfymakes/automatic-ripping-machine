"""D24: a track that finishes ripping is staged at once when the auto-apply session will encode it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import select

from arm_backend import early_staging
from arm_backend.early_staging import _auto_apply_session, _encodes_track, is_held_for_review, stage_finished_track
from arm_backend.path_template import TemplateValidationError
from arm_common import Config, Job, JobStatus, Session, StageStatus, TrackStage, TranscodeTool
from arm_common.models import Track
from tests._fakes import FakeSession
from tests._stage_env import JOB, Env, add_job, add_track

_JOB = Job(id=JOB, drive_id="drv_x", status=JobStatus.RIPPING, metadata_json={}, manual_pause=False)
_SESSION = Session(id="ses_a", name="a", transcode_preset_id="tp_a", rip_preset_id="rp_a")
_ENCODE = SimpleNamespace(tool=TranscodeTool.HANDBRAKE)
_PASSTHROUGH = SimpleNamespace(tool=TranscodeTool.NONE)


# --- is_held_for_review --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "manual_pause", "held"),
    [
        (JobStatus.AWAITING_REVIEW, False, True),
        (JobStatus.RIPPING, True, True),
        (JobStatus.RIPPING, False, False),
    ],
)
def test_a_job_is_held_while_awaiting_review_or_manually_paused(
    status: JobStatus, manual_pause: bool, held: bool
) -> None:
    job = Job(id=JOB, drive_id="drv_x", status=status, metadata_json={}, manual_pause=manual_pause)
    assert is_held_for_review(job) is held


# --- _auto_apply_session -------------------------------------------------------------------


async def test_the_auto_apply_session_is_the_routed_one_when_auto_apply_is_allowed() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_SESSION]
    job = Job(id=JOB, drive_id="drv_x", status=JobStatus.RIPPING, metadata_json={}, pending_session_id="ses_a")
    assert await _auto_apply_session(db, job) is _SESSION  # type: ignore[arg-type]


async def test_no_auto_apply_means_no_session() -> None:
    db = FakeSession()
    db.rows["config"] = [Config(id=1, auto_transcode_on_idle=False, auto_rip_on_insert=True, block_on_miss=True)]
    db.rows["drives"] = []
    assert await _auto_apply_session(db, _JOB) is None  # type: ignore[arg-type]


async def test_an_unrouted_job_has_no_auto_apply_session() -> None:
    db = FakeSession()
    db.rows["config"] = [Config(id=1, auto_transcode_on_idle=True, auto_rip_on_insert=True, block_on_miss=True)]
    db.rows["drives"] = []
    assert await _auto_apply_session(db, _JOB) is None  # type: ignore[arg-type]


# --- _encodes_track ------------------------------------------------------------------------


def _outputs(monkeypatch: pytest.MonkeyPatch, preset: Any, track_ids: list[str] | Exception) -> None:
    async def load(_db: Any, _sess: Any) -> Any:
        return preset

    async def tracks(_db: Any, _job: Any) -> list[Any]:
        return []

    def compute(_job: Any, _tracks: Any, _sess: Any, _preset: Any, _stereo: Any) -> list[Any]:
        if isinstance(track_ids, Exception):
            raise track_ids
        return [SimpleNamespace(track_id=t) for t in track_ids]

    monkeypatch.setattr(early_staging, "load_transcode_preset", load)
    monkeypatch.setattr(early_staging, "job_tracks", tracks)
    monkeypatch.setattr(early_staging, "compute_outputs", compute)


def _track(track_id: str = "trk_a") -> Track:
    return Track(id=track_id, job_id=JOB, index=1, source_ref="1")


async def test_an_encode_session_with_an_output_for_the_track_encodes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs(monkeypatch, _ENCODE, ["trk_a"])
    assert await _encodes_track(FakeSession(), _JOB, _SESSION, _track()) is True  # type: ignore[arg-type]


async def test_a_passthrough_session_does_not_encode_the_track(monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs(monkeypatch, _PASSTHROUGH, ["trk_a"])
    assert await _encodes_track(FakeSession(), _JOB, _SESSION, _track()) is False  # type: ignore[arg-type]


async def test_a_track_without_an_output_is_not_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs(monkeypatch, _ENCODE, ["trk_other"])
    assert await _encodes_track(FakeSession(), _JOB, _SESSION, _track()) is False  # type: ignore[arg-type]


async def test_a_template_error_means_not_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs(monkeypatch, _ENCODE, TemplateValidationError("bad"))
    assert await _encodes_track(FakeSession(), _JOB, _SESSION, _track()) is False  # type: ignore[arg-type]


# --- stage_finished_track ------------------------------------------------------------------


@pytest.fixture
def woken(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr(early_staging, "wake_active_stager", lambda: calls.append(1))
    return calls


def _decide(monkeypatch: pytest.MonkeyPatch, env: Env, *, session: Any = _SESSION, encodes: bool = True) -> None:
    async def routed(_db: Any, _job: Any) -> Any:
        return session

    async def encodes_track(_db: Any, _job: Any, _sess: Any, _track: Any) -> bool:
        return encodes

    monkeypatch.setattr(early_staging, "settings", env.settings)
    monkeypatch.setattr(early_staging, "_auto_apply_session", routed)
    monkeypatch.setattr(early_staging, "_encodes_track", encodes_track)


async def _run(env: Env, *, job_status: JobStatus = JobStatus.RIPPING, seed_job: bool = True) -> list[TrackStage]:
    async with env.factory() as db:
        if seed_job:
            await add_job(db)
            job = await db.get(Job, JOB)
            assert job is not None
            job.status = job_status
        track = await add_track(env, db)
        await stage_finished_track(db, env.hub, track)  # type: ignore[arg-type]
    async with env.factory() as db:
        return list((await db.execute(select(TrackStage))).scalars().all())


async def test_a_finished_track_is_staged_committed_and_the_stager_woken(
    env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    _decide(monkeypatch, env)
    rows = await _run(env)
    assert [(r.track_id, r.status) for r in rows] == [("trk_a", StageStatus.PENDING)]
    assert woken == [1]
    assert env.hub.types() == ["stage.queued"]


async def test_a_held_job_stages_nothing(env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch) -> None:
    _decide(monkeypatch, env)
    assert await _run(env, job_status=JobStatus.AWAITING_REVIEW) == []
    assert woken == []


async def test_a_missing_job_stages_nothing(env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch) -> None:
    _decide(monkeypatch, env)
    assert await _run(env, seed_job=False) == []


async def test_no_auto_apply_session_stages_nothing(
    env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    _decide(monkeypatch, env, session=None)
    assert await _run(env) == []
    assert woken == []


async def test_a_session_that_does_not_encode_the_track_stages_nothing(
    env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    _decide(monkeypatch, env, encodes=False)
    assert await _run(env) == []


async def test_a_track_that_already_has_a_row_does_not_wake_the_stager_again(
    env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    _decide(monkeypatch, env)
    await _run(env)
    woken.clear()
    async with env.factory() as db:
        track = await db.get(Track, "trk_a")
        assert track is not None
        await stage_finished_track(db, env.hub, track)  # type: ignore[arg-type]
    assert woken == []


async def test_a_failure_is_swallowed_so_the_track_update_still_succeeds(
    env: Env, woken: list[int], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _decide(monkeypatch, env)

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(early_staging, "ensure_stage_rows", boom)
    assert await _run(env) == []
    assert "early staging skipped track_id=trk_a: db down" in caplog.text
