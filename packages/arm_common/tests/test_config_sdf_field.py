from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.models.config import Config


def test_config_has_sdf_columns():
    c = Config()
    # server_default is DB-level; the bare in-memory instance carries None.
    assert hasattr(c, "makemkv_sdf_enabled")
    assert hasattr(c, "makemkv_sdf_state")
    assert hasattr(c, "makemkv_sdf_checked_at")


def test_config_metadata_has_sdf_field():
    field = next((f for f in CONFIG_FIELD_META if f.key == "makemkv_sdf_enabled"), None)
    assert field is not None
    assert field.type == "bool"
    assert field.editable is True
    assert field.group == "Ripping"
