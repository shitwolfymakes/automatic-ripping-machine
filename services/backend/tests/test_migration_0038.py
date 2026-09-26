"""0038_encoder_first: transcode_presets.encoder replaces codec + hw_preference,
and gpus gains probed_at/probe_error with encoder_kinds reset. Rendered offline
like test_migration_chain; the rendered backfill UPDATEs are then executed
against an in-memory SQLite table so every legacy (tool, codec, hw_preference)
combination is checked by value, not just by SQL text."""

from __future__ import annotations

import os
import re
import sqlite3

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common import Gpu, TranscodePreset  # noqa: E402

from tests.test_migration_chain import _render_sql  # noqa: E402

_PARENT = "0037_transcode_enabled"
_REV = "0038_encoder_first"


def _preset_update(sql: str) -> str:
    match = re.search(r"UPDATE transcode_presets SET.*?;", sql, re.DOTALL)
    assert match is not None, "no transcode_presets backfill rendered"
    return match.group(0)


def _split_part(value: str, delimiter: str, index: int) -> str:
    """Postgres split_part: 1-based field, empty string past the end."""
    parts = value.split(delimiter)
    return parts[index - 1] if index <= len(parts) else ""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.create_function("split_part", 3, _split_part)
    return conn


def test_0038_upgrade_adds_encoder_and_drops_legacy_columns() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE transcode_presets ADD COLUMN encoder VARCHAR DEFAULT 'preset' NOT NULL" in sql
    assert "ALTER TABLE transcode_presets DROP COLUMN hw_preference" in sql
    assert "ALTER TABLE transcode_presets DROP COLUMN codec" in sql
    # The backfill must run before the columns it reads are dropped.
    assert sql.index("UPDATE transcode_presets") < sql.index("DROP COLUMN hw_preference")
    assert sql.index("UPDATE transcode_presets") < sql.index("DROP COLUMN codec")


def test_0038_upgrade_backfills_every_legacy_combination() -> None:
    update = _preset_update(_render_sql(_PARENT, _REV))
    conn = _db()
    conn.execute(
        "CREATE TABLE transcode_presets (id TEXT, tool TEXT, codec TEXT, hw_preference TEXT, "
        "encoder TEXT NOT NULL DEFAULT 'preset')"
    )
    rows = [
        ("hb_default", "handbrake", None, None, "preset"),
        ("hb_cpu", "handbrake", "h265", "cpu_only", "cpu_h265"),
        ("hb_any", "handbrake", "h264", "any", "any_h264"),
        ("hb_null_pref", "handbrake", "av1", None, "any_av1"),
        ("abcde_codec", "abcde", "h265", None, "preset"),
        ("none_tool", "none", None, None, "preset"),
    ]
    conn.executemany(
        "INSERT INTO transcode_presets (id, tool, codec, hw_preference) VALUES (?, ?, ?, ?)",
        [r[:4] for r in rows],
    )
    conn.execute(update)
    got = dict(conn.execute("SELECT id, encoder FROM transcode_presets").fetchall())
    assert got == {r[0]: r[4] for r in rows}


def test_0038_upgrade_adds_unprobed_gpu_columns_and_resets_encoder_kinds() -> None:
    sql = _render_sql(_PARENT, _REV)
    # Nullable ADD COLUMN with no default: every existing row reads NULL.
    assert "ALTER TABLE gpus ADD COLUMN probed_at TIMESTAMP WITH TIME ZONE;" in sql
    assert "ALTER TABLE gpus ADD COLUMN probe_error VARCHAR;" in sql
    assert "UPDATE gpus SET encoder_kinds = '{}'" in sql


def test_0038_downgrade_restores_codec_and_hw_preference() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE gpus DROP COLUMN probe_error" in sql
    assert "ALTER TABLE gpus DROP COLUMN probed_at" in sql
    assert "ALTER TABLE transcode_presets ADD COLUMN codec VARCHAR" in sql
    assert "ALTER TABLE transcode_presets ADD COLUMN hw_preference VARCHAR" in sql
    assert "ALTER TABLE transcode_presets DROP COLUMN encoder" in sql
    assert sql.index("UPDATE transcode_presets") < sql.index("DROP COLUMN encoder")

    conn = _db()
    conn.execute("CREATE TABLE transcode_presets (id TEXT, encoder TEXT, codec TEXT, hw_preference TEXT)")
    conn.executemany(
        "INSERT INTO transcode_presets (id, encoder) VALUES (?, ?)",
        [("cpu", "cpu_h265"), ("any", "any_h264"), ("preset", "preset")],
    )
    conn.execute(_preset_update(sql))
    got = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, codec, hw_preference FROM transcode_presets")}
    assert got == {"cpu": ("h265", "cpu_only"), "any": ("h264", None), "preset": (None, None)}


def test_0038_matches_the_models() -> None:
    """Model and migration parity for the columns this revision touches."""
    columns = TranscodePreset.__table__.columns
    assert "codec" not in columns
    assert "hw_preference" not in columns
    assert not columns["encoder"].nullable
    assert columns["encoder"].server_default is not None
    assert Gpu.__table__.columns["probed_at"].nullable
    assert Gpu.__table__.columns["probe_error"].nullable
