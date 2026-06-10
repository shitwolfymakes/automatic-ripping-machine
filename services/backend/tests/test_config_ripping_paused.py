"""Config model + config API carry ripping_paused (migration 0014)."""

from arm_common import Config


def test_config_ripping_paused_assignable() -> None:
    # server_default="false" is a DB-level default; a bare in-memory construct
    # may leave the attr unset until persisted, so assert assignability (matching
    # how test_config_tvdb_key handled the nullable field).
    cfg = Config(id=1)
    cfg.ripping_paused = False
    assert cfg.ripping_paused is False


def test_config_accepts_ripping_paused_true() -> None:
    cfg = Config(id=1, ripping_paused=True)
    assert cfg.ripping_paused is True
