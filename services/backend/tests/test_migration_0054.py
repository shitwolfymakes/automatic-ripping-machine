"""0054_job_failure_reason: jobs gains a nullable text failure_reason. Rendered offline like
test_migration_chain, so the DDL text and model parity are checked without a database."""

from __future__ import annotations

from arm_common import Job

from tests.test_migration_chain import _render_sql

_PARENT = "0053_drive_scanning"
_REV = "0054_job_failure_reason"


def test_0054_upgrade_adds_a_nullable_varchar_column() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE jobs ADD COLUMN failure_reason VARCHAR" in sql
    assert "NOT NULL" not in sql.split("failure_reason", 1)[1].split(";", 1)[0]
    assert "CREATE TYPE" not in sql


def test_0054_downgrade_drops_the_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE jobs DROP COLUMN failure_reason" in sql


def test_0054_matches_the_model() -> None:
    assert Job.__table__.columns["failure_reason"].nullable
