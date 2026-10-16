"""Provider payload -> IdentityFacts (match picker spec 3.2). Pure; no I/O."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.metadata.facts import facts_for, omdb_facts, tmdb_facts, tvdb_facts, tvmaze_facts  # noqa: E402
from arm_common.schemas.job_metadata import IdentityFacts  # noqa: E402

TMDB_TV = {
    "id": 5084,
    "name": "Kolchak: The Night Stalker",
    "first_air_date": "1974-09-13",
    "last_air_date": "1975-03-28",
    "status": "Ended",
    "overview": "Chicago newspaper reporter Carl Kolchak investigates crimes.",
    "vote_average": 7.9,
    "vote_count": 210,
    "genres": [{"id": 1, "name": "Mystery"}, {"id": 2, "name": "Sci-Fi & Fantasy"}],
    "created_by": [{"name": "Jeff Rice"}],
    "number_of_episodes": 20,
    "aggregate_credits": {
        "cast": [
            {"name": "Simon Oakland", "order": 1},
            {"name": "Darren McGavin", "order": 0},
            {"name": "Jack Grinnage", "order": 2},
            {"name": "Ruth McDevitt", "order": 3},
        ]
    },
}

TMDB_MOVIE = {
    "title": "The Night Stalker",
    "release_date": "1972-01-11",
    "vote_average": 7.5,
    "vote_count": 0,
    "credits": {
        "cast": [{"name": "Darren McGavin", "order": 0}],
        "crew": [{"name": "John Llewellyn Moxey", "job": "Director"}, {"name": "Someone", "job": "Writer"}],
    },
}


def test_tmdb_tv_facts() -> None:
    f = tmdb_facts(TMDB_TV, "tv")
    assert f == IdentityFacts(
        end_year=1975,
        overview="Chicago newspaper reporter Carl Kolchak investigates crimes.",
        rating=7.9,
        rating_source="tmdb",
        votes=210,
        genres=["Mystery", "Sci-Fi & Fantasy"],
        creators=["Jeff Rice"],
        cast=["Darren McGavin", "Simon Oakland", "Jack Grinnage"],
        episode_count=20,
    )


def test_tmdb_running_show_has_no_end_year() -> None:
    assert tmdb_facts({**TMDB_TV, "status": "Returning Series"}, "tv").end_year is None


def test_tmdb_movie_uses_directors_and_hides_zero_vote_rating() -> None:
    f = tmdb_facts(TMDB_MOVIE, "movie")
    assert f.creators == ["John Llewellyn Moxey"]
    assert f.cast == ["Darren McGavin"]
    assert (f.rating, f.rating_source, f.votes, f.episode_count) == (None, None, None, None)


def test_tmdb_search_item_without_detail_still_gives_overview_and_rating() -> None:
    f = tmdb_facts({"name": "X", "overview": "Plot.", "vote_average": 6.0, "vote_count": 5, "genre_ids": [1]}, "tv")
    assert (f.overview, f.rating, f.genres, f.cast) == ("Plot.", 6.0, [], [])


def test_omdb_series_facts() -> None:
    f = omdb_facts(
        {
            "Title": "Kolchak: The Night Stalker",
            "Year": "1974–1975",
            "Plot": "A reporter investigates.",
            "imdbRating": "7.9",
            "imdbVotes": "9,812",
            "Genre": "Horror, Mystery, Sci-Fi",
            "Actors": "Darren McGavin, Simon Oakland, Jack Grinnage, Ruth McDevitt",
            "Director": "N/A",
            "Writer": "Jeff Rice",
            "Type": "series",
        },
        "tv",
    )
    assert f == IdentityFacts(
        end_year=1975,
        overview="A reporter investigates.",
        rating=7.9,
        rating_source="imdb",
        votes=9812,
        genres=["Horror", "Mystery", "Sci-Fi"],
        creators=["Jeff Rice"],
        cast=["Darren McGavin", "Simon Oakland", "Jack Grinnage"],
    )


def test_omdb_na_values_are_absent_and_movie_uses_director() -> None:
    f = omdb_facts(
        {"Year": "2005–", "Plot": "N/A", "imdbRating": "N/A", "imdbVotes": "N/A", "Genre": "N/A", "Director": "A, B"},
        "movie",
    )
    assert f == IdentityFacts(creators=["A", "B"])


def test_tvmaze_facts_strip_html_and_count_embedded_episodes() -> None:
    f = tvmaze_facts(
        {
            "premiered": "1974-09-13",
            "ended": "1975-03-28",
            "summary": "<p><b>Kolchak</b> investigates &amp; reports.</p>",
            "rating": {"average": 8},
            "genres": ["Horror", "Science-Fiction"],
            "_embedded": {
                "cast": [{"person": {"name": "Darren McGavin"}}, {"person": {"name": "Simon Oakland"}}],
                "episodes": [{"id": 1}, {"id": 2}],
            },
        }
    )
    assert f == IdentityFacts(
        end_year=1975,
        overview="Kolchak investigates & reports.",
        rating=8.0,
        rating_source="tvmaze",
        genres=["Horror", "Science-Fiction"],
        cast=["Darren McGavin", "Simon Oakland"],
        episode_count=2,
    )


def test_tvmaze_search_body_without_embeds() -> None:
    f = tvmaze_facts({"ended": None, "summary": None, "rating": {"average": None}, "genres": []})
    assert f == IdentityFacts()


def test_tvdb_facts_prefer_english_overview_and_actors_in_order() -> None:
    f = tvdb_facts(
        {
            "status": {"name": "Ended"},
            "lastAired": "1975-03-28",
            "overview": "Fallback.",
            "translations": {
                "overviewTranslations": [
                    {"language": "deu", "overview": "Deutsch."},
                    {"language": "eng", "overview": "English."},
                ]
            },
            "genres": [{"name": "Horror"}],
            "characters": [
                {"personName": "Simon Oakland", "peopleType": "Actor", "sort": 2},
                {"personName": "Jeff Rice", "peopleType": "Creator", "sort": 0},
                {"personName": "Darren McGavin", "peopleType": "Actor", "sort": 1},
                {"personName": "Darren McGavin", "peopleType": "Actor", "sort": 5},
            ],
        }
    )
    assert f == IdentityFacts(
        end_year=1975,
        overview="English.",
        genres=["Horror"],
        creators=["Jeff Rice"],
        cast=["Darren McGavin", "Simon Oakland"],
    )


def test_tvdb_search_entry_overview_fallback() -> None:
    assert tvdb_facts({"overview": "Plot."}).overview == "Plot."


def test_facts_for_dispatches_and_ignores_unknown_providers() -> None:
    assert facts_for("tmdb", "tv", TMDB_TV) == tmdb_facts(TMDB_TV, "tv")
    assert facts_for("tvmaze", "tv", {"genres": ["A"]}) == IdentityFacts(genres=["A"])
    assert facts_for("musicbrainz", "music", {}) is None
    assert facts_for(None, "movie", {}) is None


def test_malformed_shapes_do_not_crash() -> None:
    weird = {
        "genres": "Horror",
        "created_by": None,
        "aggregate_credits": [],
        "rating": "x",
        "_embedded": "x",
        "characters": [None, 3],
        "translations": None,
        "status": None,
    }
    for provider in ("tmdb", "omdb", "tvmaze", "tvdb"):
        assert isinstance(facts_for(provider, "tv", weird), IdentityFacts)


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan"])
def test_omdb_non_finite_strings_are_absent_not_raised(raw: str) -> None:
    f = omdb_facts({"Year": raw, "imdbRating": raw, "imdbVotes": raw}, "tv")
    assert (f.rating, f.rating_source, f.votes) == (None, None, None)


def test_omdb_infinite_votes_drop_only_the_votes() -> None:
    f = omdb_facts({"imdbVotes": "inf", "imdbRating": "7"}, "tv")
    assert (f.rating, f.rating_source, f.votes) == (7.0, "imdb", None)


def test_helpers_reject_bools_non_numeric_and_container_values() -> None:
    f = omdb_facts({"imdbRating": "abc", "imdbVotes": ["1"]}, "tv")
    assert (f.rating, f.votes) == (None, None)
    movie = tmdb_facts({"vote_average": True, "vote_count": [1]}, "movie")
    assert (movie.rating, movie.votes) == (None, None)


def test_tvmaze_integer_ended_year_is_used_as_is() -> None:
    assert tvmaze_facts({"ended": 1975}).end_year == 1975


def test_tvdb_genres_accept_plain_strings_and_name_dicts() -> None:
    assert tvdb_facts({"genres": ["Horror", "Drama"]}).genres == ["Horror", "Drama"]
    assert tvdb_facts({"genres": [{"name": "Horror"}, "Drama", "Horror", 3]}).genres == ["Horror", "Drama"]


def test_identity_facts_drops_unknown_keys() -> None:
    f = IdentityFacts.model_validate({"overview": "x", "evil": "payload"})
    assert f.overview == "x"
    assert "evil" not in f.model_dump()
