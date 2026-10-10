"""0035_session_routes_seed_marker: the seed-marker UPDATE must be
conditional on session_routes having rows, or an existing deployment that
never shipped the seeder (empty table, never seeded) gets permanently
flagged seeded=true and never receives the built-in routes (G-17 then only
works on fresh databases). Rendered offline like test_migration_chain."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from tests.test_migration_chain import _render_sql  # noqa: E402

_PARENT = "0034_session_routes"
_REV = "0035_session_routes_seed_marker"


def test_0035_adds_the_seeded_column() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE config ADD COLUMN session_routes_seeded BOOLEAN DEFAULT false NOT NULL" in sql


def test_0035_update_is_conditional_on_session_routes_having_rows() -> None:
    """The bug: an unconditional UPDATE marks EVERY existing deployment
    seeded=true, including one whose session_routes table is empty because
    the seeder never shipped for it (not because a user deliberately
    cleared it) — that install then never receives the built-in routes.
    The fix scopes the UPDATE with `WHERE EXISTS (SELECT 1 FROM
    session_routes)`: only a deployment that already has rows (proof the
    old empty-table seed gate already fired) gets marked seeded up front.
    """
    sql = _render_sql(_PARENT, _REV)
    assert "UPDATE config SET session_routes_seeded" in sql
    assert "WHERE EXISTS (SELECT 1 FROM session_routes)" in sql


def test_0035_downgrade_drops_the_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE config DROP COLUMN session_routes_seeded" in sql
