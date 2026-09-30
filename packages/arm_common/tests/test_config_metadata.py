from arm_common import Config
from arm_common.config_metadata import CONFIG_FIELD_META, ConfigFieldMeta
from arm_common.schemas import ConfigUpdateRequest, ConfigView

_VALID_TIERS = {"secret", "operator", "infra"}
_VALID_TYPES = {"string", "bool", "int", "enum", "string[]", "ranked"}


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
        assert (m.enum_values is not None) == (m.type in {"enum", "ranked"}), m.key


# musicbrainz_user_agent is intentionally absent from CONFIG_FIELD_META (the UI
# no longer renders it — the backend now hardcodes MUSICBRAINZ_USER_AGENT next to
# its use). It stays on ConfigUpdateRequest/ConfigView because dropping it would
# be a wire (OpenAPI) change, out of scope for this pass; the field is simply
# dormant. See packages/arm_common/arm_common/config_metadata.py.
_DORMANT_EDITABLE_FIELDS = {"musicbrainz_user_agent"}


def test_every_editable_config_field_has_metadata():
    meta = _by_key()
    for field in ConfigUpdateRequest.model_fields:
        if field in _DORMANT_EDITABLE_FIELDS:
            assert field not in meta, f"{field} is marked dormant but still in CONFIG_FIELD_META"
            continue
        assert field in meta, f"{field} editable but missing from CONFIG_FIELD_META"
        assert meta[field].tier in {"operator", "secret"}, field
        assert meta[field].editable is True, field


def test_operator_and_secret_keys_are_real_config_view_fields():
    view_fields = set(ConfigView.model_fields)
    for m in CONFIG_FIELD_META:
        if m.tier in {"operator", "secret"}:
            assert m.key in view_fields, f"{m.key} not a ConfigView field"


def test_community_keydb_toggle_metadata_present():
    meta = {m.key: m for m in CONFIG_FIELD_META}
    m = meta["community_keydb_enabled"]
    assert m.group == "Ripping"
    assert m.tier == "operator"
    assert m.type == "bool"
    assert m.editable is True


def test_community_keydb_toggle_in_view_and_update():
    from arm_common.schemas import ConfigUpdateRequest, ConfigView

    assert "community_keydb_enabled" in ConfigView.model_fields
    assert "community_keydb_enabled" in ConfigUpdateRequest.model_fields


def test_enum_labels_cover_exactly_the_enum_values() -> None:
    for m in CONFIG_FIELD_META:
        if m.enum_labels is not None:
            assert m.type in {"enum", "ranked"}, m.key
            assert set(m.enum_labels) == set(m.enum_values or []), m.key


def test_enum_requires_names_real_secret_keys() -> None:
    secret_keys = {m.key for m in CONFIG_FIELD_META if m.tier == "secret"}
    for m in CONFIG_FIELD_META:
        if m.enum_requires is not None:
            assert m.type == "ranked", m.key
            assert set(m.enum_requires) <= set(m.enum_values or []), m.key
            assert set(m.enum_requires.values()) <= secret_keys, m.key


def test_identity_settings_meta() -> None:
    by_key = {m.key: m for m in CONFIG_FIELD_META}
    eps = by_key["episode_sources"]
    assert (eps.group, eps.tier, eps.type, eps.editable) == ("Metadata", "operator", "ranked", True)
    assert eps.enum_values == ["tmdb", "tvmaze", "tvdb"]
    assert eps.enum_labels == {"tmdb": "TMDb", "tvmaze": "TVmaze", "tvdb": "TVDB"}
    assert eps.enum_requires == {"tmdb": "tmdb_api_key", "tvdb": "tvdb_api_key"}
    hints = by_key["disc_hint_sources"]
    assert (hints.type, hints.enum_values) == ("ranked", ["bd_title", "label"])
    assert hints.enum_labels == {"bd_title": "Blu-ray disc title", "label": "Volume label"}
    assert hints.enum_requires is None
    assert by_key["episode_match_tolerance_seconds"].type == "int"
    assert by_key["episode_auto_apply"].type == "bool"


def test_config_model_defaults_for_identity_settings() -> None:
    cfg = Config()
    assert cfg.episode_sources == ["tmdb", "tvmaze", "tvdb"]
    assert cfg.disc_hint_sources == ["bd_title", "label"]
    assert cfg.episode_match_tolerance_seconds == 300
    assert cfg.episode_auto_apply is True
    assert Config().episode_sources is not cfg.episode_sources  # no shared mutable default
