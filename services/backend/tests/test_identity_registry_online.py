"""Online-source order and enablement live in one place (spec §5.2)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.identity.sources import registry as reg_mod  # noqa: E402
from arm_backend.identity.sources.registry import (  # noqa: E402
    DEFAULT_ONLINE_SOURCES,
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
    assert DEFAULT_ONLINE_SOURCES == {"movie": ("tmdb", "omdb"), "tv": ("tmdb", "omdb"), "music": ("musicbrainz",)}
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
    monkeypatch.setitem(reg_mod.DEFAULT_ONLINE_SOURCES, "music", ("musicbrainz", "tmdb"))
    reg = _registry(
        FakeSource("musicbrainz", {"music"}, lookup_disc_id=_noop),
        FakeSource("tmdb", {"movie", "tv"}, search_title=_noop),
    )
    assert [s.id for s in sources_for(_cfg(), "music", reg)] == ["musicbrainz"]


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
    assert "search provider omdb is not available for movie; using tmdb" in caplog.text


def test_search_source_falls_back_for_a_provider_with_no_adapter_yet(caplog):
    """`search_provider_tv = tvmaze` is a valid setting before PR 2b adds the
    adapter: the job page falls back to the first usable ranked source."""
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}), FakeSource("omdb", {"movie", "tv"}))
    with caplog.at_level("INFO", logger="arm_backend.identity.sources.registry"):
        assert search_source(_cfg(search_provider_tv="tvmaze"), "tv", reg).id == "tmdb"
    assert "search provider tvmaze is not available for tv; using tmdb" in caplog.text


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
