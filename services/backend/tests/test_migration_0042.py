"""0042_setup_state: first-run walkthrough columns on config, plus the backfill
that keeps an install already in use (admin password changed) out of the
walkthrough after upgrading. Rendered offline like test_migration_chain."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from tests.test_migration_chain import _render_sql  # noqa: E402

_PARENT = "0041_virtual_drives"
_REV = "0042_setup_state"


def test_0042_adds_the_setup_columns() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE config ADD COLUMN setup_completed_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ALTER TABLE config ADD COLUMN setup_progress JSONB DEFAULT '{}'::jsonb NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN setup_checklist_dismissed_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ALTER TABLE config ADD COLUMN makemkv_key_checked_by_drive_id VARCHAR" in sql


def test_0042_backfill_only_marks_installs_in_use_complete() -> None:
    """A fresh install (admin still must change the default password) keeps
    setup_completed_at NULL so the walkthrough shows; an install in use is
    marked complete so upgrading never drops an operator into first-run."""
    sql = _render_sql(_PARENT, _REV)
    assert "UPDATE config SET setup_completed_at = now()" in sql
    assert "WHERE EXISTS (SELECT 1 FROM users WHERE username = 'admin' AND password_must_change = false)" in sql


def test_0042_downgrade_drops_the_columns() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    for col in (
        "setup_completed_at",
        "setup_progress",
        "setup_checklist_dismissed_at",
        "makemkv_key_checked_by_drive_id",
    ):
        assert f"ALTER TABLE config DROP COLUMN {col}" in sql
