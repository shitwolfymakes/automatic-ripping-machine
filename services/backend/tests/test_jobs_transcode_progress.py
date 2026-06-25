"""Tests for the `transcode_progress` summary attached to `JobView`."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common.schemas.jobs import JobView, TranscodeProgressSummary  # noqa: E402


def test_transcode_progress_summary_shape() -> None:
    s = TranscodeProgressSummary(state="done", tasks_total=2, tasks_done=2, percent=100.0)
    assert s.model_dump() == {
        "state": "done",
        "tasks_total": 2,
        "tasks_done": 2,
        "percent": 100.0,
    }


def test_jobview_transcode_progress_defaults_none() -> None:
    view = JobView(
        id="job_x",
        drive_id="drv_x",
        disc_type="bluray",
        status="ripped",
        title="X",
        year=2000,
        metadata_json={},
        resumed_from_crash=False,
    )
    assert view.transcode_progress is None
