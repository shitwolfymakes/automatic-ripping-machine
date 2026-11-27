"""Dispatcher tests that predate the staging gate mostly don't care where a task's source lives.

`staged_by_default` makes every track look STAGED unless the test seeds `db.rows["track_stages"]` itself,
which switches that session to its real rows (so the gate's own tests see exactly what they put there)."""

from __future__ import annotations

from typing import Any

import pytest

from arm_backend import transcode_dispatcher
from arm_backend.staging import stage_for_track
from arm_common import StageStatus, TrackStage


def staged_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stage(db: Any, track_id: str) -> TrackStage | None:
        if "track_stages" in db.rows:
            return await stage_for_track(db, track_id)
        return TrackStage(
            track_id=track_id,
            job_id="job_x",
            status=StageStatus.STAGED,
            source_path=f"/raw/job_x/{track_id}.mkv",
            dest_path=f"/raw/.staging/job_x/{track_id}.mkv",
        )

    monkeypatch.setattr(transcode_dispatcher, "stage_for_track", _stage)
