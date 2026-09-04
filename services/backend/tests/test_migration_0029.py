"""0029_drive_lifecycle: columns for spec §1/§2, rendered offline like test_migration_chain."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common import Config, Drive  # noqa: E402

from tests.test_migration_chain import _render_sql  # noqa: E402

_PARENT = "0028_user_role_disabled"
_REV = "0029_drive_lifecycle"

_DRIVE_COLS = ("by_id_name", "sysfs_port", "identity_kind", "lifecycle", "present", "vendor", "model", "last_error")
_CONFIG_COLS = ("drive_scan_interval_seconds", "drive_detected_prune_days")


def test_0029_upgrade_adds_every_column() -> None:
    sql = _render_sql(_PARENT, _REV)
    for name in _DRIVE_COLS:
        assert f"ALTER TABLE drives ADD COLUMN {name} " in sql, name
    for name in _CONFIG_COLS:
        assert f"ALTER TABLE config ADD COLUMN {name} " in sql, name
    assert "ALTER TABLE drives ADD COLUMN lifecycle VARCHAR DEFAULT 'enrolled' NOT NULL" in sql
    assert "ALTER TABLE drives ADD COLUMN present BOOLEAN DEFAULT 'true' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN drive_scan_interval_seconds INTEGER DEFAULT '30' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN drive_detected_prune_days INTEGER DEFAULT '7' NOT NULL" in sql
    assert "UNIQUE (by_id_name)" in sql


def test_0029_downgrade_drops_every_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    for name in _DRIVE_COLS:
        assert f"ALTER TABLE drives DROP COLUMN {name}" in sql, name
    for name in _CONFIG_COLS:
        assert f"ALTER TABLE config DROP COLUMN {name}" in sql, name


def test_0029_matches_the_models() -> None:
    """Model↔migration parity: NOT NULL + server_default must agree, or the
    app queries a shape the schema doesn't have — a boot failure, not a test one."""
    for name in ("lifecycle", "present"):
        col = Drive.__table__.columns[name]
        assert not col.nullable, name
        assert col.server_default is not None, name
    for name in _CONFIG_COLS:
        col = Config.__table__.columns[name]
        assert not col.nullable, name
        assert col.server_default is not None, name
    assert Drive.__table__.columns["by_id_name"].unique is True
