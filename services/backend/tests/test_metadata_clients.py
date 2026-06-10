import httpx
import pytest
import respx

from arm_backend.metadata.base import LookupError
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@respx.mock
async def test_tmdb_movie_hit(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "The Matrix", "release_date": "1999-03-31", "id": 603}]},
        )
    )
    client = TMDBClient("v4-bearer-key", http_client)
    result = await client.search_movie("the matrix", 1999)
    assert result.title == "The Matrix"
    assert result.year == 1999
    assert result.kind == "movie"
    assert result.payload["id"] == 603

    request = respx.calls.last.request
    assert request.headers["Authorization"] == "Bearer v4-bearer-key"
    assert "v4-bearer-key" not in str(request.url)


@respx.mock
async def test_tmdb_movie_miss(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.search_movie("nope")


@respx.mock
async def test_tmdb_auth_failed(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(401))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.search_movie("x")


@respx.mock
async def test_omdb_hit(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Some Movie", "Year": "2010", "imdbID": "tt0000001"},
        )
    )
    client = OMDBClient("k", http_client)
    result = await client.lookup_by_title("Some Movie", 2010)
    assert result.title == "Some Movie"
    assert result.year == 2010


@respx.mock
async def test_omdb_miss(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "not found"})
    )
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.lookup_by_title("nope")


@respx.mock
async def test_musicbrainz_hit(http_client):
    respx.get("https://musicbrainz.org/ws/2/discid/abc123").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [{"title": "Album Name", "date": "2005-04-12"}],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("abc123")
    assert result.title == "Album Name"
    assert result.year == 2005
    assert result.kind == "music"

    request = respx.calls.last.request
    assert request.headers["User-Agent"].startswith("arm-test/")


async def test_musicbrainz_requires_user_agent(http_client):
    with pytest.raises(ValueError):
        MusicBrainzClient("", http_client)


@respx.mock
async def test_musicbrainz_extracts_artist_album_tracks(http_client):
    """Full happy path: parser populates the top-level keys that the music
    path template reads — artist, album, tracks[].title — directly into the
    payload that becomes job.metadata_json."""
    respx.get("https://musicbrainz.org/ws/2/discid/abc123").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "rel-uuid-1",
                        "title": "Dark Side of the Moon",
                        "date": "1973-03-01",
                        "artist-credit": [{"name": "Pink Floyd"}],
                        "media": [
                            {
                                "position": 1,
                                "format": "CD",
                                "discs": [{"id": "abc123"}],
                                "tracks": [
                                    {"position": "1", "title": "Speak to Me"},
                                    {"position": "2", "title": "Breathe"},
                                    {"position": "3", "title": "On the Run"},
                                ],
                            }
                        ],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("abc123")
    assert result.title == "Dark Side of the Moon"
    assert result.year == 1973
    # Top-level parsed fields — what _build_track_ctx reads.
    assert result.payload["artist"] == "Pink Floyd"
    assert result.payload["album"] == "Dark Side of the Moon"
    assert result.payload["tracks"] == [
        {"title": "Speak to Me", "position": 1},
        {"title": "Breathe", "position": 2},
        {"title": "On the Run", "position": 3},
    ]
    # release["id"] is preserved by spread — extract_poster_url derives
    # the Cover Art Archive URL from it.
    assert result.payload["id"] == "rel-uuid-1"


@respx.mock
async def test_musicbrainz_multi_disc_matches_by_disc_id(http_client):
    """A 2-CD release: media[0] is disc 1 (different disc_id), media[1]
    is disc 2 (our disc_id). The parser must pick media[1]'s tracks."""
    respx.get("https://musicbrainz.org/ws/2/discid/discB").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "rel-uuid",
                        "title": "Mellon Collie",
                        "date": "1995",
                        "artist-credit": [{"name": "Smashing Pumpkins"}],
                        "media": [
                            {
                                "position": 1,
                                "discs": [{"id": "discA"}],
                                "tracks": [
                                    {"position": "1", "title": "Dawn to Dusk Track 1"},
                                ],
                            },
                            {
                                "position": 2,
                                "discs": [{"id": "discB"}],
                                "tracks": [
                                    {"position": "1", "title": "Twilight to Starlight 1"},
                                    {"position": "2", "title": "Twilight to Starlight 2"},
                                ],
                            },
                        ],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("discB")
    assert [t["title"] for t in result.payload["tracks"]] == [
        "Twilight to Starlight 1",
        "Twilight to Starlight 2",
    ]


@respx.mock
async def test_musicbrainz_single_disc_release_no_discs_array(http_client):
    """Single-disc releases sometimes omit the `discs[]` array on the
    medium. Parser must fall back to media[0] without raising."""
    respx.get("https://musicbrainz.org/ws/2/discid/xyz").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "rel-uuid",
                        "title": "Self-Titled",
                        "date": "2020",
                        "artist-credit": [{"name": "The Band"}],
                        "media": [
                            {
                                "position": 1,
                                "tracks": [
                                    {"position": "1", "title": "Opener"},
                                ],
                            }
                        ],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("xyz")
    assert result.payload["tracks"] == [{"title": "Opener", "position": 1}]


@respx.mock
async def test_musicbrainz_multi_artist_credit_with_joinphrase(http_client):
    """A collaboration with `joinphrase` ('A & B' or 'A feat. B') is
    rendered by walking the artist-credit list and concatenating the
    name + joinphrase pairs."""
    respx.get("https://musicbrainz.org/ws/2/discid/q").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "r1",
                        "title": "Collab Album",
                        "date": "2018",
                        "artist-credit": [
                            {"name": "Daft Punk", "joinphrase": " & "},
                            {"name": "The Weeknd"},
                        ],
                        "media": [{"tracks": [{"position": "1", "title": "Starboy"}]}],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("q")
    assert result.payload["artist"] == "Daft Punk & The Weeknd"


@respx.mock
async def test_musicbrainz_empty_artist_credit_yields_empty_string(http_client):
    """Edge: `artist-credit` is empty — artist resolves to empty string.
    Downstream this trips template validation as a fan-out skip, NOT a
    500. The identify itself still succeeds (title/year are present)."""
    respx.get("https://musicbrainz.org/ws/2/discid/q").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "r1",
                        "title": "Unknown Artist Disc",
                        "date": "2010",
                        "artist-credit": [],
                        "media": [{"tracks": [{"position": "1", "title": "T1"}]}],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("q")
    assert result.payload["artist"] == ""
    assert result.payload["album"] == "Unknown Artist Disc"


@respx.mock
async def test_musicbrainz_skips_artist_credit_entries_without_name(http_client):
    """Defensive: a credit entry with a missing/non-string name is
    skipped rather than rendered as 'None' / empty in the joined string."""
    respx.get("https://musicbrainz.org/ws/2/discid/q").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "r1",
                        "title": "Album",
                        "date": "2010",
                        "artist-credit": [
                            {},  # no name at all
                            {"name": None},  # name is null
                            {"name": "Real Artist"},
                        ],
                        "media": [{"tracks": [{"position": "1", "title": "T"}]}],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("q")
    assert result.payload["artist"] == "Real Artist"


@respx.mock
async def test_musicbrainz_no_media_yields_empty_tracks(http_client):
    """Edge: release has no `media[]` (degenerate response). Tracks list
    is empty, no exception. Identify still produces a usable result."""
    respx.get("https://musicbrainz.org/ws/2/discid/q").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "r1",
                        "title": "Album",
                        "date": "2010",
                        "artist-credit": [{"name": "A"}],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("q")
    assert result.payload["tracks"] == []


@respx.mock
async def test_musicbrainz_tracks_drop_entries_without_title(http_client):
    """Defensive: a track entry with a non-string `title` (or None) is
    skipped rather than crashing the parser. A non-integer string position
    falls through with no `position` key (kept off the dict entirely)."""
    respx.get("https://musicbrainz.org/ws/2/discid/q").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "r1",
                        "title": "Album",
                        "date": "2010",
                        "artist-credit": [{"name": "A"}],
                        "media": [
                            {
                                "tracks": [
                                    {"position": "1", "title": "Good Track"},
                                    {"position": "2", "title": None},
                                    {"position": "?", "title": "Mystery Position"},
                                    {"position": 4, "title": "Int Position"},
                                ]
                            }
                        ],
                    }
                ],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("q")
    assert result.payload["tracks"] == [
        {"title": "Good Track", "position": 1},
        {"title": "Mystery Position"},
        {"title": "Int Position", "position": 4},
    ]


@respx.mock
async def test_omdb_search_candidates(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [
                    {"Title": "The Matrix", "Year": "1999", "imdbID": "tt0133093", "Poster": "http://x/p.jpg"},
                    {"Title": "The Matrix Reloaded", "Year": "2003", "imdbID": "tt0234215", "Poster": "N/A"},
                ],
            },
        )
    )
    client = OMDBClient("k", http_client)
    results = await client.search_candidates("matrix", kind="movie")
    assert [r.title for r in results] == ["The Matrix", "The Matrix Reloaded"]
    assert results[0].year == 1999
    assert results[0].payload["imdbID"] == "tt0133093"
    # search uses the OMDB `s=` param (not `t=`); guard against a future typo.
    assert "s=matrix" in str(respx.calls.last.request.url)


@respx.mock
async def test_omdb_search_no_results_returns_empty(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "Movie not found!"})
    )
    client = OMDBClient("k", http_client)
    results = await client.search_candidates("zzzznope", kind="movie")
    assert results == []


@respx.mock
async def test_omdb_search_auth_failure_raises(http_client):
    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(401))
    client = OMDBClient("bad", http_client)
    with pytest.raises(LookupError):
        await client.search_candidates("matrix", kind="movie")


@respx.mock
async def test_omdb_lookup_by_imdb_id(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Title": "The Matrix",
                "Year": "1999",
                "imdbID": "tt0133093",
            },
        )
    )
    client = OMDBClient("k", http_client)
    result = await client.lookup_by_imdb_id("tt0133093")
    assert result.title == "The Matrix"
    assert result.year == 1999
    # lookup uses the OMDB `i=` param; guard against a future typo.
    assert "i=tt0133093" in str(respx.calls.last.request.url)


# ---------------------------------------------------------------------------
# Coverage gap tests — lookup_by_title error branches
# ---------------------------------------------------------------------------


@respx.mock
async def test_omdb_lookup_by_title_timeout_raises(http_client):
    from arm_backend.metadata.base import LookupTimeout

    def _raise_timeout(request):
        raise httpx.TimeoutException("timed out", request=request)

    respx.get("https://www.omdbapi.com/").mock(side_effect=_raise_timeout)
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupTimeout):
        await client.lookup_by_title("x")


@respx.mock
async def test_omdb_lookup_by_title_transport_error_raises(http_client):

    def _raise_transport(request):
        raise httpx.ConnectError("conn refused", request=request)

    respx.get("https://www.omdbapi.com/").mock(side_effect=_raise_transport)
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.lookup_by_title("x")


@respx.mock
async def test_omdb_lookup_by_title_401_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(401))
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="omdb auth failed"):
        await client.lookup_by_title("x")


@respx.mock
async def test_omdb_lookup_by_title_5xx_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(503))
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="5xx"):
        await client.lookup_by_title("x")


@respx.mock
async def test_omdb_lookup_by_title_non200_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(404))
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="omdb status=404"):
        await client.lookup_by_title("x")


@respx.mock
async def test_omdb_lookup_by_title_missing_title_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "", "Year": "2000"})
    )
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="missing title"):
        await client.lookup_by_title("x")


# ---------------------------------------------------------------------------
# Coverage gap tests — search_candidates error branches
# ---------------------------------------------------------------------------

# Note: the shared transport/status branches (timeout, transport error, 401,
# 5xx, non-200) live in OMDBClient._get_json and are covered once by the
# lookup_by_title_*_raises tests above. search_candidates / lookup_by_imdb_id
# only need their own BEHAVIOR tests (empty-vs-raise, skip, kind inference).


@respx.mock
async def test_omdb_search_candidates_skips_items_without_title(http_client):
    """Items in Search[] that have no Title are silently skipped."""

    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [
                    {"Title": "", "Year": "2000", "imdbID": "tt0000001"},
                    {"Year": "2001", "imdbID": "tt0000002"},  # missing Title key
                    {"Title": "Real Movie", "Year": "2002", "imdbID": "tt0000003"},
                ],
            },
        )
    )
    client = OMDBClient("k", http_client)
    results = await client.search_candidates("real", kind="movie")
    assert len(results) == 1
    assert results[0].title == "Real Movie"


@respx.mock
async def test_omdb_lookup_by_imdb_id_miss_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "Incorrect IMDb ID."})
    )
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="omdb miss"):
        await client.lookup_by_imdb_id("tt9999999")


@respx.mock
async def test_omdb_lookup_by_imdb_id_missing_title_raises(http_client):

    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "", "Year": "2000"})
    )
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError, match="missing title"):
        await client.lookup_by_imdb_id("tt0133093")


@respx.mock
async def test_omdb_lookup_by_imdb_id_tv_series_kind(http_client):
    """When OMDB returns Type=series, kind is set to 'tv'."""

    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Title": "Breaking Bad",
                "Year": "2008",
                "Type": "series",
            },
        )
    )
    client = OMDBClient("k", http_client)
    result = await client.lookup_by_imdb_id("tt0903747")
    assert result.kind == "tv"


# ---------------------------------------------------------------------------
# TMDB multi-result candidate search
# ---------------------------------------------------------------------------


@respx.mock
async def test_tmdb_search_movie_candidates(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "The Matrix", "release_date": "1999-03-31", "id": 603, "poster_path": "/a.jpg"},
                    {"title": "The Matrix Reloaded", "release_date": "2003-05-15", "id": 604, "poster_path": "/b.jpg"},
                ]
            },
        )
    )
    client = TMDBClient("k", http_client)
    results = await client.search_movie_candidates("matrix")
    assert [r.title for r in results] == ["The Matrix", "The Matrix Reloaded"]
    assert results[0].year == 1999
    assert results[0].payload["poster_path"] == "/a.jpg"


@respx.mock
async def test_tmdb_search_tv_candidates(http_client):
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"name": "Battlestar Galactica", "first_air_date": "2004-10-18", "id": 1972},
                ]
            },
        )
    )
    client = TMDBClient("k", http_client)
    results = await client.search_tv_candidates("galactica")
    assert results[0].title == "Battlestar Galactica"
    assert results[0].year == 2004
    assert results[0].kind == "tv"


@respx.mock
async def test_tmdb_search_empty_results(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    client = TMDBClient("k", http_client)
    assert await client.search_movie_candidates("zzz") == []


@respx.mock
async def test_tmdb_search_auth_failure_raises(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(401))
    client = TMDBClient("bad", http_client)
    with pytest.raises(LookupError):
        await client.search_movie_candidates("matrix")


@respx.mock
async def test_tmdb_search_candidates_skips_items_without_title(http_client):
    """Items with no usable title are silently skipped; tv path + original_name fallback exercised."""
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"name": "", "first_air_date": "2000-01-01", "id": 1},  # empty name — skip
                    {"first_air_date": "2001-01-01", "id": 2},  # missing name key — skip
                    {
                        "original_name": "Fallback Show",
                        "first_air_date": "2002-06-01",
                        "id": 3,
                    },  # original_name fallback
                ]
            },
        )
    )
    client = TMDBClient("k", http_client)
    results = await client.search_tv_candidates("x")
    assert len(results) == 1
    assert results[0].title == "Fallback Show"
    assert results[0].year == 2002


@respx.mock
async def test_tmdb_get_results_5xx_raises(http_client):
    # Covers the shared _get_results 5xx branch (used by both search paths).
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(503))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError, match="5xx"):
        await client.search_movie_candidates("x")


@respx.mock
async def test_tmdb_get_results_timeout_raises(http_client):
    from arm_backend.metadata.base import LookupTimeout

    def _raise_timeout(request):
        raise httpx.TimeoutException("timed out", request=request)

    respx.get("https://api.themoviedb.org/3/search/movie").mock(side_effect=_raise_timeout)
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupTimeout):
        await client.search_movie_candidates("x")


@respx.mock
async def test_tmdb_search_movie_top_hit_with_year(http_client):
    # Covers single-hit search_movie + the year-param branch.
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Iron Man", "release_date": "2008-05-02", "id": 1726},
                ]
            },
        )
    )
    client = TMDBClient("k", http_client)
    result = await client.search_movie("iron man", 2008)
    assert result.title == "Iron Man"
    assert result.year == 2008
    assert "year=2008" in str(respx.calls.last.request.url)


@respx.mock
async def test_tmdb_search_tv_top_hit(http_client):
    # Covers single-hit search_tv path.
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"name": "The Expanse", "first_air_date": "2015-12-14", "id": 63639},
                ]
            },
        )
    )
    client = TMDBClient("k", http_client)
    result = await client.search_tv("expanse")
    assert result.title == "The Expanse"
    assert result.kind == "tv"


@respx.mock
async def test_tmdb_search_top_result_missing_title_raises(http_client):
    # Covers the _search "top result missing title" branch.
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"release_date": "1999-01-01", "id": 1}]})
    )
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError, match="missing title"):
        await client.search_movie("x")


@respx.mock
async def test_tmdb_get_results_transport_error_raises(http_client):
    # Covers the shared _get_results HTTPError (non-timeout transport) branch.
    def _raise_transport(request):
        raise httpx.ConnectError("conn refused", request=request)

    respx.get("https://api.themoviedb.org/3/search/movie").mock(side_effect=_raise_transport)
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError, match="transport error"):
        await client.search_movie_candidates("x")


@respx.mock
async def test_tmdb_get_results_non200_raises(http_client):
    # Covers the shared _get_results non-200 (non-401, non-5xx) branch.
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(404))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError, match="status=404"):
        await client.search_movie_candidates("x")


@respx.mock
async def test_tmdb_search_movie_candidates_with_year(http_client):
    # Covers the year-param branch in search_movie_candidates.
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"title": "Dune", "release_date": "2021-09-15", "id": 1}]})
    )
    client = TMDBClient("k", http_client)
    results = await client.search_movie_candidates("dune", year=2021)
    assert results[0].title == "Dune"
    assert "year=2021" in str(respx.calls.last.request.url)


# ---------------------------------------------------------------------------
# MusicBrainz release search
# ---------------------------------------------------------------------------


@respx.mock
async def test_musicbrainz_search_releases(http_client):
    respx.get("https://musicbrainz.org/ws/2/release").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "title": "The Dark Side of the Moon",
                        "date": "1973-03-01",
                        "id": "mb-1",
                        "artist-credit": [{"name": "Pink Floyd"}],
                    },
                ]
            },
        )
    )
    client = MusicBrainzClient("arm/test", http_client)
    results = await client.search_releases("dark side of the moon")
    assert results[0].title == "The Dark Side of the Moon"
    assert results[0].year == 1973
    assert results[0].kind == "music"
    assert results[0].payload["artist"] == "Pink Floyd"


@respx.mock
async def test_musicbrainz_search_empty(http_client):
    respx.get("https://musicbrainz.org/ws/2/release").mock(return_value=httpx.Response(200, json={"releases": []}))
    client = MusicBrainzClient("arm/test", http_client)
    assert await client.search_releases("zzz") == []


@respx.mock
async def test_musicbrainz_search_5xx_raises(http_client):
    respx.get("https://musicbrainz.org/ws/2/release").mock(return_value=httpx.Response(503))
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupError):
        await client.search_releases("x")


@respx.mock
async def test_musicbrainz_search_skips_releases_without_title(http_client):
    """Releases missing the title key are silently skipped."""
    respx.get("https://musicbrainz.org/ws/2/release").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {"date": "2000-01-01", "id": "mb-no-title"},  # no title key
                    {"title": "", "date": "2001-01-01", "id": "mb-empty-title"},  # empty title
                    {"title": "Real Album", "date": "2002-06-15", "id": "mb-real"},
                ]
            },
        )
    )
    client = MusicBrainzClient("arm/test", http_client)
    results = await client.search_releases("real")
    assert len(results) == 1
    assert results[0].title == "Real Album"


@respx.mock
async def test_musicbrainz_search_timeout_raises(http_client):
    from arm_backend.metadata.base import LookupTimeout

    def _raise_timeout(request):
        raise httpx.TimeoutException("timed out", request=request)

    respx.get("https://musicbrainz.org/ws/2/release").mock(side_effect=_raise_timeout)
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupTimeout):
        await client.search_releases("x")


@respx.mock
async def test_musicbrainz_transport_error_raises(http_client):
    # Covers the shared _get HTTPError branch (non-timeout transport failure).
    def _raise_transport(request):
        raise httpx.ConnectError("conn refused", request=request)

    respx.get("https://musicbrainz.org/ws/2/release").mock(side_effect=_raise_transport)
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupError, match="transport error"):
        await client.search_releases("x")


@respx.mock
async def test_musicbrainz_get_non200_raises(http_client):
    # Covers the shared _get non-200 (non-5xx) branch.
    respx.get("https://musicbrainz.org/ws/2/release").mock(return_value=httpx.Response(404))
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupError, match="status=404"):
        await client.search_releases("x")


@respx.mock
async def test_musicbrainz_disc_id_no_releases_raises(http_client):
    # Covers lookup_disc_id's "no releases" branch.
    respx.get("https://musicbrainz.org/ws/2/discid/abc").mock(return_value=httpx.Response(200, json={"releases": []}))
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupError, match="no releases"):
        await client.lookup_disc_id("abc")


@respx.mock
async def test_musicbrainz_disc_id_top_release_missing_title_raises(http_client):
    # Covers lookup_disc_id's "top release missing title" branch.
    respx.get("https://musicbrainz.org/ws/2/discid/abc").mock(
        return_value=httpx.Response(200, json={"releases": [{"date": "1999"}]})
    )
    client = MusicBrainzClient("arm/test", http_client)
    with pytest.raises(LookupError, match="missing title"):
        await client.lookup_disc_id("abc")
