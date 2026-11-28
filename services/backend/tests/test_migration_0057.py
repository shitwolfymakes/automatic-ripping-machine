"""0057_tick_one_version: `config.tick_one_version` (NOT NULL, default true) and
`jobs.tick_one_version` (nullable, backfilled true for video jobs not yet started).
Rendered offline like test_migration_chain."""

from __future__ import annotations

from arm_common import Config, Job
from tests.test_migration_chain import _render_sql

_PARENT = "0056_rip_end_on_completion"
_REV = "0057_tick_one_version"


def test_0057_adds_the_config_default_not_null_true() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE config ADD COLUMN tick_one_version BOOLEAN DEFAULT 'true' NOT NULL" in sql


def test_0057_adds_a_nullable_job_column() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE jobs ADD COLUMN tick_one_version BOOLEAN" in sql
    assert "ALTER TABLE jobs ADD COLUMN tick_one_version BOOLEAN NOT NULL" not in sql


def test_0057_backfills_video_jobs_before_start() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "UPDATE jobs SET tick_one_version = true" in sql
    for status in ("created", "awaiting_user_id", "identified", "awaiting_review"):
        assert f"'{status}'" in sql
    for disc_type in ("dvd", "bluray"):
        assert f"'{disc_type}'" in sql


def test_0057_matches_the_models() -> None:
    config = Config.__table__.columns["tick_one_version"]  # type: ignore[attr-defined]
    job = Job.__table__.columns["tick_one_version"]  # type: ignore[attr-defined]
    assert not config.nullable
    assert job.nullable


def test_0057_downgrade_drops_both() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE config DROP COLUMN tick_one_version" in sql
    assert "ALTER TABLE jobs DROP COLUMN tick_one_version" in sql
