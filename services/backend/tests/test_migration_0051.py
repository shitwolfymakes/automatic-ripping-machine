"""0051_rip_end_on_completion: the global default on config and the per-drive override on drives. Rendered offline like
test_migration_chain, so the DDL text and model parity are checked without a database."""

from __future__ import annotations

from arm_common import Config, Drive

from tests.test_migration_chain import _render_sql

_PARENT = "0050_handbrake_settings"
_REV = "0051_rip_end_on_completion"


def test_0051_adds_a_not_null_global_that_defaults_off_and_a_nullable_drive_override() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE config ADD COLUMN rip_end_on_completion_message BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ALTER TABLE drives ADD COLUMN rip_end_on_completion_message BOOLEAN" in sql
    assert "CREATE TYPE" not in sql


def test_0051_downgrade_drops_both_columns() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE drives DROP COLUMN rip_end_on_completion_message" in sql
    assert "ALTER TABLE config DROP COLUMN rip_end_on_completion_message" in sql


def test_0051_matches_the_models() -> None:
    config = Config.__table__.columns["rip_end_on_completion_message"]  # type: ignore[attr-defined]
    assert not config.nullable
    assert str(config.server_default.arg) == "false"
    assert Drive.__table__.columns["rip_end_on_completion_message"].nullable  # type: ignore[attr-defined]
    assert Config(id=1).rip_end_on_completion_message is False
    assert Drive(id="d", hostname="h", device_path="/dev/sr0").rip_end_on_completion_message is None
