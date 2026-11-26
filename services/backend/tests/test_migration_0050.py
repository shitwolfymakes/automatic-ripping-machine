"""0050_handbrake_settings: transcode_presets.preset_json is replaced by
handbrake_settings and handbrake_schemas is created. Rendered offline like
test_migration_chain, so the DDL text and model parity are checked without a
database."""

from __future__ import annotations

from arm_common import HandbrakeSchemaRecord, TranscodePreset

from tests.test_migration_chain import _render_sql

_PARENT = "0049_transcode_task_telemetry"
_REV = "0050_handbrake_settings"


def test_0050_upgrade_swaps_the_preset_column_and_creates_the_schema_table() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE transcode_presets DROP COLUMN preset_json" in sql
    assert "ALTER TABLE transcode_presets ADD COLUMN handbrake_settings JSONB" in sql
    assert "CREATE TABLE handbrake_schemas" in sql
    assert "CREATE TYPE" not in sql


def test_0050_downgrade_restores_preset_json_and_drops_the_table() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE transcode_presets ADD COLUMN preset_json JSONB" in sql
    assert "ALTER TABLE transcode_presets DROP COLUMN handbrake_settings" in sql
    assert "DROP TABLE handbrake_schemas" in sql


def test_0050_matches_the_models() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert TranscodePreset.__table__.columns["handbrake_settings"].nullable
    assert "preset_json" not in TranscodePreset.__table__.columns
    table = HandbrakeSchemaRecord.__table__
    for column in table.columns:
        assert f"{column.name} " in sql, f"0050 does not create handbrake_schemas.{column.name}"
    assert table.columns["content_hash"].unique


def test_schema_record_ids_use_the_hbs_prefix() -> None:
    from datetime import UTC, datetime

    record = HandbrakeSchemaRecord(
        content_hash="h",
        handbrake_tag="1.9.0",
        preset_version="1",
        image_ref="img",
        raw={},
        fetched_at=datetime.now(UTC),
    )
    assert record.id.startswith("hbs_")
