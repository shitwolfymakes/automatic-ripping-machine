from arm_common.config_metadata import CONFIG_FIELD_META, ConfigFieldMeta
from arm_common.schemas import ConfigUpdateRequest, ConfigView

_VALID_TIERS = {"secret", "operator", "infra"}
_VALID_TYPES = {"string", "bool", "enum", "string[]"}


def _by_key() -> dict[str, ConfigFieldMeta]:
    return {m.key: m for m in CONFIG_FIELD_META}


def test_registry_entries_are_well_formed():
    keys = [m.key for m in CONFIG_FIELD_META]
    assert len(keys) == len(set(keys)), "duplicate keys in CONFIG_FIELD_META"
    for m in CONFIG_FIELD_META:
        assert m.tier in _VALID_TIERS, m.key
        assert m.type in _VALID_TYPES, m.key
        assert m.group, m.key
        assert m.label, m.key
        assert m.help, m.key
        assert m.editable == (m.tier in {"operator", "secret"}), m.key
        assert (m.enum_values is not None) == (m.type == "enum"), m.key


def test_every_editable_config_field_has_metadata():
    meta = _by_key()
    for field in ConfigUpdateRequest.model_fields:
        assert field in meta, f"{field} editable but missing from CONFIG_FIELD_META"
        assert meta[field].tier in {"operator", "secret"}, field
        assert meta[field].editable is True, field


def test_operator_and_secret_keys_are_real_config_view_fields():
    view_fields = set(ConfigView.model_fields)
    for m in CONFIG_FIELD_META:
        if m.tier in {"operator", "secret"}:
            assert m.key in view_fields, f"{m.key} not a ConfigView field"
