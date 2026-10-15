"""Online-source order and enablement live in one place (spec §5.2)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.identity.sources import registry as reg_mod  # noqa: E402
from arm_backend.identity.sources.registry import (  # noqa: E402
    DEFAULT_ONLINE_SOURCES,
    fingerprint_sources,
    known_source_ids,
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


def test_search_source_honours_legacy_metadata_provider():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("musicbrainz", {"music"}),
    )
    assert search_source(_cfg(metadata_provider="omdb"), "movie", reg).id == "omdb"
    reg["omdb"]._reason = "no omdb key"
    assert search_source(_cfg(metadata_provider="omdb"), "movie", reg).id == "tmdb"
    reg["omdb"]._reason = None
    assert search_source(_cfg(metadata_provider="omdb"), "music", reg).id == "musicbrainz"
    assert search_source(_cfg(metadata_provider="bogus"), "movie", reg).id == "tmdb"
