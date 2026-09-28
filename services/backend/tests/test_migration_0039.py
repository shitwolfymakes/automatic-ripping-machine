"""0039_identity_core: provenance + episode_number_end columns, role -> enum
values, role_source / video_type dropped, TheDiscDB map moved into
identity_claims. Rendered offline like test_migration_chain; the role backfill
is executed against in-memory SQLite by value.

Note: `_render_sql(from_rev, to_rev)` without `downgrade=True` does not render
a downgrade when `from_rev` is the newer revision (verified empirically: it
renders an empty transaction). The downgrade path is instead exercised in the
manual Postgres check documented in the task report, so there is no
`test_0039_downgrade_restores_columns` here.
"""

from __future__ import annotations

import os
import re
import sqlite3

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from tests.test_migration_chain import _render_sql  # noqa: E402

_PARENT = "0038_encoder_first"
_REV = "0039_identity_core"


def _updates(sql: str, table: str) -> list[str]:
    return re.findall(rf"UPDATE {table} SET.*?;", sql, re.DOTALL)


def test_0039_adds_and_drops_columns_in_order() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE tracks ADD COLUMN episode_number_end INTEGER" in sql
    assert "ALTER TABLE tracks ADD COLUMN identity_provenance JSON" in sql
    assert "ALTER TABLE jobs ADD COLUMN identity_provenance JSON" in sql
    assert "ALTER TABLE tracks DROP COLUMN role_source" in sql
    assert "ALTER TABLE tracks DROP COLUMN video_type" in sql
    # video_type is read by the role backfill, so it must be dropped after it.
    first_role_update = sql.index("UPDATE tracks SET role")
    assert first_role_update < sql.index("DROP COLUMN video_type")


def test_0039_role_backfill_by_value() -> None:
    sql = _render_sql(_PARENT, _REV)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tracks (id TEXT, role TEXT, video_type TEXT)")
    rows = [
        ("a", None, "series"),
        ("b", None, "movie"),
        ("c", None, "garbage"),
        ("d", "MainMovie", None),
        ("e", "Episode", "movie"),
        ("f", "Featurette", None),
        ("g", "Trailer", None),
        ("h", "SomethingNew", None),
        ("i", "extra", None),
        ("j", None, None),
    ]
    conn.executemany("INSERT INTO tracks VALUES (?, ?, ?)", rows)
    for stmt in _updates(sql, "tracks"):
        conn.execute(stmt)
    got = dict(conn.execute("SELECT id, role FROM tracks").fetchall())
    assert got == {
        "a": "episode",
        "b": "main",
        "c": None,
        "d": "main",
        "e": "episode",
        "f": "extra",
        "g": "trailer",
        "h": "other",
        "i": "extra",
        "j": None,
    }


def test_0039_moves_thediscdb_map_into_identity_claims() -> None:
    sql = _render_sql(_PARENT, _REV)
    (move,) = [u for u in _updates(sql, "jobs") if "identity_claims" in u]
    assert "- 'thediscdb'" in move
    assert "jsonb_each" in move
    assert "jsonb_strip_nulls" in move
    assert "WHERE jsonb_typeof(metadata_json::jsonb -> 'thediscdb') = 'object'" in move
