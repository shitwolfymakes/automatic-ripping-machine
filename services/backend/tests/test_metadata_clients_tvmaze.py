"""TVmaze title-search client (PR 2b). respx-mocked; no network."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

from arm_backend.metadata.base import LookupError, LookupTimeout  # noqa: E402
from arm_backend.metadata.tvmaze import TVMazeClient, show_to_result, title_is_close  # noqa: E402

_BASE = "https://api.tvmaze.com"
_SHOW = {
    "id": 4607,
    "name": "Lost",
    "premiered": "2004-09-22",
    "externals": {"tvrage": 2600, "thetvdb": 73739, "imdb": "tt0411008"},
    "image": {"medium": "https://static.tvmaze.com/uploads/images/medium_portrait/1/2.jpg"},
}


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def test_show_to_result_maps_ids_year_and_poster():
    result = show_to_result(_SHOW)
    assert result is not None
    assert (result.title, result.year, result.kind) == ("Lost", 2004, "tv")
    assert result.payload["tvmaze_id"] == "4607"
    assert result.payload["imdb_id"] == "tt0411008"
    assert result.payload["tvdb_id"] == "73739"
    assert result.payload["poster_url"].startswith("https://static.tvmaze.com/")


def test_show_to_result_tolerates_missing_fields():
    result = show_to_result({"id": 1, "name": "Untitled", "externals": {"imdb": None}, "image": None})
    assert result is not None and result.year is None
    assert "imdb_id" not in result.payload and "tvdb_id" not in result.payload and "poster_url" not in result.payload
    assert show_to_result({"id": 2}) is None  # no name
    assert show_to_result("not a dict") is None


@respx.mock
async def test_search_show_uses_singlesearch(http_client):
    route = respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(200, json=_SHOW))
    result = await TVMazeClient(http_client).search_show("lost")
    assert result.title == "Lost" and result.payload["tvmaze_id"] == "4607"
    assert route.calls.last.request.url.params["q"] == "lost"


@respx.mock
async def test_search_show_404_is_a_lookup_error(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(404, json={"name": "Not Found"}))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_show("nothing here")


@respx.mock
async def test_search_candidates_unwraps_show_entries(http_client):
    respx.get(f"{_BASE}/search/shows").mock(
        return_value=httpx.Response(200, json=[{"score": 1.0, "show": _SHOW}, {"score": 0.5, "show": {"id": 9}}])
    )
    results = await TVMazeClient(http_client).search_candidates("lost", limit=5)
    assert [r.title for r in results] == ["Lost"]


@respx.mock
async def test_lookup_by_imdb_id_follows_redirects(http_client):
    respx.get(f"{_BASE}/lookup/shows").mock(return_value=httpx.Response(200, json=_SHOW))
    result = await TVMazeClient(http_client).lookup_by_imdb_id("tt0411008")
    assert result.payload["imdb_id"] == "tt0411008"
    assert respx.calls.last.request.url.params["imdb"] == "tt0411008"


@respx.mock
async def test_timeout_and_transport_errors(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LookupTimeout):
        await TVMazeClient(http_client).search_show("lost")
    respx.get(f"{_BASE}/search/shows").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_candidates("lost")
    respx.get(f"{_BASE}/lookup/shows").mock(return_value=httpx.Response(500))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).lookup_by_imdb_id("tt1")


def test_title_is_close_rules():
    assert title_is_close("the.office!", "The Office")
    assert title_is_close("lost", "Lost")
    assert title_is_close("the office", "The Office (US)")
    assert title_is_close("heat", "Heat of the Night")  # deliberate: whole-word containment
    assert not title_is_close("blade runner 1982", "Lost")
    assert not title_is_close("", "Lost")
    assert not title_is_close("lost", "")
    assert title_is_close("君の名は", "君の名は")
    assert title_is_close("Война и мир", "война и мир")
    assert title_is_close("Amélie", "Amélie")
    assert title_is_close("amelie", "Amélie")  # pinned: difflib ratio is above 0.75


@respx.mock
async def test_search_show_rejects_a_far_match(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(200, json=_SHOW))
    with pytest.raises(LookupError, match="not close"):
        await TVMazeClient(http_client).search_show("blade runner")


@respx.mock
async def test_search_show_non_json_body_is_a_lookup_error(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(200, content=b"<html>"))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_show("lost")


@respx.mock
async def test_search_candidates_non_list_body_is_a_lookup_error(http_client):
    respx.get(f"{_BASE}/search/shows").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_candidates("lost")


@respx.mock
async def test_search_candidates_caps_at_limit(http_client):
    shows = [{"show": {**_SHOW, "id": i, "name": f"Lost {i}"}} for i in range(3)]
    respx.get(f"{_BASE}/search/shows").mock(return_value=httpx.Response(200, json=shows))
    assert len(await TVMazeClient(http_client).search_candidates("lost", limit=2)) == 2


def test_show_to_result_poster_fallbacks():
    original = show_to_result({"name": "X", "image": {"original": "https://x/o.jpg"}})
    assert original is not None and original.payload["poster_url"] == "https://x/o.jpg"
    bad = show_to_result({"name": "X", "image": {"medium": "ftp://x/m.jpg"}})
    assert bad is not None and "poster_url" not in bad.payload
