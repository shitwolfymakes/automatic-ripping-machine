"""Config model carries the nullable tvdb_api_key field (migration 0013)."""

from arm_common import Config


def test_config_defaults_tvdb_api_key_to_none() -> None:
    cfg = Config(id=1)
    assert cfg.tvdb_api_key is None


def test_config_accepts_tvdb_api_key() -> None:
    cfg = Config(id=1, tvdb_api_key="tvdb-secret")
    assert cfg.tvdb_api_key == "tvdb-secret"
