"""0051_track_title_class: four nullable VARCHAR columns on tracks, no native
enum type. Rendered offline like test_migration_chain."""

from __future__ import annotations

from arm_common import Track
from tests.test_migration_chain import _render_sql

_PARENT = "0050_handbrake_settings"
_REV = "0051_track_title_class"
_COLUMNS = ("source_file", "playlist_name", "title_class", "title_class_ref")


def test_0051_adds_four_nullable_varchar_columns() -> None:
    sql = _render_sql(_PARENT, _REV)
    for name in _COLUMNS:
        assert f"ALTER TABLE tracks ADD COLUMN {name} VARCHAR" in sql
    assert "NOT NULL" not in sql
    assert "CREATE TYPE" not in sql


def test_0051_matches_the_model() -> None:
    columns = Track.__table__.columns  # type: ignore[attr-defined]
    for name in _COLUMNS:
        assert columns[name].nullable


def test_0051_downgrade_drops_them() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    for name in _COLUMNS:
        assert f"ALTER TABLE tracks DROP COLUMN {name}" in sql
