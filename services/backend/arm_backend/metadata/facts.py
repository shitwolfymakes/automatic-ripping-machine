"""Provider payload -> IdentityFacts (match picker spec 3.2).

One pure function per provider: no I/O, never raises on odd shapes. Search
results and the details endpoint both go through `facts_for`, so a row and
its detail pane can't disagree."""

from __future__ import annotations

import math
import re
from html import unescape
from typing import Any, Literal

from arm_common.schemas.job_metadata import IdentityFacts

RatingSource = Literal["imdb", "tmdb", "tvmaze"]

_TAG = re.compile(r"<[^>]+>")
_ENDED = {"ended", "canceled", "cancelled"}
_CAST_LIMIT = 3


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(unescape(_TAG.sub(" ", value)).split())
    return text if text and text != "N/A" else None


def _year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value[:4].isdigit():
        return int(value[:4])
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.replace(",", ""))
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int | None:
    n = _number(value)
    return int(n) if n is not None else None


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _names(items: Any, key: str = "name") -> list[str]:
    out: list[str] = []
    for item in _dicts(items):
        name = item.get(key)
        if isinstance(name, str) and name and name not in out:
            out.append(name)
    return out


def _sort_key(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    return value if isinstance(value, int) else 999


def _csv(value: Any) -> list[str]:
    text = _text(value)
    return [part.strip() for part in text.split(",") if part.strip()] if text else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rating(value: Any, votes: int | None, source: RatingSource) -> tuple[float | None, RatingSource | None]:
    rating = _number(value)
    if rating is None or rating <= 0 or votes == 0:
        return None, None
    return rating, source


def tmdb_facts(payload: dict[str, Any], kind: str) -> IdentityFacts:
    is_tv = kind == "tv"
    status = str(payload.get("status") or "").lower()
    # A show's details carry every season's credits; a search row only the latest.
    credits = _dict(payload.get("aggregate_credits")) if is_tv else {}
    credits = credits or _dict(payload.get("credits"))
    cast = sorted(_dicts(credits.get("cast")), key=lambda c: _sort_key(c, "order"))
    votes = _count(payload.get("vote_count"))
    rating, source = _rating(payload.get("vote_average"), votes, "tmdb")
    if is_tv:
        creators = _names(payload.get("created_by"))
    else:
        creators = _names([c for c in _dicts(credits.get("crew")) if c.get("job") == "Director"])
    return IdentityFacts(
        end_year=_year(payload.get("last_air_date")) if is_tv and status in _ENDED else None,
        overview=_text(payload.get("overview")),
        rating=rating,
        rating_source=source,
        votes=votes if rating is not None else None,
        genres=_names(payload.get("genres")),
        creators=creators,
        cast=_names(cast)[:_CAST_LIMIT],
        episode_count=_count(payload.get("number_of_episodes")) if is_tv else None,
    )


def omdb_facts(payload: dict[str, Any], kind: str) -> IdentityFacts:
    years = re.split(r"[–-]", str(payload.get("Year") or ""))
    votes = _count(None if payload.get("imdbVotes") == "N/A" else payload.get("imdbVotes"))
    rating, source = _rating(None if payload.get("imdbRating") == "N/A" else payload.get("imdbRating"), votes, "imdb")
    return IdentityFacts(
        end_year=_year(years[1]) if len(years) > 1 else None,
        overview=_text(payload.get("Plot")),
        rating=rating,
        rating_source=source,
        votes=votes if rating is not None else None,
        genres=_csv(payload.get("Genre")),
        creators=_csv(payload.get("Director") if kind == "movie" else payload.get("Writer")),
        cast=_csv(payload.get("Actors"))[:_CAST_LIMIT],
    )


def tvmaze_facts(payload: dict[str, Any]) -> IdentityFacts:
    embedded = _dict(payload.get("_embedded"))
    rating, source = _rating(_dict(payload.get("rating")).get("average"), None, "tvmaze")
    genres = (
        [g for g in payload.get("genres") or [] if isinstance(g, str)]
        if isinstance(payload.get("genres"), list)
        else []
    )
    episodes = embedded.get("episodes")
    return IdentityFacts(
        end_year=_year(payload.get("ended")),
        overview=_text(payload.get("summary")),
        rating=rating,
        rating_source=source,
        genres=genres,
        cast=_names([_dict(c.get("person")) for c in _dicts(embedded.get("cast"))])[:_CAST_LIMIT],
        episode_count=len(episodes) if isinstance(episodes, list) else None,
    )


def _tvdb_genres(items: Any) -> list[str]:
    """Search entries list genres as plain strings, detail records as
    {"name": ...} dicts."""
    if not isinstance(items, list):
        return []
    named = [{"name": g} if isinstance(g, str) else g for g in items]
    return _names(named)


def tvdb_facts(payload: dict[str, Any]) -> IdentityFacts:
    status = str(_dict(payload.get("status")).get("name") or "").lower()
    english = next(
        (
            t.get("overview")
            for t in _dicts(_dict(payload.get("translations")).get("overviewTranslations"))
            if t.get("language") == "eng"
        ),
        None,
    )
    people = sorted(_dicts(payload.get("characters")), key=lambda c: _sort_key(c, "sort"))
    return IdentityFacts(
        end_year=_year(payload.get("lastAired")) if status in _ENDED else None,
        overview=_text(english) or _text(payload.get("overview")),
        genres=_tvdb_genres(payload.get("genres")),
        creators=_names([p for p in people if p.get("peopleType") == "Creator"], key="personName"),
        cast=_names([p for p in people if p.get("peopleType") == "Actor"], key="personName")[:_CAST_LIMIT],
    )


def facts_for(provider: str | None, kind: str, payload: dict[str, Any]) -> IdentityFacts | None:
    """The facts a `provider` payload carries, or None for a provider the
    match picker doesn't cover (MusicBrainz, the disc databases)."""
    if provider == "tmdb":
        return tmdb_facts(payload, kind)
    if provider == "omdb":
        return omdb_facts(payload, kind)
    if provider == "tvmaze":
        return tvmaze_facts(payload)
    if provider == "tvdb":
        return tvdb_facts(payload)
    return None
