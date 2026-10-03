"""Source protocol and capability tiers."""

from arm_common import Config

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability
from arm_backend.identity.sources.registry import (
    DEFAULT_RANKS,
    SOURCE_TIERS,
    disabled_source_ids,
    enabled_episode_source_ids,
    enabled_hint_sources,
    episode_auto_apply,
    episode_sources_setting,
    episode_tolerance,
    hint_sources_setting,
    source_ranks,
)


def test_tiers_follow_capabilities() -> None:
    assert SOURCE_TIERS["manual"] == TIER_BY_CAPABILITY[Capability.MANUAL]
    assert SOURCE_TIERS["thediscdb"] == TIER_BY_CAPABILITY[Capability.DISC_MAP]
    assert SOURCE_TIERS["bd_title"] == SOURCE_TIERS["label"] == TIER_BY_CAPABILITY[Capability.DISC_HINT]
    assert SOURCE_TIERS["preset"] == TIER_BY_CAPABILITY[Capability.PRESET]


def test_default_hint_ranks_prefer_bd_title() -> None:
    assert DEFAULT_RANKS["bd_title"] < DEFAULT_RANKS["label"]


def test_episode_sources_are_tier_three_and_ranked() -> None:
    from arm_backend.identity.sources.registry import DEFAULT_EPISODE_SOURCES, EPISODE_SOURCE_BY_SETTING

    ids = [EPISODE_SOURCE_BY_SETTING[s] for s in DEFAULT_EPISODE_SOURCES]
    assert ids == ["episodes_tmdb", "episodes_tvmaze", "episodes_tvdb"]
    assert all(SOURCE_TIERS[i] == TIER_BY_CAPABILITY[Capability.EPISODE_MATCH] for i in ids)
    assert [DEFAULT_RANKS[i] for i in ids] == [0, 1, 2]


def test_accessors_fall_back_on_none() -> None:
    for cfg in (None, _bare_config()):
        assert episode_sources_setting(cfg) == ("tmdb", "tvmaze", "tvdb")
        assert hint_sources_setting(cfg) == ("bd_title", "label")
        assert episode_tolerance(cfg) == 300
        assert episode_auto_apply(cfg) is True
        assert disabled_source_ids(cfg) == frozenset()


def _bare_config() -> Config:
    cfg = Config()
    cfg.episode_sources = None  # type: ignore[assignment]  # a legacy / partial row
    cfg.disc_hint_sources = None  # type: ignore[assignment]
    cfg.episode_match_tolerance_seconds = None  # type: ignore[assignment]
    cfg.episode_auto_apply = None  # type: ignore[assignment]
    return cfg


def test_accessors_follow_operator_order_and_drop_unknown_values() -> None:
    cfg = Config(episode_sources=["tvdb", "bogus", "tmdb"], disc_hint_sources=["label"])
    assert episode_sources_setting(cfg) == ("tvdb", "tmdb")
    assert enabled_episode_source_ids(cfg) == ("episodes_tvdb", "episodes_tmdb")
    assert [s.id for s in enabled_hint_sources(cfg)] == ["label"]
    assert disabled_source_ids(cfg) == frozenset({"episodes_tvmaze", "bd_title"})
    assert source_ranks(cfg) == {"episodes_tvdb": 0, "episodes_tmdb": 1, "label": 0}


def test_empty_lists_disable_everything() -> None:
    cfg = Config(episode_sources=[], disc_hint_sources=[])
    assert enabled_episode_source_ids(cfg) == ()
    assert enabled_hint_sources(cfg) == ()
    assert disabled_source_ids(cfg) == frozenset(
        {"episodes_tmdb", "episodes_tvmaze", "episodes_tvdb", "bd_title", "label"}
    )


def test_tolerance_and_auto_apply_read_the_config() -> None:
    cfg = Config(episode_match_tolerance_seconds=120, episode_auto_apply=False)
    assert episode_tolerance(cfg) == 120
    assert episode_auto_apply(cfg) is False


def test_source_ranks_none_matches_default_ranks() -> None:
    assert source_ranks(None) == DEFAULT_RANKS
