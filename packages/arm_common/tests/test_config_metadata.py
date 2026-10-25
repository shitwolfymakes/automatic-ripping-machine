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
            assert m.type in ("ranked", "enum"), m.key
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
    assert hints.enum_labels == {"bd_title": "Blu-ray disc title", "label": "Disc volume label"}
    assert hints.enum_requires is None
    assert by_key["episode_match_tolerance_seconds"].type == "int"
    assert by_key["episode_auto_apply"].type == "bool"
    movies = by_key["movie_sources"]
    assert (movies.group, movies.tier, movies.type, movies.editable) == ("Metadata", "operator", "ranked", True)
    assert movies.enum_values == ["tmdb", "omdb"]
    assert movies.enum_labels == {"tmdb": "TMDb", "omdb": "OMDb"}
    assert movies.enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"}
    music = by_key["music_sources"]
    assert (music.type, music.enum_values, music.enum_requires) == ("ranked", ["musicbrainz"], None)
    assert music.enum_labels == {"musicbrainz": "MusicBrainz"}
    movie_sp = by_key["search_provider_movie"]
    assert (movie_sp.type, movie_sp.enum_values) == ("enum", ["tmdb", "omdb"])
    assert movie_sp.enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key"}
    tv_sp = by_key["search_provider_tv"]
    assert (tv_sp.type, tv_sp.enum_values) == ("enum", ["tmdb", "omdb", "tvmaze", "tvdb"])
    assert tv_sp.enum_labels == {"tmdb": "TMDb", "omdb": "OMDb", "tvmaze": "TVmaze", "tvdb": "TVDB"}
    assert tv_sp.enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key", "tvdb": "tvdb_api_key"}
    music_sp = by_key["search_provider_music"]
    assert (music_sp.type, music_sp.enum_values, music_sp.enum_requires) == ("enum", ["musicbrainz"], None)
    for key, label in (
        ("movie_auto_apply", "Apply confident movie matches"),
        ("music_auto_apply", "Apply confident music matches"),
    ):
        meta = by_key[key]
        # setup_step mirrors the movie_sources entry, which carries none.
        assert (meta.type, meta.group, meta.editable, meta.setup_step) == ("bool", "Metadata", True, None)
        assert meta.setup_step == by_key["movie_sources"].setup_step
        assert meta.label == label
        assert "Review first" in meta.help
    assert by_key["episode_auto_apply"].help == (
        "When off, a TV show match and every episode match are kept as suggestions to confirm on the job page; "
        "the disc is held with no countdown. Ripping › Review first still holds every disc."
    )
    assert by_key["crc64service_enabled"].type == "bool"
    assert "metadata_provider" not in by_key
    # The wizard asks for the movie search provider, in the slot the removed
    # `metadata_provider` held; the rest are Settings-only.
    assert (by_key["search_provider_movie"].setup_step, by_key["search_provider_movie"].setup_order) == ("metadata", 4)
    for key in (
        "movie_sources",
        "music_sources",
        "search_provider_tv",
        "search_provider_music",
        "crc64service_enabled",
    ):
        assert by_key[key].setup_step is None, key


def test_config_model_defaults_for_identity_settings() -> None:
    cfg = Config()
    assert cfg.episode_sources == ["tmdb", "tvmaze", "tvdb"]
    assert cfg.disc_hint_sources == ["bd_title", "label"]
    assert cfg.episode_match_tolerance_seconds == 300
    assert cfg.episode_auto_apply is True
    assert cfg.movie_sources == ["tmdb", "omdb"]
    assert cfg.music_sources == ["musicbrainz"]
    assert (cfg.search_provider_movie, cfg.search_provider_tv, cfg.search_provider_music) == (
        "tmdb",
        "tmdb",
        "musicbrainz",
    )
    assert cfg.movie_auto_apply is True
    assert cfg.music_auto_apply is True
    assert cfg.crc64service_enabled is True
    assert not hasattr(cfg, "metadata_provider")
    assert Config().episode_sources is not cfg.episode_sources  # no shared mutable default
    assert Config().movie_sources is not cfg.movie_sources


def test_iso_cap_meta() -> None:
    m = {x.key: x for x in CONFIG_FIELD_META}["max_parallel_iso_rips"]
    assert (m.group, m.tier, m.type, m.editable) == ("Ripping", "operator", "int", True)


def test_drive_defaults_optical() -> None:
    from arm_common import Drive

    d = Drive(hostname="h", device_path="/dev/sr0")
    assert d.kind == "optical"
    assert d.source_kind is None
    assert d.source_path is None


# --- First-run setup walkthrough tags (setup spec 2026-10-01 §7.2) ---


def test_setup_step_tags_are_valid_steps() -> None:
    from arm_common.enums import SetupStep

    valid = {s.value for s in SetupStep}
    for m in CONFIG_FIELD_META:
        if m.setup_step is not None:
            assert m.setup_step in valid, m.key
            assert m.setup_order is not None, m.key
            assert m.editable, m.key


def test_setup_step_tagging_matches_spec() -> None:
    def keys(step: str) -> list[str]:
        tagged = [m for m in CONFIG_FIELD_META if m.setup_step == step]
        return [m.key for m in sorted(tagged, key=lambda m: m.setup_order or 0)]

    assert keys("makemkv") == ["makemkv_key", "community_keydb_enabled", "makemkv_sdf_enabled"]
    assert keys("metadata") == [
        "tmdb_api_key",
        "omdb_api_key",
        "tvdb_api_key",
        "search_provider_movie",
        "thediscdb_enabled",
    ]
    assert keys("discs") == ["auto_rip_on_insert", "on_previously_ripped"]
    assert keys("transcoding") == ["transcode_enabled", "max_parallel_transcodes"]


def test_widgets_and_part_of() -> None:
    meta = {m.key: m for m in CONFIG_FIELD_META}
    assert meta["makemkv_key"].widget == "makemkv_key"
    assert meta["auto_rip_on_insert"].widget == "disc_handling"
    assert meta["hold_for_review"].part_of == "auto_rip_on_insert"
    for m in CONFIG_FIELD_META:
        if m.part_of is not None:
            assert m.part_of in meta, m.key


def test_signup_urls_on_metadata_keys() -> None:
    meta = {m.key: m for m in CONFIG_FIELD_META}
    assert meta["tmdb_api_key"].signup_url == "https://www.themoviedb.org/settings/api"
    assert meta["omdb_api_key"].signup_url == "https://www.omdbapi.com/apikey.aspx"
    assert meta["tvdb_api_key"].signup_url == "https://thetvdb.com/api-information"


def test_setup_step_order() -> None:
    from arm_common.enums import SETUP_STEP_ORDER

    assert [s.value for s in SETUP_STEP_ORDER] == [
        "account",
        "system",
        "drives",
        "makemkv",
        "metadata",
        "discs",
        "transcoding",
        "notifications",
        "finish",
    ]
