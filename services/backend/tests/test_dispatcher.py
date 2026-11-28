"""Dispatcher routing rules — uses respx to mock all three providers."""

import httpx
import pytest
import respx

from arm_backend.metadata.dispatcher import MetadataDispatcher
from arm_common import Config, DiscType
from arm_common.schemas import ScanResult


async def _identify(dispatcher: MetadataDispatcher, *args, **kwargs):
    """The hit `identify` found (None for a shortlist or a miss)."""
    return (await dispatcher.identify(*args, **kwargs)).result


def _config(**overrides) -> Config:
    base = dict(
        id=1,
        tmdb_api_key="tmdb-k",
        omdb_api_key="omdb-k",
        musicbrainz_user_agent="arm-test/0.0 (t@example.com)",
    )
    base.update(overrides)
    return Config(**base)


@respx.mock
async def test_dispatcher_all_miss_returns_none():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "no"})
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="NOPE")
        result = await _identify(dispatcher, scan, _config(episode_sources=["tmdb"]))
    assert result is None


async def test_dispatcher_data_short_circuits():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DATA, volume_label="WHATEVER")
        result = await _identify(dispatcher, scan, _config())
    assert result is None


async def test_dispatcher_unknown_short_circuits():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.UNKNOWN)
        result = await _identify(dispatcher, scan, _config())
    assert result is None


@respx.mock
async def test_dispatcher_cd_uses_only_musicbrainz():
    respx.get("https://musicbrainz.org/ws/2/discid/some-disc").mock(
        return_value=httpx.Response(200, json={"releases": [{"title": "Album", "date": "1990-05-01"}]})
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="some-disc")
        result = await _identify(dispatcher, scan, _config())
    assert result is not None
    assert result.kind == "music"


async def test_dispatcher_cd_without_disc_id_misses():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.CD)
        result = await _identify(dispatcher, scan, _config())
    assert result is None


async def test_identify_from_imdb_walks_the_ranked_sources():
    """The exact-id lookup asks the enabled sources for the kind in rank
    order; an unconfigured source is skipped and the hit carries its source id."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str, reason: str | None, hit: MetadataResult | None):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return reason

            async def lookup_imdb(self, cfg, imdb_id):
                calls.append(f"{sid}:{imdb_id}")
                return hit

        return S()

    reg = {
        "tmdb": _source("tmdb", "no tmdb key", MetadataResult(title="T", year=None, kind="movie")),
        "omdb": _source("omdb", None, MetadataResult(title="Round Midnight", year=1986, kind="movie")),
    }
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        hit = await dispatcher.identify_from_imdb("tt0090557", _config(movie_sources=["tmdb", "omdb"]))
        assert hit is not None and hit.title == "Round Midnight" and hit.provider == "omdb"
        assert hit.payload["imdb_id"] == "tt0090557"
        assert calls == ["omdb:tt0090557"]
        assert await dispatcher.identify_from_imdb("", _config()) is None
        assert await dispatcher.identify_from_imdb("tt1", _config(movie_sources=[])) is None
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb", "omdb"]), "movie") is True
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb"]), "movie") is False  # tmdb unkeyed
        assert dispatcher.has_imdb_lookup(_config(movie_sources=[]), "movie") is False


async def test_identify_from_imdb_falls_through_a_miss_to_the_next_source():
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str, hit: MetadataResult | None):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return None

            async def lookup_imdb(self, cfg, imdb_id):
                calls.append(f"{sid}:{imdb_id}")
                return hit

        return S()

    reg = {"tmdb": _source("tmdb", None), "omdb": _source("omdb", MetadataResult(title="T", year=None, kind="movie"))}
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        hit = await dispatcher.identify_from_imdb("tt1", _config(movie_sources=["tmdb", "omdb"]))
    assert hit is not None and hit.provider == "omdb"
    # The trailing tmdb call is fill_external_ids asking TMDb for the omdb hit's TMDb id.
    assert calls == ["tmdb:tt1", "omdb:tt1", "tmdb:tt1"]


async def test_identify_from_imdb_uses_the_kind_list():
    from arm_backend.metadata.base import MetadataResult

    kinds: list[str] = []

    class Omdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_imdb(self, cfg, imdb_id):
            kinds.append("called")
            return MetadataResult(title="Lost", year=2004, kind="tv")

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": Omdb()})
        cfg = _config(movie_sources=[], episode_sources=["tmdb", "tvmaze"])
        # OMDb is not in the TV list: no TV source offers the lookup.
        assert await dispatcher.identify_from_imdb("tt0411008", cfg, kind="tv") is None
        assert dispatcher.has_imdb_lookup(cfg, "tv") is False
        assert kinds == []
        cfg = _config(movie_sources=["omdb"], episode_sources=[])
        hit = await dispatcher.identify_from_imdb("tt0411008", cfg, kind="movie")
        assert hit is not None and hit.kind == "tv" and kinds == ["called"]


@respx.mock
async def test_omdb_skipped_when_config_key_empty():
    """When cfg.omdb_api_key is None the OMDb branch is skipped entirely."""
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    # OMDb must NOT be called — any unexpected call will raise via respx strict mode.
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Should Not Appear", "Year": "1999"},
        )
    )

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE")
        result = await _identify(dispatcher, scan, _config(omdb_api_key=None, episode_sources=["tmdb"]))
    assert result is None
    assert omdb_route.call_count == 0


@pytest.mark.asyncio
async def test_call_stamps_the_source_id_as_provider() -> None:
    """_call is the one place that knows which source produced a hit; it
    stamps MetadataResult.provider with the source id so identity and
    provider_raw key on it, overwriting anything the client set."""
    from arm_backend.metadata.base import MetadataResult

    dispatcher = MetadataDispatcher(httpx.AsyncClient())

    async def _hit() -> MetadataResult:
        return MetadataResult(title="X", year=None, kind="movie", payload={}, provider="spoofed")

    for sid in ("tmdb", "omdb", "arm_server", "musicbrainz"):
        result = await dispatcher._call(sid, _hit())
        assert result is not None and result.provider == sid, sid

    async def _miss() -> None:
        return None

    assert await dispatcher._call("tmdb", _miss()) is None
    await dispatcher.aclose()


@respx.mock
async def test_identify_from_imdb_keeps_the_known_imdb_and_adds_tvdb():
    respx.get("https://api.themoviedb.org/3/find/tt0071003").mock(
        return_value=httpx.Response(
            200,
            json={
                "movie_results": [],
                "tv_results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}],
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    async with httpx.AsyncClient() as client:
        hit = await MetadataDispatcher(client).identify_from_imdb("tt0071003", _config())
    assert hit is not None and hit.kind == "tv"
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")


async def test_fill_external_ids_skips_non_tmdb_keyless_and_idless_hits():
    from arm_backend.metadata.base import MetadataResult

    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client)
        omdb = MetadataResult(provider="omdb", kind="movie", title="X", year=1999, payload={"imdbID": "tt1"})
        assert await d.fill_external_ids(None, _config()) is None
        assert await d.fill_external_ids(omdb, _config()) is omdb
        tmdb_hit = MetadataResult(provider="tmdb", kind="movie", title="X", year=1999, payload={"id": 1})
        assert await d.fill_external_ids(tmdb_hit, _config(tmdb_api_key=None)) is tmdb_hit
        assert "imdb_id" not in tmdb_hit.payload
        idless = MetadataResult(provider="tmdb", kind="movie", title="X", year=1999, payload={})
        assert await d.fill_external_ids(idless, _config()) is idless
        assert idless.payload == {}


async def test_fill_external_ids_timeout_keeps_the_hit(monkeypatch):
    """A slow `external_ids` call is bounded by PROVIDER_TIMEOUT_SECONDS; on
    timeout the hit is returned unchanged."""
    import asyncio

    from arm_backend.metadata import dispatcher as dispatcher_mod
    from arm_backend.metadata.base import MetadataResult
    from arm_backend.metadata.tmdb import TMDBClient

    async def slow(self, tmdb_id, kind):
        await asyncio.sleep(10)
        return {"imdb_id": "tt9"}

    monkeypatch.setattr(TMDBClient, "get_external_id_map", slow)
    monkeypatch.setattr(dispatcher_mod, "PROVIDER_TIMEOUT_SECONDS", 0.01)
    async with httpx.AsyncClient() as client:
        hit = MetadataResult(provider="tmdb", kind="tv", title="X", year=1999, payload={"id": 1})
        assert await MetadataDispatcher(client).fill_external_ids(hit, _config()) is hit
    assert hit.payload == {"id": 1}


async def test_dispatcher_accepts_an_injected_registry():
    from arm_backend.metadata.base import MetadataResult

    class OnlyOmdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "omdb_api_key"

        def configured(self, cfg):
            return None

        async def search_candidates(self, cfg, kind, title, limit=10, *, enrich=True):
            return [MetadataResult(title="Blade Runner", year=1982, kind=kind, payload={"imdbID": "tt0083658"})]

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": OnlyOmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="BLADE_RUNNER_1982")
        found = await dispatcher.identify(scan, _config(tmdb_api_key=None, omdb_api_key=None))
    # A label alone is thin evidence: the injected source's only candidate is offered, not applied.
    assert found.result is None and found.match is not None
    assert found.match.decision == "shortlist"
    assert [(c.title, c.provider) for c in found.match.candidates] == [("Blade Runner", "omdb")]
    assert dispatcher.sources["omdb"].id == "omdb"


def _recording_source(sid, calls, media_types=frozenset({"movie", "tv"})):

    class Fake:
        id = sid
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_candidates(self, cfg, kind, title, limit=10, *, enrich=True):
            calls.append(f"{sid}:{kind}")
            return []

    Fake.media_types = media_types
    return Fake()


async def test_crc64_lookup_skipped_when_the_switch_is_off():
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class FakeArmServer:
        id = "arm_server"
        media_types = frozenset({"movie"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_fingerprint(self, cfg, algo, value):
            calls.append(value)
            return MetadataResult(title="Iron Man", year=2008, kind="movie")

    reg = {"arm_server": FakeArmServer(), "tmdb": _recording_source("tmdb", [])}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="X", fingerprints=[{"algo": "crc64", "value": "abc"}])
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        await _identify(dispatcher, scan, _config(crc64service_enabled=False))
        assert calls == []
        hit = await _identify(dispatcher, scan, _config())
    assert calls == ["abc"] and hit is not None and hit.title == "Iron Man"


async def test_fill_external_ids_adds_the_tmdb_id_to_a_tvmaze_hit():
    """A non-TMDb hit with an IMDb id gets its TMDb id from TMDb /find
    when TMDb is configured, so the episode stage can use every provider."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "tmdb_api_key"

        def configured(self, cfg):
            return None if cfg.tmdb_api_key else "no tmdb key"

        async def lookup_imdb(self, cfg, imdb_id):
            calls.append(imdb_id)
            return MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 4607}, provider="tmdb")

    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        hit = MetadataResult(
            title="Lost", year=2004, kind="tv", payload={"id": 1, "imdb_id": "tt0411008"}, provider="tvmaze"
        )
        out = await d.fill_external_ids(hit, _config())
        assert out is hit and out.payload["tmdb_id"] == "4607"
        assert calls == ["tt0411008"]
        # Ids already present win; no second call for a hit that has tmdb_id.
        await d.fill_external_ids(hit, _config())
        assert calls == ["tt0411008"]
        # Unconfigured TMDb: nothing happens.
        other = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdb_id": "tt1"}, provider="tvmaze")
        assert (await d.fill_external_ids(other, _config(tmdb_api_key=None))).payload == {"imdb_id": "tt1"}
        assert calls == ["tt0411008"]


async def test_fill_external_ids_ignores_a_kind_mismatch_and_failures():
    from arm_backend.metadata.base import LookupError, MetadataResult

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "tmdb_api_key"
        mode = "mismatch"

        def configured(self, cfg):
            return None

        async def lookup_imdb(self, cfg, imdb_id):
            if self.mode == "mismatch":
                return MetadataResult(title="Lost (film)", year=1990, kind="movie", payload={"id": 99}, provider="tmdb")
            raise LookupError("down")

    tmdb = Tmdb()
    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client, sources={"tmdb": tmdb})
        hit = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdb_id": "tt0411008"}, provider="tvdb")
        assert "tmdb_id" not in (await d.fill_external_ids(hit, _config())).payload
        tmdb.mode = "raise"
        assert "tmdb_id" not in (await d.fill_external_ids(hit, _config())).payload
        assert await d.fill_external_ids(None, _config()) is None


# --- Miss reasons: the attempts each identify call records -----------------


def _attempt_source(sid, behaviour, media_types=frozenset({"movie", "tv"}), *, configured=None):
    """A fake source whose search/lookup does `behaviour`: "hit", "miss",
    "timeout" (raises TimeoutError) or "error" (raises LookupError)."""
    import asyncio

    from arm_backend.metadata.base import LookupError as MetaLookupError
    from arm_backend.metadata.base import MetadataResult

    async def _act(kind, title):
        if behaviour == "hit":
            return MetadataResult(title=title, year=None, kind=kind)
        if behaviour == "timeout":
            raise asyncio.TimeoutError
        if behaviour == "error":
            raise MetaLookupError("boom")
        return None

    class Fake:
        id = sid
        requires_key = None

        def configured(self, cfg):
            return configured

        async def search_candidates(self, cfg, kind, title, limit=10, *, enrich=True):
            found = await _act(kind, title)
            return [] if found is None else [found]

        async def lookup_imdb(self, cfg, imdb_id):
            return await _act("movie", imdb_id)

    Fake.media_types = media_types
    return Fake()


async def test_attempts_reset_on_each_call():
    reg = {"tmdb": _attempt_source("tmdb", "miss")}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT")
    cfg = _config(movie_sources=["tmdb"], episode_sources=["tmdb"])
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        await _identify(dispatcher, scan, cfg)
        first = len(dispatcher.last_attempts)
        await _identify(dispatcher, scan, cfg)
        assert len(dispatcher.last_attempts) == first
        await dispatcher.identify_from_imdb("tt0113277", cfg)
    assert dispatcher.last_attempts == [
        {"source": "tmdb", "step": "imdb", "kind": "movie", "outcome": "miss", "detail": "tt0113277"}
    ]


async def test_listed_sources_without_a_key_record_not_configured():
    reg = {
        "tmdb": _attempt_source("tmdb", "hit", configured="no tmdb key"),
        "omdb": _attempt_source("omdb", "hit", configured="no omdb key"),
    }
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        cfg = _config(movie_sources=["tmdb", "omdb"], episode_sources=["tmdb"])
        assert await _identify(dispatcher, scan, cfg) is None
    assert dispatcher.last_attempts
    assert all(a["outcome"] == "not_configured" for a in dispatcher.last_attempts)
    assert {(a["source"], a["kind"]) for a in dispatcher.last_attempts} == {
        ("tmdb", "movie"),
        ("omdb", "movie"),
        ("tmdb", "tv"),
    }


async def test_cd_attempts_record_the_disc_id_step():
    from arm_backend.metadata.base import MetadataResult

    class Mb:
        id = "musicbrainz"
        media_types = frozenset({"music"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_disc_id(self, cfg, disc_id, toc=None):
            return MetadataResult(title="Album", year=None, kind="music")

    scan = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="abc")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"musicbrainz": Mb()})
        assert await _identify(dispatcher, scan, _config()) is not None
    assert dispatcher.last_attempts == [
        {"source": "musicbrainz", "step": "disc_id", "kind": "music", "outcome": "hit", "detail": "abc"}
    ]


async def test_cd_passes_toc_and_records_a_fuzzy_match():
    from arm_backend.metadata.base import MetadataResult

    seen = []

    class Mb:
        id = "musicbrainz"
        media_types = frozenset({"music"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_disc_id(self, cfg, disc_id, toc=None):
            seen.append(toc)
            return MetadataResult(title="Album", year=None, kind="music", payload={"toc_match": "fuzzy"})

    scan = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="abc", cd_toc="1 2 3 4 5")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"musicbrainz": Mb()})
        assert await _identify(dispatcher, scan, _config()) is not None
    assert seen == ["1 2 3 4 5"]
    assert dispatcher.last_attempts == [
        {
            "source": "musicbrainz",
            "step": "disc_id",
            "kind": "music",
            "outcome": "hit",
            "detail": "matched by track layout",
        }
    ]


async def test_cd_fuzzy_toc_miss_records_a_miss_with_a_reason():
    from arm_backend.metadata.base import LookupError

    class Mb:
        id = "musicbrainz"
        media_types = frozenset({"music"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_disc_id(self, cfg, disc_id, toc=None):
            raise LookupError("musicbrainz toc not found")

    scan = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="abc", cd_toc="1 2 3 4 5")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"musicbrainz": Mb()})
        await _identify(dispatcher, scan, _config())
    assert dispatcher.last_attempts[0] == {
        "source": "musicbrainz",
        "step": "disc_id",
        "kind": "music",
        "outcome": "miss",
        "detail": "no release fits the track layout",
    }


async def test_overlapping_identifies_keep_their_own_attempts():
    """The dispatcher is shared by the app: two discs identified at once must
    not see each other's attempts (or suppress each other's skip entries)."""
    import asyncio

    class Interleaving:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            await asyncio.sleep(0)
            return None

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"tmdb": Interleaving()})
        cfg = _config(movie_sources=["tmdb"], episode_sources=[])

        async def run(label: str) -> list[dict]:
            await _identify(dispatcher, ScanResult(disc_type=DiscType.DVD, volume_label=label), cfg)
            return dispatcher.last_attempts

        a, b = await asyncio.gather(run("ALPHA"), run("BRAVO"))
    assert a and {x["detail"] for x in a} == {"ALPHA"}
    assert b and {x["detail"] for x in b} == {"BRAVO"}
    # Each call records its own no_sources entry for the empty TV list.
    assert sum(1 for x in a if x["outcome"] == "no_sources") == 1
    assert sum(1 for x in b if x["outcome"] == "no_sources") == 1


async def test_the_movie_sources_setting_decides_which_sources_are_searched():
    calls: list[str] = []
    reg = {"tmdb": _recording_source("tmdb", calls), "omdb": _recording_source("omdb", calls)}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        await _identify(dispatcher, scan, _config(movie_sources=["omdb", "tmdb"]))
        assert {c for c in calls if c.endswith(":movie")} == {"omdb:movie", "tmdb:movie"}
        calls.clear()
        await _identify(MetadataDispatcher(client, sources=reg), scan, _config(movie_sources=[]))
    assert [c for c in calls if c.endswith(":movie")] == []
    assert set(calls) == {"tmdb:tv"}


async def test_the_episode_sources_setting_decides_which_sources_search_tv():
    """The TV search reads the operator's episode list; ids with no adapter in the registry are skipped and OMDb
    is not in the list."""
    calls: list[str] = []
    reg = {"tmdb": _recording_source("tmdb", calls), "omdb": _recording_source("omdb", calls)}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        cfg = _config(movie_sources=[], episode_sources=["tvmaze", "tmdb", "tvdb"])
        assert await _identify(dispatcher, scan, cfg) is None
        assert calls == ["tmdb:tv"]
        calls.clear()
        cfg = _config(movie_sources=["omdb"], episode_sources=["tvmaze"])
        assert await _identify(dispatcher, scan, cfg) is None
    assert calls == ["omdb:movie"]


async def test_attempts_record_hit_and_miss_with_the_searched_title():
    reg = {"tmdb": _attempt_source("tmdb", "miss"), "omdb": _attempt_source("omdb", "hit")}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        found = await dispatcher.identify(scan, _config(movie_sources=["tmdb", "omdb"], episode_sources=[]))
    assert found.match is not None and found.match.decision == "shortlist"
    attempts = dispatcher.last_attempts
    assert {"source": "tmdb", "step": "title", "kind": "movie", "outcome": "miss", "detail": "HEAT"} in attempts
    assert {"source": "omdb", "step": "title", "kind": "movie", "outcome": "hit", "detail": "HEAT"} in attempts


async def test_attempts_record_timeout_and_error():
    reg = {"tmdb": _attempt_source("tmdb", "timeout"), "omdb": _attempt_source("omdb", "error")}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        assert await _identify(dispatcher, scan, _config(movie_sources=["tmdb", "omdb"], episode_sources=[])) is None
    outcomes = [(a["source"], a["kind"], a["outcome"]) for a in dispatcher.last_attempts]
    assert ("tmdb", "movie", "timeout") in outcomes
    assert ("omdb", "movie", "error") in outcomes


async def test_an_empty_tv_search_records_no_sources():
    reg = {"tmdb": _attempt_source("tmdb", "miss")}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        cfg = _config(movie_sources=["tmdb"], episode_sources=[])
        assert await _identify(dispatcher, scan, cfg) is None
    assert {"source": None, "step": "title", "kind": "tv", "outcome": "no_sources", "detail": "SHOW"} in (
        dispatcher.last_attempts
    )
    # Recorded once per kind, however many queries were searched.
    assert sum(1 for a in dispatcher.last_attempts if a["outcome"] == "no_sources") == 1


def _detail_source(sid: str, reason: str | None, hit, calls: list[str]):
    class S:
        id = sid
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return reason

        async def details(self, cfg, kind, provider_id):
            calls.append(f"{sid}:{kind}:{provider_id}")
            return hit

    return S()


async def test_refetch_asks_the_best_provider_by_the_id_its_details_take():
    from arm_backend.metadata.base import MetadataResult
    from arm_common.schemas import SuggestionCandidate

    calls: list[str] = []
    recall = MetadataResult(title="Total Recall", year=1990, kind="movie", payload={"id": 861})
    reg = {"tmdb": _detail_source("tmdb", None, recall, calls), "omdb": _detail_source("omdb", None, recall, calls)}
    row = SuggestionCandidate(
        title="Total Recall",
        year=1990,
        kind="movie",
        provider="tmdb",
        providers=["omdb", "tmdb"],
        ids={"tmdb": "861", "imdb": "tt0100802"},
        score=71.0,
    )
    async with httpx.AsyncClient() as client:
        hit = await MetadataDispatcher(client, sources=reg).refetch(row, _config())
    assert hit is not None and hit.provider == "tmdb" and hit.title == "Total Recall"
    assert calls == ["tmdb:movie:861"]


async def test_refetch_falls_through_an_unreachable_provider_to_the_next_that_returned_it():
    from arm_backend.metadata.base import MetadataResult
    from arm_common.schemas import SuggestionCandidate

    calls: list[str] = []
    recall = MetadataResult(title="Total Recall", year=1990, kind="movie", payload={"imdbID": "tt0100802"})
    reg = {
        "tmdb": _detail_source("tmdb", "no tmdb key", None, calls),
        "omdb": _detail_source("omdb", None, recall, calls),
    }
    row = SuggestionCandidate(
        title="Total Recall",
        year=1990,
        kind="movie",
        provider="tmdb",
        providers=["tmdb", "omdb"],
        ids={"tmdb": "861", "imdb": "tt0100802"},
        score=71.0,
    )
    async with httpx.AsyncClient() as client:
        hit = await MetadataDispatcher(client, sources=reg).refetch(row, _config())
    # OMDb takes the IMDb id.
    assert hit is not None and hit.provider == "omdb" and calls == ["omdb:movie:tt0100802"]


async def test_refetch_is_none_when_no_provider_can_answer():
    from arm_common.schemas import SuggestionCandidate

    calls: list[str] = []
    reg = {"omdb": _detail_source("omdb", None, None, calls)}
    row = SuggestionCandidate(
        title="X", kind="movie", provider="tmdb", providers=["tmdb", "omdb"], ids={"tmdb": "1", "imdb": "tt1"}, score=50
    )
    async with httpx.AsyncClient() as client:
        assert await MetadataDispatcher(client, sources=reg).refetch(row, _config()) is None
    assert calls == ["omdb:movie:tt1"]
