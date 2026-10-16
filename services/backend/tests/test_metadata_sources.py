"""Online-source adapters: one per HTTP client, keyed per call from Config."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
from arm_backend.metadata import sources as sources_mod  # noqa: E402
from arm_backend.metadata.base import MetadataResult  # noqa: E402
from arm_backend.metadata.sources import build_online_sources, capability  # noqa: E402
from arm_common import Config  # noqa: E402


def _config(**overrides) -> Config:
    base = {"id": 1, "tmdb_api_key": "tmdb-k", "omdb_api_key": "omdb-k", "musicbrainz_user_agent": "arm-test/0.0 (t@x)"}
    base.update(overrides)
    return Config(**base)


async def test_registry_has_the_six_sources_with_their_media_types():
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    assert set(reg) == {"tmdb", "omdb", "tvmaze", "tvdb", "musicbrainz", "arm_server"}
    assert reg["tmdb"].media_types == frozenset({"movie", "tv"})
    assert reg["omdb"].media_types == frozenset({"movie", "tv"})
    assert reg["tvmaze"].media_types == frozenset({"tv"})
    assert reg["tvdb"].media_types == frozenset({"tv"})
    assert reg["tvmaze"].requires_key is None
    assert reg["tvdb"].requires_key == "tvdb_api_key"
    assert reg["musicbrainz"].media_types == frozenset({"music"})
    assert reg["arm_server"].media_types == frozenset()
    for sid, source in reg.items():
        assert source.id == sid


@pytest.mark.parametrize("key", [None, "", "   "])
async def test_keyed_sources_report_missing_key(key):
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    cfg = _config(tmdb_api_key=key, omdb_api_key=key, tvdb_api_key=key)
    assert reg["tvdb"].configured(cfg) == "no tvdb key"
    assert reg["tmdb"].configured(cfg) == "no tmdb key"
    assert reg["omdb"].configured(cfg) == "no omdb key"
    assert reg["tmdb"].requires_key == "tmdb_api_key"
    assert reg["omdb"].requires_key == "omdb_api_key"


async def test_keyless_sources_are_always_configured():
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    cfg = _config(tmdb_api_key=None, omdb_api_key=None)
    assert reg["musicbrainz"].configured(cfg) is None
    assert reg["arm_server"].configured(cfg) is None
    assert reg["musicbrainz"].requires_key is None


def test_capability_returns_none_for_missing_methods():
    class Bare:
        id = "x"
        media_types = frozenset()
        requires_key = None

        def configured(self, cfg):
            return None

    assert capability(Bare(), "search_title") is None
    assert capability(Bare(), "configured") is not None


async def test_tmdb_adapter_delegates_by_kind(monkeypatch):
    calls: list[tuple] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def search_movie(self, title, year):
            calls.append(("movie", title, year))
            return MetadataResult(title="M", year=year, kind="movie")

        async def search_tv(self, title):
            calls.append(("tv", title))
            return MetadataResult(title="T", year=None, kind="tv")

        async def search_movie_candidates(self, title, year=None, limit=10):
            calls.append(("movie_cands", title, limit))
            return []

        async def search_tv_candidates(self, title, limit=10):
            calls.append(("tv_cands", title, limit))
            return []

        async def find_by_imdb_id(self, imdb_id):
            calls.append(("find", imdb_id))
            return MetadataResult(title="F", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as http:
        tmdb = build_online_sources(http)["tmdb"]
        cfg = _config()
        assert (await tmdb.search_title(cfg, "movie", "alien", 1979)).title == "M"
        assert (await tmdb.search_title(cfg, "tv", "lost", 2004)).title == "T"
        assert await tmdb.search_candidates(cfg, "movie", "alien", limit=3) == []
        assert await tmdb.search_candidates(cfg, "tv", "lost", limit=4) == []
        assert (await tmdb.lookup_imdb(cfg, "tt1")).title == "F"
    assert ("movie", "alien", 1979) in calls
    assert ("tv", "lost") in calls
    assert ("movie_cands", "alien", 3) in calls
    assert ("tv_cands", "lost", 4) in calls
    assert ("find", "tt1") in calls
    assert all(c[1] == "tmdb-k" for c in calls if c[0] == "init")


async def test_omdb_adapter_prefers_env_override_and_passes_kind(monkeypatch):
    calls: list[tuple] = []

    class FakeOMDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def lookup_by_title(self, title, year=None, kind="movie"):
            calls.append(("title", title, year, kind))

        async def search_candidates(self, title, kind="movie", limit=10):
            calls.append(("cands", title, kind, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="I", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as http:
        omdb = build_online_sources(http)["omdb"]
        cfg = _config(omdb_api_key="saved-k")
        assert await omdb.search_title(cfg, "tv", "lost", 2004) is None
        assert await omdb.search_candidates(cfg, "movie", "alien", limit=5) == []
        assert (await omdb.lookup_imdb(cfg, "tt2")).title == "I"
    assert ("title", "lost", 2004, "tv") in calls
    assert ("cands", "alien", "movie", 5) in calls
    assert ("imdb", "tt2") in calls
    assert all(c[1] == "saved-k" for c in calls if c[0] == "init")


async def test_musicbrainz_adapter_delegates(monkeypatch):
    calls: list[tuple] = []

    class FakeMB:
        def __init__(self, user_agent, http):
            calls.append(("init", user_agent))

        async def lookup_disc_id(self, disc_id, toc=None):
            calls.append(("disc", disc_id, toc))
            return MetadataResult(title="A", year=None, kind="music")

        async def search_releases(self, query, limit=10, **filters):
            calls.append(("search", query, filters))
            return []

    monkeypatch.setattr(sources_mod, "MusicBrainzClient", FakeMB)
    async with httpx.AsyncClient() as http:
        mb = build_online_sources(http)["musicbrainz"]
        assert (await mb.lookup_disc_id(_config(), "d1", "1 2 3 4 5")).title == "A"
        assert await mb.search_releases(_config(), "abbey road", artist="beatles") == []
    assert ("disc", "d1", "1 2 3 4 5") in calls
    assert calls[-1][1] == "abbey road" and calls[-1][2]["artist"] == "beatles"
    assert calls[0][1] == sources_mod.MUSICBRAINZ_USER_AGENT


async def test_arm_server_adapter_only_answers_crc64(monkeypatch):
    calls: list[str] = []

    class FakeArm:
        def __init__(self, http):
            pass

        async def lookup_by_crc64(self, crc64):
            calls.append(crc64)
            return MetadataResult(title="C", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "ArmServerClient", FakeArm)
    async with httpx.AsyncClient() as http:
        arm = build_online_sources(http)["arm_server"]
        assert await arm.lookup_fingerprint(_config(), "sha256", "zzz") is None
        assert (await arm.lookup_fingerprint(_config(), "crc64", "abc")).title == "C"
    assert calls == ["abc"]


async def test_tvmaze_adapter_is_tv_only_and_delegates(monkeypatch):
    calls: list[tuple] = []

    class FakeTVMaze:
        def __init__(self, http):
            pass

        async def search_show(self, title):
            calls.append(("show", title))
            return MetadataResult(title="Lost", year=2004, kind="tv")

        async def search_candidates(self, title, limit=10):
            calls.append(("cands", title, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="Lost", year=2004, kind="tv")

    monkeypatch.setattr(sources_mod, "TVMazeClient", FakeTVMaze)
    async with httpx.AsyncClient() as http:
        tvmaze = build_online_sources(http)["tvmaze"]
        cfg = _config()
        assert await tvmaze.search_title(cfg, "movie", "lost", None) is None
        assert await tvmaze.search_candidates(cfg, "movie", "lost") == []
        assert (await tvmaze.search_title(cfg, "tv", "lost", 2004)).title == "Lost"
        assert await tvmaze.search_candidates(cfg, "tv", "lost", limit=3) == []
        assert (await tvmaze.lookup_imdb(cfg, "tt0411008")).title == "Lost"
    assert calls == [("show", "lost"), ("cands", "lost", 3), ("imdb", "tt0411008")]


async def test_tvdb_adapter_is_tv_only_and_passes_the_key(monkeypatch):
    calls: list[tuple] = []

    class FakeTVDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def search_series(self, title):
            calls.append(("series", title))
            return MetadataResult(title="Lost", year=2004, kind="tv")

        async def search_candidates(self, title, limit=10):
            calls.append(("cands", title, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="Lost", year=2004, kind="tv")

    monkeypatch.setattr(sources_mod, "TVDBClient", FakeTVDB)
    async with httpx.AsyncClient() as http:
        tvdb = build_online_sources(http)["tvdb"]
        cfg = _config(tvdb_api_key="tvdb-k")
        assert await tvdb.search_title(cfg, "movie", "lost", None) is None
        assert await tvdb.search_candidates(cfg, "movie", "lost") == []
        assert (await tvdb.search_title(cfg, "tv", "lost", 2004)).title == "Lost"
        assert await tvdb.search_candidates(cfg, "tv", "lost", limit=2) == []
        assert (await tvdb.lookup_imdb(cfg, "tt0411008")).title == "Lost"
    assert ("series", "lost") in calls and ("cands", "lost", 2) in calls and ("imdb", "tt0411008") in calls
    assert all(c[1] == "tvdb-k" for c in calls if c[0] == "init")
