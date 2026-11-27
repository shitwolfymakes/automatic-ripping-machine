"""0052_drop_track_sha256: the column goes, parity with the model. Rendered offline like
test_migration_chain, so no database is needed."""

from __future__ import annotations

from arm_common import Track

from tests.test_migration_chain import _render_sql

_PARENT = "0051_track_stages"
_REV = "0052_drop_track_sha256"


def test_0052_drops_the_column() -> None:
    assert "ALTER TABLE tracks DROP COLUMN sha256" in _render_sql(_PARENT, _REV)


def test_0052_downgrade_re_adds_a_nullable_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE tracks ADD COLUMN sha256 VARCHAR" in sql
    assert "NOT NULL" not in sql


def test_0052_matches_the_model() -> None:
    assert "sha256" not in Track.__table__.columns
