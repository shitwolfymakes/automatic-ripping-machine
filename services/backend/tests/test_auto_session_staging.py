"""Fan-out creates stage rows for encode presets only, and wakes the stager when it did."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import select

from arm_backend import auto_session
from arm_backend.transcode_apply import ResolvedTask
from arm_common import StageStatus, TrackStage, TranscodeTool
from tests._stage_env import Env, add_job, add_track

_ENCODE = SimpleNamespace(tool=TranscodeTool.HANDBRAKE)
_PASSTHROUGH = SimpleNamespace(tool=TranscodeTool.NONE)


@pytest.fixture
def woken(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr(auto_session, "wake_active_stager", lambda: calls.append(1))
    return calls


async def _fan_out(env: Env, preset: Any, wanted: list[str]) -> list[TrackStage]:
    async with env.factory() as db:
        await add_job(db)
        tracks = [await add_track(env, db, tid) for tid in ("trk_a", "trk_b")]
        resolved = [ResolvedTask(t, f"{t}.mkv") for t in wanted]
        await auto_session._stage_resolved_tracks(db, env.hub, preset, tracks, resolved)  # type: ignore[arg-type]
        await db.commit()
        return list((await db.execute(select(TrackStage))).scalars().all())


async def test_an_encode_fan_out_stages_the_tracks_it_reads_and_wakes_the_stager(
    env: Env,
    woken: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_session, "settings", env.settings)
    rows = await _fan_out(env, _ENCODE, ["trk_a"])
    assert [(r.track_id, r.status) for r in rows] == [("trk_a", StageStatus.PENDING)]
    assert woken == [1]
    assert env.hub.types() == ["stage.queued"]


async def test_a_passthrough_fan_out_stages_nothing(env: Env, woken: list[int]) -> None:
    assert await _fan_out(env, _PASSTHROUGH, ["trk_a"]) == []
    assert woken == [] and env.hub.calls == []


async def test_no_preset_is_passthrough_and_stages_nothing(env: Env, woken: list[int]) -> None:
    assert await _fan_out(env, None, ["trk_a"]) == []
    assert woken == []


async def test_a_fan_out_that_created_nothing_does_not_wake_the_stager(
    env: Env,
    woken: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_session, "settings", env.settings)
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db, "trk_a")
        await auto_session._stage_resolved_tracks(db, env.hub, _ENCODE, [track], [])  # type: ignore[arg-type]
    assert woken == [] and env.hub.calls == []
