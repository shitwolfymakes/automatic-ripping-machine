"""0039_identity_core: provenance + episode_number_end columns, role -> enum
values, role_source / video_type dropped, TheDiscDB map moved into
identity_claims. Rendered offline like test_migration_chain; the role backfill
is executed against in-memory SQLite by value.
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
    (move,) = [u for u in _updates(sql, "jobs") if "- 'thediscdb'" in u]
    assert "jsonb_each" in move
    assert "jsonb_strip_nulls" in move
    assert "WHERE jsonb_typeof(metadata_json::jsonb -> 'thediscdb') = 'object'" in move


def test_0039_move_drops_empty_title_and_filename() -> None:
    """An empty TheDiscDB title / filename is no opinion, not a proposal of ''."""
    sql = _render_sql(_PARENT, _REV)
    (move,) = [u for u in _updates(sql, "jobs") if "- 'thediscdb'" in u]
    assert "'episode_name', to_jsonb(NULLIF(m.value ->> 'title', ''))" in move
    assert "'filename', to_jsonb(NULLIF(m.value ->> 'filename', ''))" in move


def test_0039_seeds_manual_claims_for_legacy_operator_choices() -> None:
    """Operator exclusions / roles made before the upgrade disagree with the
    moved disc map; `excluded` and `role` are unguarded in the resolver, so
    they are kept by seeding `manual` claims from the stored columns."""
    sql = _render_sql(_PARENT, _REV)
    jobs_updates = _updates(sql, "jobs")
    (seed,) = [u for u in jobs_updates if "'{identity_claims,sources,manual}'" in u]
    (move,) = [u for u in jobs_updates if "- 'thediscdb'" in u]
    # Reads the moved thediscdb claims, so it must run after the move.
    assert sql.index(move) < sql.index(seed)
    assert "FROM tracks t" in seed
    assert "ARRAY['identity_claims', 'sources', 'thediscdb', 'tracks', t.source_ref]" in seed
    # selected: only where the claim equals the stored `excluded` (= disagrees).
    assert "WHEN c.claim -> 'selected' = to_jsonb(t.excluded) THEN NOT t.excluded" in seed
    # role: only a non-null stored role that differs from the claim's.
    assert "t.role IS NOT NULL" in seed
    assert "c.claim -> 'role' <> to_jsonb(t.role)" in seed
    # Agreeing tracks contribute nothing; existing manual claims are merged.
    assert "f.fields <> '{}'::jsonb" in seed
    assert "ARRAY['identity_claims', 'sources', 'manual', 'tracks', t.source_ref]" in seed
    # Nothing else in the upgrade touches jobs after the seed.
    assert sql.index(seed) == max(sql.index(u) for u in jobs_updates)


def test_0039_downgrade_restores_columns() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE tracks ADD COLUMN role_source VARCHAR" in sql
    assert "ALTER TABLE tracks ADD COLUMN video_type VARCHAR" in sql
    assert "ALTER TABLE tracks DROP COLUMN identity_provenance" in sql
    assert "ALTER TABLE jobs DROP COLUMN identity_provenance" in sql
    assert "- 'identity_claims'" in sql
    # role_source restore reads identity_provenance, so both the role
    # reverse-mapping and the role_source restore must run before the
    # column is dropped.
    role_update = sql.index("UPDATE tracks SET role = CASE role")
    role_source_update = sql.index("UPDATE tracks SET role_source")
    drop_identity_provenance = sql.index("ALTER TABLE tracks DROP COLUMN identity_provenance")
    assert role_update < drop_identity_provenance
    assert role_source_update < drop_identity_provenance
