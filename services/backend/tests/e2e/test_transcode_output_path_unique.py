"""The live-output_path partial unique index is built on SQLite too.

0001 creates it on Postgres; the model mirrors it with `sqlite_where` so the
metadata-built schema this tier uses enforces the same rule: one live
(queued / in_progress / done) task per output_path, failed tasks exempt.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from arm_common import TranscodeTask


def _row(task_id: str, status: str) -> dict[str, str]:
    return {
        "id": task_id,
        "session_application_id": "sap_1",
        "source_track_id": "trk_1",
        "status": status,
        "output_path": "/media/out.mkv",
    }


def test_two_live_tasks_cannot_share_an_output_path() -> None:
    engine = create_engine("sqlite://")
    table = TranscodeTask.__table__  # type: ignore[attr-defined]
    table.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(table), [_row("txt_failed", "failed"), _row("txt_live", "queued")])
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(table), [_row("txt_dup", "done")])
    engine.dispose()
