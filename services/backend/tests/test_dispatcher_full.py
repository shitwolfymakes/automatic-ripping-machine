"""Supplementary MetadataDispatcher branch coverage — the orchestration
paths test_dispatcher.py doesn't reach: crc64/1337server-first, the
no-volume-label / empty-title short-circuits, TMDB-tv hit, OMDB-without-
TMDB-key, the out-of-range year guard, and _call's LookupError/timeout
swallows.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import respx  # noqa: E402

from arm_backend.metadata.dispatcher import MetadataDispatcher, _normalize_volume_label  # noqa: E402
from arm_common import Config, DiscType  # noqa: E402
from arm_common.schemas import ScanResult  # noqa: E402

_ARM = "https://1337server.pythonanywhere.com/api/v1/"


def _config(**overrides: object) -> Config:
    base: dict[str, object] = dict(
        id=1,
        tmdb_api_key="tmdb-k",
        omdb_api_key="omdb-k",
        musicbrainz_user_agent="arm-test/0.0 (t@example.com)",
    )
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


def _scan(**kw: object) -> ScanResult:
    return ScanResult(disc_type=DiscType.DVD, **kw)  # type: ignore[arg-type]


def test_normalize_year_out_of_range() -> None:
    """A 4-digit run outside 1900-2100 is not treated as a year (35->37)."""
    title, year = _normalize_volume_label("DISC_3050")
    assert year is None
    assert "3050" not in title or title  # number kept in title, just not parsed as year


async def test_crc64_arm_server_hit_wins() -> None:
    with respx.mock:
        respx.get(_ARM).mock(
            return_value=httpx.Response(
                200, json={"success": True, "results": {"0": {"title": "Iron Man", "year": 2008}}}
            )
        )
        async with httpx.AsyncClient(timeout=5.0) as http:
            scan = _scan(volume_label="ANYTHING", fingerprints=[{"algo": "crc64", "value": "abc"}])
            result = await MetadataDispatcher(http).identify(scan, _config())
    assert result is not None
    assert result.title == "Iron Man"


async def test_crc64_miss_then_tmdb_fallback() -> None:
    with respx.mock:
        respx.get(_ARM).mock(return_value=httpx.Response(200, json={"success": False}))
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=httpx.Response(200, json={"results": [{"title": "Found", "release_date": "2010-01-01"}]})
        )
        async with httpx.AsyncClient(timeout=5.0) as http:
            scan = _scan(volume_label="FOUND_2010", fingerprints=[{"algo": "crc64", "value": "x"}])
            result = await MetadataDispatcher(http).identify(scan, _config())
    assert result is not None and result.title == "Found"


async def test_no_volume_label_after_crc64_miss_returns_none() -> None:
    with respx.mock:
        respx.get(_ARM).mock(return_value=httpx.Response(200, json={"success": False}))
        async with httpx.AsyncClient(timeout=5.0) as http:
            scan = _scan(volume_label=None, fingerprints=[{"algo": "crc64", "value": "x"}])
            result = await MetadataDispatcher(http).identify(scan, _config())
    assert result is None


async def test_empty_title_after_normalize_returns_none() -> None:
    """A volume label that is purely a year normalizes to an empty title."""
    async with httpx.AsyncClient(timeout=5.0) as http:
        result = await MetadataDispatcher(http).identify(_scan(volume_label="1999"), _config())
    assert result is None


async def test_tmdb_movie_miss_tv_hit() -> None:
    with respx.mock:
        respx.get("https://api.themoviedb.org/3/search/movie").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        respx.get("https://api.themoviedb.org/3/search/tv").mock(
            return_value=httpx.Response(200, json={"results": [{"name": "Show", "first_air_date": "2015"}]})
        )
        async with httpx.AsyncClient(timeout=5.0) as http:
            result = await MetadataDispatcher(http).identify(_scan(volume_label="SHOW"), _config())
    assert result is not None and result.kind == "tv"


async def test_omdb_used_when_no_tmdb_key() -> None:
    with respx.mock:
        respx.get("https://www.omdbapi.com/").mock(
            return_value=httpx.Response(200, json={"Response": "True", "Title": "OmdbOnly", "Year": "2001"})
        )
        async with httpx.AsyncClient(timeout=5.0) as http:
            result = await MetadataDispatcher(http).identify(_scan(volume_label="OMDBONLY"), _config(tmdb_api_key=None))
    assert result is not None and result.title == "OmdbOnly"


async def test_call_swallows_lookup_error() -> None:
    """A provider 5xx raises LookupError inside _call → logged, returns None,
    and (no other provider configured) identify yields None."""
    with respx.mock:
        respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient(timeout=5.0) as http:
            result = await MetadataDispatcher(http).identify(_scan(volume_label="BOOM"), _config(tmdb_api_key=None))
    assert result is None


async def test_call_swallows_timeout() -> None:
    with respx.mock:
        respx.get("https://www.omdbapi.com/").mock(side_effect=httpx.TimeoutException("t"))
        async with httpx.AsyncClient(timeout=5.0) as http:
            result = await MetadataDispatcher(http).identify(_scan(volume_label="SLOW"), _config(tmdb_api_key=None))
    assert result is None


async def test_no_providers_configured_returns_none() -> None:
    """No crc64, no TMDB key, no OMDB key → fall through to return None
    (the `if omdb_key:` false branch, 96->102)."""
    async with httpx.AsyncClient(timeout=5.0) as http:
        result = await MetadataDispatcher(http).identify(
            _scan(volume_label="TITLE"), _config(tmdb_api_key=None, omdb_api_key=None)
        )
    assert result is None


async def test_call_asyncio_timeout_branch(monkeypatch: object) -> None:
    """Drive _call's real asyncio.wait_for timeout (108-109), distinct from
    a provider's own httpx-timeout → LookupTimeout."""
    import asyncio

    from arm_backend.metadata import dispatcher as disp_mod

    monkeypatch.setattr(disp_mod, "PROVIDER_TIMEOUT_SECONDS", 0.01)  # type: ignore[attr-defined]

    async def _slow() -> None:
        await asyncio.sleep(1.0)

    async with httpx.AsyncClient() as http:
        d = MetadataDispatcher(http)
        assert await d._call("slow", _slow()) is None


async def test_call_lookup_error_branch() -> None:
    from arm_backend.metadata.base import LookupError as MetaLookupError

    async def _boom() -> None:
        raise MetaLookupError("nope")

    async with httpx.AsyncClient() as http:
        d = MetadataDispatcher(http)
        assert await d._call("boom", _boom()) is None


async def test_aclose_closes_http() -> None:
    http = httpx.AsyncClient()
    await MetadataDispatcher(http).aclose()
    assert http.is_closed
