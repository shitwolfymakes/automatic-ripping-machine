"""0046_disc_fingerprint_created_at: backfill the NULL created_at values 0006
left behind, then match the model's NOT NULL DEFAULT now(). Rendered offline
like test_migration_chain."""

from __future__ import annotations


from arm_common import DiscFingerprint
from tests.test_migration_chain import _render_sql

_PARENT = "0045_transcode_task_started_at"
_REV = "0046_disc_fingerprint_created_at"


def test_0046_backfills_before_setting_not_null() -> None:
    sql = _render_sql(_PARENT, _REV)
    backfill = sql.index("UPDATE disc_fingerprints SET created_at = COALESCE(")
    assert "WHERE created_at IS NULL" in sql
    default = sql.index("ALTER TABLE disc_fingerprints ALTER COLUMN created_at SET DEFAULT now()")
    not_null = sql.index("ALTER TABLE disc_fingerprints ALTER COLUMN created_at SET NOT NULL")
    assert backfill < default and backfill < not_null


def test_0046_matches_the_model() -> None:
    column = DiscFingerprint.__table__.columns["created_at"]  # type: ignore[attr-defined]
    assert not column.nullable
    assert column.server_default is not None


def test_0046_downgrade_restores_the_0006_shape() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE disc_fingerprints ALTER COLUMN created_at DROP NOT NULL" in sql
    assert "ALTER TABLE disc_fingerprints ALTER COLUMN created_at DROP DEFAULT" in sql
