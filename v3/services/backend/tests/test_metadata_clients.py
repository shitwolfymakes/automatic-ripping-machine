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
