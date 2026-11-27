"""0051_track_stages: the table, its two indexes, and parity with the model. Rendered offline like
test_migration_chain, so no database is needed."""

from __future__ import annotations

from arm_common import TrackStage

from tests.test_migration_chain import _render_sql

_PARENT = "0050_handbrake_settings"
_REV = "0051_track_stages"


def test_0051_creates_the_table_and_indexes_without_a_native_enum() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "CREATE TABLE track_stages" in sql
    assert "status VARCHAR DEFAULT 'pending' NOT NULL" in sql
    assert "CREATE UNIQUE INDEX ix_track_stages_track_id ON track_stages (track_id)" in sql
    assert "CREATE INDEX ix_track_stages_job_id ON track_stages (job_id)" in sql
    assert "REFERENCES tracks (id) ON DELETE CASCADE" in sql
    assert "REFERENCES jobs (id) ON DELETE CASCADE" in sql
    assert "CREATE TYPE" not in sql


def test_0051_downgrade_drops_the_table() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "DROP TABLE track_stages" in sql
    assert "CREATE TYPE" not in sql


def test_0051_matches_the_model() -> None:
    sql = _render_sql(_PARENT, _REV)
    for column in TrackStage.__table__.columns:
        assert f"{column.name} " in sql, f"0051 does not create track_stages.{column.name}"
    assert TrackStage.__table__.columns["track_id"].unique
    assert str(TrackStage.__table__.columns["status"].type) == "VARCHAR"
    assert not TrackStage.__table__.columns["status"].nullable
