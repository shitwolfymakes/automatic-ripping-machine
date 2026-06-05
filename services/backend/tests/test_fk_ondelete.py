"""Foreign-key `ondelete` audit.

Locks down the cascade semantics that Postgres enforces at delete time
— we can't catch these with FakeSession because the in-memory test
doubles don't honour real FK constraints, and these failures only
surface when a real cascade fires in production.

The mapping below is the contract: when a parent row is deleted, what
happens to children? CASCADE = "go with it" (data is purely derived);
SET NULL = "keep the child but drop the link" (operational state we
want to preserve); RESTRICT = "block the delete" (the child is
authoritative state we don't want auto-orphaned).
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

import arm_common.models  # noqa: E402,F401  ensure all models are imported
from sqlmodel import SQLModel  # noqa: E402


_EXPECTED: dict[tuple[str, str], str] = {
    # transcode_tasks → tracks: CASCADE so deleting a Job (which cascades
    # tracks) doesn't trip on the FK from any transcode_task that ever
    # referenced one of those tracks. Job-level delete is the user-visible
    # operation; cascading the operational transcode-task row with it is
    # the right semantic. Originally RESTRICT — see migration 0008.
    ("transcode_tasks", "source_track_id"): "CASCADE",
    # transcode_tasks → session_applications: CASCADE so deleting a
    # session_application (which itself cascades from jobs) takes its
    # tasks with it. Already CASCADE since 0001.
    ("transcode_tasks", "session_application_id"): "CASCADE",
    # tracks → jobs, etc. — sanity-check the rest of the cascade chain
    # so a future model rewrite can't quietly downgrade these.
    ("tracks", "job_id"): "CASCADE",
    ("session_applications", "job_id"): "CASCADE",
    ("events", "job_id"): "CASCADE",
    ("disc_fingerprints", "job_id"): "CASCADE",
    # gpus.claimed_by_task_id → transcode_tasks: SET NULL because a
    # GPU shouldn't disappear when its claimant task does — only the
    # claim link is invalidated.
    ("gpus", "claimed_by_task_id"): "SET NULL",
}


@pytest.mark.parametrize(("table", "column"), sorted(_EXPECTED.keys()))
def test_fk_ondelete_matches_expected(table: str, column: str) -> None:
    expected = _EXPECTED[(table, column)]
    tbl = SQLModel.metadata.tables[table]
    fk = next(fk for fk in tbl.foreign_keys if fk.parent.name == column)
    assert fk.ondelete == expected, (
        f"{table}.{column} FK ondelete is {fk.ondelete!r}, expected {expected!r}. "
        "Change requires a migration + a deliberate decision; if you're "
        "downgrading from CASCADE, verify the parent-delete chain still works."
    )
