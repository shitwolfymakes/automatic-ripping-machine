from arm_common import Config


def test_config_has_makemkv_status_columns_defaulting_none():
    cfg = Config(id=1)
    assert cfg.makemkv_key_valid is None
    assert cfg.makemkv_key_state is None
    assert cfg.makemkv_key_checked_at is None
