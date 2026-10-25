"""Online-source order and enablement live in one place (spec §5.2)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.identity.sources import registry as reg_mod  # noqa: E402
from arm_backend.identity.sources.registry import (  # noqa: E402
    fingerprint_sources,
    known_source_ids,
    lookup_sources,
    online_source_ids,
    search_source,
    sources_for,
)
from arm_common import Config  # noqa: E402


class FakeSource:
    def __init__(self, id: str, media_types: set[str], reason: str | None = None, **caps):
        self.id = id
        self.media_types = frozenset(media_types)
        self.requires_key = None
        self._reason = reason
        for name, fn in caps.items():
            setattr(self, name, fn)

    def configured(self, cfg):
        return self._reason


async def _noop(*a, **k):
    return None


def _registry(*sources: FakeSource) -> dict[str, FakeSource]:
    return {s.id: s for s in sources}


def _cfg(**kw) -> Config:
    return Config(id=1, **kw)


def test_default_order_matches_today():
    assert reg_mod.DEFAULT_MOVIE_SOURCES == ("tmdb", "omdb")
    assert reg_mod.DEFAULT_MUSIC_SOURCES == ("musicbrainz",)
    assert online_source_ids(_cfg(), "movie") == ("tmdb", "omdb")
    assert online_source_ids(None, "music") == ("musicbrainz",)
    assert online_source_ids(_cfg(), "data") == ()


def test_sources_for_keeps_order_and_drops_unconfigured():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}, reason="no tmdb key", search_title=_noop),
        FakeSource("omdb", {"movie", "tv"}, search_title=_noop),
    )
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["omdb"]
    reg["tmdb"]._reason = None
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["tmdb", "omdb"]


def test_sources_for_skips_ids_missing_from_registry():
    reg = _registry(FakeSource("omdb", {"movie", "tv"}, search_title=_noop))
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["omdb"]


def test_sources_for_requires_media_type_membership(monkeypatch):
    """A listed id whose adapter does not serve the media type is dropped.
    `_MUSIC_KNOWN` is widened because the column validator would otherwise
    refuse to put tmdb on the music list at all."""
    monkeypatch.setitem(reg_mod._MUSIC_KNOWN, "tmdb", "tmdb")
    reg = _registry(
        FakeSource("musicbrainz", {"music"}, lookup_disc_id=_noop),
        FakeSource("tmdb", {"movie", "tv"}, search_title=_noop),
    )
    cfg = _cfg(music_sources=["musicbrainz", "tmdb"])
    assert online_source_ids(cfg, "music") == ("musicbrainz", "tmdb")
    assert [s.id for s in sources_for(cfg, "music", reg)] == ["musicbrainz"]


def test_search_source_is_first_configured_of_the_list():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}, reason="no tmdb key"),
        FakeSource("omdb", {"movie", "tv"}),
    )
    assert search_source(_cfg(), "movie", reg).id == "omdb"
    reg["omdb"]._reason = "no omdb key"
    assert search_source(_cfg(), "movie", reg) is None


def test_fingerprint_sources_default_to_arm_server():
    reg = _registry(FakeSource("arm_server", set(), lookup_fingerprint=_noop))
    assert [s.id for s in fingerprint_sources(_cfg(), reg)] == ["arm_server"]
    assert fingerprint_sources(_cfg(), {}) == ()


def test_known_source_ids_reads_media_types_from_the_registry():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("musicbrainz", {"music"}),
        FakeSource("arm_server", set()),
    )
    assert known_source_ids("movie", reg) == ("tmdb", "omdb")
    assert known_source_ids("music", reg) == ("musicbrainz",)
    assert known_source_ids("data", reg) == ()


def test_search_source_reads_the_search_provider_setting(caplog):
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("musicbrainz", {"music"}),
    )
    assert search_source(_cfg(search_provider_movie="omdb"), "movie", reg).id == "omdb"
    assert search_source(_cfg(search_provider_tv="tmdb"), "tv", reg).id == "tmdb"
    assert search_source(_cfg(), "music", reg).id == "musicbrainz"
    reg["omdb"]._reason = "no omdb key"
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_movie="omdb"), "movie", reg).id == "tmdb"
    assert "search provider omdb unusable (no omdb key); using tmdb for movie" in caplog.text


def test_search_source_falls_back_for_an_unknown_id(caplog):
    """A row may hold an unknown id the registry does not know (a downgrade, a hand
    edit); the box falls back to the first usable ranked source."""
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}))
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_tv="bogus"), "tv", reg).id == "tmdb"
    assert "search provider bogus unusable (no adapter named bogus); using tmdb for tv" in caplog.text


def test_settings_readers_default_for_legacy_rows():
    from arm_backend.identity.sources.registry import (
        crc64service_enabled,
        movie_auto_apply,
        movie_sources_setting,
        music_auto_apply,
        music_sources_setting,
        search_provider_setting,
    )

    assert movie_sources_setting(None) == ("tmdb", "omdb")
    assert music_sources_setting(None) == ("musicbrainz",)
    assert search_provider_setting(None, "movie") == "tmdb"
    assert search_provider_setting(None, "tv") == "tmdb"
    assert search_provider_setting(None, "music") == "musicbrainz"
    assert search_provider_setting(None, "data") == ""
    assert movie_auto_apply(None) is True
    assert music_auto_apply(None) is True
    assert crc64service_enabled(None) is True
    cfg = _cfg(
        movie_sources=["omdb", "bogus", "omdb"], music_sources=[], movie_auto_apply=False, crc64service_enabled=False
    )
    assert movie_sources_setting(cfg) == ("omdb",)
    assert music_sources_setting(cfg) == ()
    assert movie_auto_apply(cfg) is False
    assert crc64service_enabled(cfg) is False


def test_lookup_sources_puts_preferred_first():
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}))
    assert [s.id for s in lookup_sources(_cfg(search_provider_movie="omdb"), "movie", reg)] == ["omdb", "tmdb"]
    assert [s.id for s in lookup_sources(_cfg(), "movie", reg)] == ["tmdb", "omdb"]
    reg["omdb"]._reason = "no omdb key"
    assert [s.id for s in lookup_sources(_cfg(search_provider_movie="omdb"), "movie", reg)] == ["tmdb"]


def test_online_source_ids_reads_the_movie_and_music_lists():
    assert online_source_ids(_cfg(movie_sources=["omdb", "tmdb"]), "movie") == ("omdb", "tmdb")
    assert online_source_ids(_cfg(movie_sources=[]), "movie") == ()
    assert online_source_ids(_cfg(music_sources=[]), "music") == ()
    assert online_source_ids(_cfg(episode_sources=["tvmaze", "tmdb"]), "tv") == ("tvmaze", "tmdb")
    assert online_source_ids(_cfg(episode_sources=[]), "tv") == ()
    assert online_source_ids(None, "tv") == ("tmdb", "tvmaze", "tvdb")


def test_sources_for_tv_skips_ids_without_an_adapter():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}, search_title=_noop), FakeSource("omdb", {"movie", "tv"}, search_title=_noop)
    )
    assert [s.id for s in sources_for(_cfg(episode_sources=["tvmaze", "tvdb", "tmdb"]), "tv", reg)] == ["tmdb"]
    assert sources_for(_cfg(episode_sources=["tvmaze"]), "tv", reg) == ()


def test_fingerprint_sources_honours_the_switch():
    from arm_backend.identity.sources.registry import fingerprint_sources

    reg = _registry(FakeSource("arm_server", {"movie"}))
    assert [s.id for s in fingerprint_sources(_cfg(), reg)] == ["arm_server"]
    assert fingerprint_sources(_cfg(crc64service_enabled=False), reg) == ()


def test_online_source_values_match_the_field_metadata():
    from arm_backend.identity.sources.registry import ONLINE_SOURCE_VALUES
    from arm_common.config_metadata import CONFIG_FIELD_META

    meta = {m.key: m for m in CONFIG_FIELD_META}
    assert tuple(meta["movie_sources"].enum_values) == ONLINE_SOURCE_VALUES["movie"]
    assert tuple(meta["search_provider_movie"].enum_values) == ONLINE_SOURCE_VALUES["movie"]
    assert tuple(meta["search_provider_tv"].enum_values) == ONLINE_SOURCE_VALUES["tv"]
    assert tuple(meta["music_sources"].enum_values) == ONLINE_SOURCE_VALUES["music"]
    assert tuple(meta["search_provider_music"].enum_values) == ONLINE_SOURCE_VALUES["music"]


def test_auto_apply_for_maps_each_kind_to_its_switch() -> None:
    from arm_backend.identity.sources.registry import auto_apply_for

    cfg = Config(id=1, movie_auto_apply=False, episode_auto_apply=True, music_auto_apply=False)
    assert auto_apply_for(cfg, "movie") is False
    assert auto_apply_for(cfg, "tv") is True
    assert auto_apply_for(cfg, "music") is False
    cfg.episode_auto_apply = False
    assert auto_apply_for(cfg, "tv") is False
    # Unknown kinds and a missing row apply (identify never holds what it cannot name).
    assert auto_apply_for(cfg, "weird") is True
    assert auto_apply_for(None, "movie") is True


def test_search_provider_need_not_be_on_the_ranked_list():
    """D-7 keeps OMDb off the automatic TV order (`episode_sources`) while
    `search_provider_tv` still offers it, so the box's provider is honoured
    whenever its adapter serves the type and has its key -- looking it up in
    the ranked list only meant the choice could never take effect."""
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("tvmaze", {"tv"}),
    )
    assert "omdb" not in online_source_ids(_cfg(), "tv")
    assert search_source(_cfg(search_provider_tv="omdb"), "tv", reg).id == "omdb"
    # ...and with no TMDb key either, so the ranked list cannot supply it.
    cfg = _cfg(search_provider_tv="omdb", episode_sources=["tvmaze"])
    assert search_source(cfg, "tv", reg).id == "omdb"
    # The exact-id lookup walk follows the same choice.
    assert [s.id for s in lookup_sources(cfg, "tv", reg)] == ["omdb", "tvmaze"]


def test_search_provider_survives_an_emptied_ranked_list(caplog):
    """Clearing a type's ranked list stops the AUTOMATIC lookups; the job
    page's search box is a separate, explicit operator action and keeps
    working (and logs nothing, since nothing fell back)."""
    reg = _registry(FakeSource("musicbrainz", {"music"}, search_releases=_noop))
    cfg = _cfg(music_sources=[])
    assert sources_for(cfg, "music", reg) == ()
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(cfg, "music", reg).id == "musicbrainz"
    assert "unusable" not in caplog.text


def test_search_provider_that_cannot_serve_the_type_falls_back(caplog):
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("musicbrainz", {"music"}))
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_movie="musicbrainz"), "movie", reg).id == "tmdb"
    assert "musicbrainz does not search movie" in caplog.text


def test_search_source_uses_a_provider_outside_the_ranked_list():
    """The Search card is independent of Online lookup: OMDb is never in
    `episode_sources`, and an unticked movie source can still serve the box."""
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}))
    cfg = _cfg(search_provider_tv="omdb", episode_sources=["tmdb", "tvmaze", "tvdb"])
    assert search_source(cfg, "tv", reg).id == "omdb"
    cfg = _cfg(search_provider_movie="omdb", movie_sources=["tmdb"])
    assert search_source(cfg, "movie", reg).id == "omdb"
    # the identify walk still ignores it
    assert [s.id for s in sources_for(cfg, "movie", reg)] == ["tmdb"]
    # and an exact-id lookup asks it first, ahead of the ranked list
    assert [s.id for s in lookup_sources(cfg, "movie", reg)] == ["omdb", "tmdb"]


def test_search_source_unconfigured_outside_provider_falls_back(caplog):
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}, reason="no omdb key"))
    cfg = _cfg(search_provider_movie="omdb", movie_sources=["tmdb"])
    with caplog.at_level("DEBUG", logger="arm_backend.identity.sources.registry"):
        assert search_source(cfg, "movie", reg).id == "tmdb"
    assert "search provider omdb unusable (no omdb key); using tmdb for movie" in caplog.text


def test_search_source_provider_not_serving_the_type_falls_back():
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie"}))
    assert search_source(_cfg(search_provider_tv="omdb"), "tv", reg).id == "tmdb"
