"""0060_config_min_title_length: a nullable column with a DB default of 120.

Existing rows stay NULL so the config seeder can fill them once from the
ripper's min-length env value, the way max_parallel_transcodes is seeded."""

from __future__ import annotations

from arm_common import Config
from tests.test_migration_chain import _render_sql

_PARENT = "0059_miss_defaults"
_REV = "0060_config_min_title_length"


def test_0060_adds_the_column_then_its_default() -> None:
    sql = _render_sql(_PARENT, _REV)
    add = sql.index("ALTER TABLE config ADD COLUMN min_title_length_seconds INTEGER")
    default = sql.index("ALTER TABLE config ALTER COLUMN min_title_length_seconds SET DEFAULT '120'")
    assert add < default
    assert "NOT NULL" not in sql[add:default]


def test_0060_matches_the_model() -> None:
    column = Config.__table__.columns["min_title_length_seconds"]  # type: ignore[attr-defined]
    assert column.nullable
    assert column.server_default is not None
    assert column.server_default.arg == "120"


def test_0060_downgrade_drops_the_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE config DROP COLUMN min_title_length_seconds" in sql
