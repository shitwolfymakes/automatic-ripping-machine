# Match Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the title search's poster grid with a results list plus a detail pane (years, type, rating, cast, plot, genres, creator, episodes), backed by richer provider data, a cached details endpoint, nearest-year sorting, and a resolve path that saves a picked match as a whole identity with a facts snapshot.

**Architecture:** One pure module (`metadata/facts.py`) maps each provider's raw payload to a shared `IdentityFacts` model; search and a new `GET /api/metadata/details` both use it. Resolve gains an optional `match` block that replaces the job's show ids wholesale and records provider, poster and facts. The UI gets a `MatchPicker` (list + pane) inside `TitleSearch`, so the Home review card, the job page and the Identify dialog all use it.

**Tech Stack:** FastAPI + Pydantic v2 (`arm_common` schemas), httpx + respx tests, SvelteKit/Svelte 5 runes, vitest + @testing-library/svelte.

**Spec:** `docs/superpowers/specs/2026-10-16-match-picker-design.md`

## Global Constraints

- Worktree `/home/upb/src/arm-wt-match`, branch `feat/match-picker`, based on `identification/3-review-and-cd` (PR #376). Run every command from the worktree root unless a step says otherwise.
- Commits: `git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit …`. No `Co-Authored-By` line and no "Generated with" footer on commits or the PR.
- Push with `env -u GITHUB_TOKEN git push`; PR calls with `env -u GITHUB_TOKEN gh …`.
- Backend tests are zero infra: `uv run pytest services/backend/tests/<file> -q`. Fake HTTP with `respx`; fake the DB with `tests._fakes.FakeSession`. The Backend keeps 100% statement coverage.
- No Postgres enums, no migration in this change (everything new lives in the `metadata_json` JSON column).
- After any change to a Backend router or an `arm_common` schema: `bash devtools/regen-openapi-snapshot.sh && bash services/ui-neu/scripts/codegen.sh`, and commit both outputs.
- UI gate, run from `services/ui-neu/frontend`, all five must pass: `npm run check`, `npm run lint:styles`, `npm run lint`, `npm run format:check`, `npx vitest run`. Every `:global(...)` selector needs a comment saying why.
- Ruff line length 120. Python 3.14.
- Provider base URLs (from `arm_backend/config.py`): TMDb `https://api.themoviedb.org/3`, OMDb `https://www.omdbapi.com/`, TVDB `https://api4.thetvdb.com/v4`, TVmaze `https://api.tvmaze.com`.
- New image hosts, exact entries: `static.tvmaze.com`, `artworks.thetvdb.com`.
- Year sorts, never filters; the year is never sent upstream.
- Details cache: one hour TTL, 256 entries, oldest evicted, errors not cached.

## Review Focus

1. **Applying a match from a different provider than the job's current identity** (job holds `tmdb=A`, operator picks a TVmaze result for show B): the stored ids must be exactly B's, with `tmdb` cleared, and episode show ids forgotten. Pinned in Task 6.
2. **A result whose details call fails or the provider has no key** (TVDB key removed after search): the pane keeps the row's facts and shows a one-line note; Use this match still works. Pinned in Tasks 4 and 10.
3. **Operator edits the type to the other kind under "Edit before using"** (picked a series, saves as movie): the candidate's ids must not be sent, and resolve must not take the `match` path. Pinned in Task 11.
4. **Rapid clicks across rows** (details for row 1 land after row 2 was picked): the pane must show row 2, and `onselect` must not report row 1's details as the selection. Pinned in Task 10.
5. **Provider payloads with "N/A", HTML, missing or zero values** (OMDb `imdbVotes: "N/A"`, TVmaze `summary: "<p>…</p>"`, TMDb `vote_count: 0`): no crash, absent fields stay empty, zero-vote ratings are hidden. Pinned in Task 2.

---

## File Structure

Backend:
- Modify `packages/arm_common/arm_common/schemas/job_metadata.py`: `IdentityFacts`; `JobIdentity.facts`, `JobIdentity.facts_fetched_at`.
- Modify `packages/arm_common/arm_common/schemas/metadata.py`: `MetadataCandidate.provider`, `MetadataCandidate.facts`.
- Modify `packages/arm_common/arm_common/schemas/jobs.py`: `ResolveMatch`; `ResolveRequest.match`.
- Create `services/backend/arm_backend/metadata/facts.py`: per-provider payload → `IdentityFacts`, no I/O.
- Create `services/backend/arm_backend/metadata/details_cache.py`: small TTL cache.
- Modify `services/backend/arm_backend/metadata/tmdb.py`: `fetch_detail`, `detail_result`; search uses `fetch_detail`.
- Modify `services/backend/arm_backend/metadata/tvmaze.py`: `show_details`.
- Modify `services/backend/arm_backend/metadata/tvdb.py`: `series_details`.
- Modify `services/backend/arm_backend/metadata/sources.py`: `details` capability on four adapters.
- Modify `services/backend/arm_backend/routers/metadata.py`: candidate facts/provider, `year` sort, `/details`.
- Modify `services/backend/arm_backend/routers/images.py`: two hosts.
- Modify `services/backend/arm_backend/routers/jobs.py`: `match` path in `resolve_identity`.
- Tests: `services/backend/tests/test_metadata_facts.py` (new), `test_details_cache.py` (new), `test_metadata_details_router.py` (new), `test_resolve_match.py` (new), plus updates to `test_metadata_clients_full.py`, `test_metadata_search_router.py`, `test_image_proxy_allowlist.py`, `test_metadata_clients_tvmaze.py`, `test_metadata_clients_tvdb.py`.

UI (`services/ui-neu/frontend/src`):
- Modify `lib/api/jobs.ts`: `searchMetadata(…, year)`, `fetchMatchDetails`, `resolveJob` body `match`.
- Create `lib/utils/match.ts` (+ `match.test.ts`).
- Create `lib/components/match/MatchResultRow.svelte`, `MatchDetailPane.svelte`, `MatchPicker.svelte` (+ tests in the same folder).
- Modify `lib/components/TitleSearch.svelte` (+ `TitleSearch.test.ts`), `lib/components/__tests__/IdentifyDialog.test.ts`.

---

### Task 1: Schemas

**Files:**
- Modify: `packages/arm_common/arm_common/schemas/job_metadata.py` (after `ExternalIds`, around line 55; `JobIdentity` around line 56)
- Modify: `packages/arm_common/arm_common/schemas/metadata.py`
- Modify: `packages/arm_common/arm_common/schemas/jobs.py` (`ResolveRequest`, around line 26)
- Modify: `packages/arm_common/arm_common/schemas/__init__.py` (export `IdentityFacts`, `ResolveMatch` alongside the existing exports)
- Test: `services/backend/tests/test_metadata_schema_fields.py`

**Interfaces:**
- Produces: `IdentityFacts` (fields below), `JobIdentity.facts: IdentityFacts | None`, `JobIdentity.facts_fetched_at: datetime | None`, `MetadataCandidate.provider: str | None`, `MetadataCandidate.facts: IdentityFacts | None`, `ResolveMatch(provider, poster_url, poster_is_manual, facts)`, `ResolveRequest.match: ResolveMatch | None`. Import paths: `from arm_common.schemas.job_metadata import IdentityFacts`, `from arm_common.schemas.jobs import ResolveMatch`.

- [ ] **Step 1: Write the failing tests** (append to `services/backend/tests/test_metadata_schema_fields.py`)

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from arm_common.schemas import MetadataCandidate
from arm_common.schemas.job_metadata import IdentityFacts, JobIdentity, JobMetadata
from arm_common.schemas.jobs import ResolveMatch, ResolveRequest


def test_identity_facts_defaults_are_empty() -> None:
    f = IdentityFacts()
    assert f.model_dump() == {
        "end_year": None,
        "overview": None,
        "rating": None,
        "rating_source": None,
        "votes": None,
        "genres": [],
        "creators": [],
        "cast": [],
        "episode_count": None,
    }


def test_identity_facts_rejects_unknown_rating_source() -> None:
    with pytest.raises(ValidationError):
        IdentityFacts(rating=7.0, rating_source="tvdb")


def test_candidate_carries_provider_and_facts() -> None:
    c = MetadataCandidate(title="Kolchak", kind="tv", provider="tmdb", facts=IdentityFacts(cast=["Darren McGavin"]))
    assert c.model_dump()["facts"]["cast"] == ["Darren McGavin"]
    assert MetadataCandidate(title="x", kind="movie").facts is None


def test_job_identity_round_trips_a_facts_snapshot() -> None:
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    md = JobMetadata.model_validate(
        {"identity": {"provider": "tvmaze", "facts": {"genres": ["Horror"]}, "facts_fetched_at": now.isoformat()}}
    )
    assert md.identity is not None and md.identity.facts == IdentityFacts(genres=["Horror"])
    assert md.identity.facts_fetched_at == now
    assert JobIdentity(provider="manual").facts is None


def test_resolve_request_accepts_match_and_forbids_unknown_keys() -> None:
    req = ResolveRequest.model_validate(
        {"title": "K", "match": {"provider": "tvmaze", "poster_url": "https://static.tvmaze.com/a.jpg"}}
    )
    assert req.match == ResolveMatch(provider="tvmaze", poster_url="https://static.tvmaze.com/a.jpg")
    assert req.match.poster_is_manual is False and req.match.facts is None
    with pytest.raises(ValidationError):
        ResolveMatch.model_validate({"provider": "tvmaze", "bogus": 1})
    with pytest.raises(ValidationError):
        ResolveMatch.model_validate({"provider": "imdb"})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_metadata_schema_fields.py -q`
Expected: FAIL with `ImportError: cannot import name 'IdentityFacts'`.

- [ ] **Step 3: Implement**

In `job_metadata.py`, after `class ExternalIds`:

```python
class IdentityFacts(BaseModel):
    """What a person uses to tell titles apart: run, plot, rating, people.
    Filled from a provider payload by `arm_backend.metadata.facts`; shown in
    the match picker and snapshotted on the job when a match is used."""

    model_config = ConfigDict(extra="allow")

    end_year: int | None = None
    overview: str | None = None
    rating: float | None = None  # 0-10
    rating_source: Literal["imdb", "tmdb", "tvmaze"] | None = None
    votes: int | None = None
    genres: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)  # series creators, or a movie's directors
    cast: list[str] = Field(default_factory=list)  # top billed, at most three
    episode_count: int | None = None
```

In `JobIdentity`, after `identified_at`:

```python
    # Snapshot of the picked match's facts (match picker spec 3.6). Not
    # refreshed; a later identify or accept replaces the whole identity.
    facts: IdentityFacts | None = None
    facts_fetched_at: datetime | None = None
```

In `metadata.py`, import `IdentityFacts` next to `ExternalIds` and add to `MetadataCandidate` after `external_ids`:

```python
    # The source that produced this candidate (tmdb/omdb/tvmaze/tvdb), and
    # what it knows about the title (match picker spec 3.1).
    provider: str | None = None
    facts: IdentityFacts | None = None
```

In `schemas/jobs.py`, import `IdentityFacts` from `job_metadata` and add before `ResolveRequest`:

```python
class ResolveMatch(BaseModel):
    """A search result the operator picked (match picker spec 3.6). Its
    presence makes `external_ids` replace the stored show ids wholesale."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["tmdb", "omdb", "tvmaze", "tvdb"]
    poster_url: str | None = None
    # True when the operator edited the poster URL before using the match.
    poster_is_manual: bool = False
    facts: IdentityFacts | None = None
```

Add to `ResolveRequest` after `external_ids`:

```python
    match: ResolveMatch | None = None
```

Add `Literal` to the `typing` import in `schemas/jobs.py` if missing. Export both new names from `arm_common/schemas/__init__.py` the same way `ExternalIds` and `ResolveRequest` are exported.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest services/backend/tests/test_metadata_schema_fields.py services/backend/tests/test_job_metadata_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/arm_common services/backend/tests/test_metadata_schema_fields.py
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(schemas): IdentityFacts on candidates and job identity; resolve match block"
```

---

### Task 2: Facts extraction (`metadata/facts.py`)

**Files:**
- Create: `services/backend/arm_backend/metadata/facts.py`
- Test: `services/backend/tests/test_metadata_facts.py`

**Interfaces:**
- Consumes: `IdentityFacts` (Task 1).
- Produces: `facts_for(provider: str | None, kind: str, payload: dict[str, Any]) -> IdentityFacts | None` (None for providers other than tmdb/omdb/tvmaze/tvdb), and per-provider `tmdb_facts(payload, kind)`, `omdb_facts(payload, kind)`, `tvmaze_facts(payload)`, `tvdb_facts(payload)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Provider payload -> IdentityFacts (match picker spec 3.2). Pure; no I/O."""

import os

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
            "translations": {"overviewTranslations": [{"language": "deu", "overview": "Deutsch."}, {"language": "eng", "overview": "English."}]},
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
    weird = {"genres": "Horror", "created_by": None, "aggregate_credits": [], "rating": "x", "_embedded": "x",
             "characters": [None, 3], "translations": None, "status": None}
    for provider in ("tmdb", "omdb", "tvmaze", "tvdb"):
        assert isinstance(facts_for(provider, "tv", weird), IdentityFacts)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_metadata_facts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'arm_backend.metadata.facts'`.

- [ ] **Step 3: Implement** `services/backend/arm_backend/metadata/facts.py`

```python
"""Provider payload -> IdentityFacts (match picker spec 3.2).

One pure function per provider: no I/O, never raises on odd shapes. Search
results and the details endpoint both go through `facts_for`, so a row and
its detail pane can't disagree."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from arm_common.schemas.job_metadata import IdentityFacts

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
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


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


def _csv(value: Any) -> list[str]:
    text = _text(value)
    return [part.strip() for part in text.split(",") if part.strip()] if text else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rating(value: Any, votes: int | None, source: str) -> tuple[float | None, str | None]:
    rating = _number(value)
    if rating is None or rating <= 0 or votes == 0:
        return None, None
    return rating, source


def tmdb_facts(payload: dict[str, Any], kind: str) -> IdentityFacts:
    is_tv = kind == "tv"
    status = str(payload.get("status") or "").lower()
    credits = _dict(payload.get("aggregate_credits" if is_tv else "credits"))
    cast = sorted(_dicts(credits.get("cast")), key=lambda c: c.get("order") if isinstance(c.get("order"), int) else 999)
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
        rating_source=source,  # type: ignore[arg-type]
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
        rating_source=source,  # type: ignore[arg-type]
        votes=votes if rating is not None else None,
        genres=_csv(payload.get("Genre")),
        creators=_csv(payload.get("Director") if kind == "movie" else payload.get("Writer")),
        cast=_csv(payload.get("Actors"))[:_CAST_LIMIT],
    )


def tvmaze_facts(payload: dict[str, Any]) -> IdentityFacts:
    embedded = _dict(payload.get("_embedded"))
    rating, source = _rating(_dict(payload.get("rating")).get("average"), None, "tvmaze")
    genres = [g for g in payload.get("genres") or [] if isinstance(g, str)] if isinstance(payload.get("genres"), list) else []
    episodes = embedded.get("episodes")
    return IdentityFacts(
        end_year=_year(payload.get("ended")),
        overview=_text(payload.get("summary")),
        rating=rating,
        rating_source=source,  # type: ignore[arg-type]
        genres=genres,
        cast=_names([_dict(c.get("person")) for c in _dicts(embedded.get("cast"))])[:_CAST_LIMIT],
        episode_count=len(episodes) if isinstance(episodes, list) else None,
    )


def tvdb_facts(payload: dict[str, Any]) -> IdentityFacts:
    status = str(_dict(payload.get("status")).get("name") or "").lower()
    english = next(
        (t.get("overview") for t in _dicts(_dict(payload.get("translations")).get("overviewTranslations"))
         if t.get("language") == "eng"),
        None,
    )
    people = sorted(_dicts(payload.get("characters")), key=lambda c: c.get("sort") if isinstance(c.get("sort"), int) else 999)
    return IdentityFacts(
        end_year=_year(payload.get("lastAired")) if status in _ENDED else None,
        overview=_text(english) or _text(payload.get("overview")),
        genres=_names(payload.get("genres")),
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
```

Run `uv run ruff format services/backend/arm_backend/metadata/facts.py services/backend/tests/test_metadata_facts.py` so the long lines wrap at 120.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest services/backend/tests/test_metadata_facts.py -q && uv run mypy services/backend/arm_backend/metadata/facts.py`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/metadata/facts.py services/backend/tests/test_metadata_facts.py
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(metadata): map provider payloads to IdentityFacts"
```

---

### Task 3: TMDb detail call in search

**Files:**
- Modify: `services/backend/arm_backend/metadata/tmdb.py` (`_search_candidates` ~line 99, `get_external_id_map` ~line 128)
- Test: `services/backend/tests/test_metadata_clients_full.py`, `services/backend/tests/test_metadata_search_router.py`

**Interfaces:**
- Produces: `TMDBClient.fetch_detail(tmdb_id, kind) -> dict[str, Any]` (raises `LookupError`/`LookupTimeout`), `TMDBClient.detail_result(tmdb_id, kind) -> MetadataResult` (raises), static `TMDBClient._id_map(body) -> dict[str, str]`. `get_external_id_map` keeps its signature and never-raise contract (the dispatcher still calls it).

- [ ] **Step 1: Write the failing tests** (append to `test_metadata_clients_full.py`; reuse its existing `http_client` fixture and imports, adding `respx`/`httpx` imports if absent)

```python
_TMDB = "https://api.themoviedb.org/3"


@respx.mock
async def test_tmdb_search_candidates_fetch_detail_with_credits(http_client):
    respx.get(f"{_TMDB}/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 5084, "name": "Kolchak", "first_air_date": "1974-09-13"}]})
    )
    detail = respx.get(f"{_TMDB}/tv/5084").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5084,
                "name": "Kolchak",
                "number_of_episodes": 20,
                "external_ids": {"imdb_id": "tt0071003", "tvdb_id": 77170},
                "aggregate_credits": {"cast": [{"name": "Darren McGavin", "order": 0}]},
            },
        )
    )
    external = respx.get(f"{_TMDB}/tv/5084/external_ids")
    [r] = await TMDBClient("k", http_client).search_tv_candidates("kolchak")
    assert detail.calls.last.request.url.params["append_to_response"] == "external_ids,aggregate_credits"
    assert not external.called
    assert r.payload["imdb_id"] == "tt0071003" and r.payload["tvdb_id"] == "77170"
    assert r.payload["number_of_episodes"] == 20
    assert r.payload["aggregate_credits"]["cast"][0]["name"] == "Darren McGavin"


@respx.mock
async def test_tmdb_movie_search_asks_for_credits(http_client):
    respx.get(f"{_TMDB}/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-31"}]})
    )
    detail = respx.get(f"{_TMDB}/movie/603").mock(return_value=httpx.Response(200, json={"id": 603}))
    await TMDBClient("k", http_client).search_movie_candidates("matrix")
    assert detail.calls.last.request.url.params["append_to_response"] == "external_ids,credits"


@respx.mock
async def test_tmdb_search_keeps_a_candidate_whose_detail_fails(http_client):
    respx.get(f"{_TMDB}/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1, "name": "A", "overview": "Plot."}]})
    )
    respx.get(f"{_TMDB}/tv/1").mock(return_value=httpx.Response(500))
    [r] = await TMDBClient("k", http_client).search_tv_candidates("a")
    assert r.payload["imdb_id"] is None and r.payload["overview"] == "Plot."


@respx.mock
async def test_tmdb_detail_result_raises_on_miss_and_maps_ids(http_client):
    respx.get(f"{_TMDB}/tv/404").mock(return_value=httpx.Response(404))
    with pytest.raises(LookupError):
        await TMDBClient("k", http_client).detail_result(404, "tv")
    respx.get(f"{_TMDB}/tv/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "name": "K", "first_air_date": "1974-01-01",
                                               "external_ids": {"imdb_id": "tt1"}})
    )
    r = await TMDBClient("k", http_client).detail_result(5, "tv")
    assert (r.title, r.year, r.kind, r.payload["imdb_id"], r.payload["tvdb_id"]) == ("K", 1974, "tv", "tt1", None)
```

`LookupError` here is `arm_backend.metadata.base.LookupError`; import it as the file already does for other tests.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_metadata_clients_full.py -q -k "fetch_detail or asks_for_credits or detail_fails or detail_result"`
Expected: FAIL (`/tv/5084` not called; `detail_result` missing).

- [ ] **Step 3: Implement** in `tmdb.py`

Add the id extraction as a static method and make `get_external_id_map` use it:

```python
    @staticmethod
    def _id_map(body: dict[str, Any]) -> dict[str, str]:
        """`{"imdb_id", "tvdb_id"}` from a TMDb `external_ids` body, known ones only."""
        out: dict[str, str] = {}
        imdb = body.get("imdb_id")
        if isinstance(imdb, str) and imdb:
            out["imdb_id"] = imdb
        tvdb = body.get("tvdb_id")
        if isinstance(tvdb, int) or (isinstance(tvdb, str) and tvdb):
            out["tvdb_id"] = str(tvdb)
        return out
```

Replace the body of `get_external_id_map` after the `isinstance(body, dict)` guard with `return self._id_map(body)`.

Add:

```python
    async def fetch_detail(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> dict[str, Any]:
        """`/{kind}/{id}` with external ids and credits appended in one call
        (match picker spec 3.3). Raises LookupError/LookupTimeout."""
        credits = "aggregate_credits" if kind == "tv" else "credits"
        try:
            r = await self._http.get(
                f"{_base_url()}/{kind}/{tmdb_id}",
                params={"append_to_response": f"external_ids,{credits}"},
                headers=self._headers,
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout("tmdb timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tmdb transport error: {e}") from e
        if r.status_code == 404:
            raise LookupError("tmdb miss")
        if r.status_code != 200:
            raise LookupError(f"tmdb status={r.status_code}")
        try:
            body = r.json()
        except ValueError as e:
            raise LookupError("tmdb malformed response") from e
        if not isinstance(body, dict):
            raise LookupError("tmdb malformed response")
        return body

    @staticmethod
    def _merge_detail(result: MetadataResult, detail: dict[str, Any]) -> None:
        ids = TMDBClient._id_map(detail.get("external_ids") or {}) if isinstance(detail.get("external_ids"), dict) else {}
        result.payload.update({k: v for k, v in detail.items() if k != "external_ids"})
        result.payload["imdb_id"] = ids.get("imdb_id")
        result.payload["tvdb_id"] = ids.get("tvdb_id")

    async def detail_result(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> MetadataResult:
        """One title's full record as a MetadataResult (details endpoint)."""
        body = await self.fetch_detail(tmdb_id, kind)
        result = self._parse_one(body, kind)
        if result is None:
            raise LookupError("tmdb detail missing title")
        self._merge_detail(result, body)
        return result
```

In `_search_candidates`, replace the enrichment block (from the `# Enrich each candidate` comment to the end of the loop) with:

```python
        # One detail call per candidate (external ids + credits appended):
        # the same call count as the old external_ids fan-out, but it also
        # carries the facts the match picker shows. A failed call keeps the
        # search row with None ids; gather(return_exceptions=True) keeps one
        # failure from failing the batch.
        enrichable = [r for r in out if r.payload.get("id") is not None]
        details = await asyncio.gather(
            *(self.fetch_detail(r.payload["id"], kind) for r in enrichable),
            return_exceptions=True,
        )
        resolved = {id(r): d for r, d in zip(enrichable, details) if isinstance(d, dict)}
        for r in out:
            self._merge_detail(r, resolved.get(id(r), {}))
        return out
```

Make sure `LookupTimeout` is imported from `arm_backend.metadata.base` at the top of `tmdb.py` (add it next to `LookupError` if missing).

- [ ] **Step 4: Update existing tests that mocked `/external_ids` for search**

Run: `uv run pytest services/backend/tests -q -x -k "tmdb or search" 2>&1 | tail -30`

For every failing test whose respx route is `…/{movie|tv}/<id>/external_ids` **and** which exercises search candidates (search router or `search_*_candidates`), change the route to `…/{movie|tv}/<id>` and move the mocked body under `external_ids`, for example `json={"imdb_id": "tt1"}` becomes `json={"id": <id>, "external_ids": {"imdb_id": "tt1"}}`. Leave tests of `get_external_id_map`, `get_external_ids` and the dispatcher unchanged; they still call `/external_ids`. Respx raises `AllMockedAssertionError` for unmocked routes, which identifies each one.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest services/backend/tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/backend/arm_backend/metadata/tmdb.py services/backend/tests
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(tmdb): search fetches each candidate's detail with credits in one call"
```

---

### Task 4: Details capability for TVmaze, TVDB, OMDb and TMDb adapters

**Files:**
- Modify: `services/backend/arm_backend/metadata/tvmaze.py`, `services/backend/arm_backend/metadata/tvdb.py`, `services/backend/arm_backend/metadata/sources.py` (four adapters; add the capability to the Protocol comment list)
- Test: `services/backend/tests/test_metadata_clients_tvmaze.py`, `services/backend/tests/test_metadata_clients_tvdb.py`, `services/backend/tests/test_metadata_sources.py`

**Interfaces:**
- Consumes: `TMDBClient.detail_result` (Task 3), `OMDBClient.lookup_by_imdb_id` (exists).
- Produces: `TVMazeClient.show_details(tvmaze_id: str) -> MetadataResult`, `TVDBClient.series_details(tvdb_id: str) -> MetadataResult`, and on each adapter `async def details(self, cfg, kind: Kind, provider_id: str) -> MetadataResult` (raises `LookupError`/`LookupTimeout`). Capability name: `"details"`.

- [ ] **Step 1: Write the failing tests**

Append to `test_metadata_clients_tvmaze.py`:

```python
@respx.mock
async def test_show_details_embeds_cast_and_episodes(http_client):
    route = respx.get(f"{_BASE}/shows/4607").mock(
        return_value=httpx.Response(200, json={**_SHOW, "_embedded": {"cast": [{"person": {"name": "Matthew Fox"}}], "episodes": [{"id": 1}]}})
    )
    result = await TVMazeClient(http_client).show_details("4607")
    assert route.calls.last.request.url.params.get_list("embed[]") == ["cast", "episodes"]
    assert result.payload["tvmaze_id"] == "4607"
    assert result.payload["_embedded"]["cast"][0]["person"]["name"] == "Matthew Fox"


@respx.mock
async def test_show_details_404_is_a_lookup_error(http_client):
    respx.get(f"{_BASE}/shows/9").mock(return_value=httpx.Response(404))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).show_details("9")
```

Append to `test_metadata_clients_tvdb.py` (reuse its login fixture/pattern; the file already mocks `POST {base}/login`):

```python
@respx.mock
async def test_series_details_reads_extended_with_translations(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json={"data": {"token": "t"}}))
    route = respx.get(f"{_BASE}/series/77170/extended").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": 77170,
                    "name": "Kolchak: The Night Stalker",
                    "year": "1974",
                    "image": "https://artworks.thetvdb.com/banners/posters/77170-1.jpg",
                    "remoteIds": [{"id": "tt0071003", "sourceName": "IMDB"}],
                    "characters": [{"personName": "Darren McGavin", "peopleType": "Actor", "sort": 0}],
                }
            },
        )
    )
    result = await TVDBClient("k", http_client).series_details("77170")
    assert route.calls.last.request.url.params["meta"] == "translations"
    assert "short" not in route.calls.last.request.url.params
    assert (result.title, result.year) == ("Kolchak: The Night Stalker", 1974)
    assert result.payload["tvdb_id"] == "77170" and result.payload["imdb_id"] == "tt0071003"
    assert result.payload["poster_url"].startswith("https://artworks.thetvdb.com/")


@respx.mock
async def test_series_details_malformed_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json={"data": {"token": "t"}}))
    respx.get(f"{_BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(LookupError):
        await TVDBClient("k", http_client).series_details("1")
```

Use the base constant the TVDB test file already defines (if it is named differently than `_BASE`, use that name; its value is `https://api4.thetvdb.com/v4`).

Append to `test_metadata_sources.py`:

```python
import httpx
import pytest
import respx

from arm_backend.metadata.sources import build_online_sources
from arm_common import Config


@respx.mock
async def test_each_title_source_has_a_details_capability():
    respx.get("https://api.themoviedb.org/3/tv/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "name": "K", "external_ids": {}})
    )
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "K", "Year": "1974", "Type": "series", "imdbID": "tt1"})
    )
    respx.get("https://api.tvmaze.com/shows/7").mock(return_value=httpx.Response(200, json={"id": 7, "name": "K"}))
    respx.post("https://api4.thetvdb.com/v4/login").mock(return_value=httpx.Response(200, json={"data": {"token": "t"}}))
    respx.get("https://api4.thetvdb.com/v4/series/9/extended").mock(
        return_value=httpx.Response(200, json={"data": {"id": 9, "name": "K"}})
    )
    cfg = Config(id=1, tmdb_api_key="k", omdb_api_key="k", tvdb_api_key="k")
    async with httpx.AsyncClient() as http:
        sources = build_online_sources(http)
        assert (await sources["tmdb"].details(cfg, "tv", "5")).title == "K"
        assert (await sources["omdb"].details(cfg, "tv", "tt1")).kind == "tv"
        assert (await sources["tvmaze"].details(cfg, "tv", "7")).payload["tvmaze_id"] == "7"
        assert (await sources["tvdb"].details(cfg, "tv", "9")).payload["tvdb_id"] == "9"
```

If `test_metadata_sources.py` already imports some of these names, don't duplicate the imports.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_metadata_clients_tvmaze.py services/backend/tests/test_metadata_clients_tvdb.py services/backend/tests/test_metadata_sources.py -q`
Expected: FAIL with `AttributeError` for `show_details` / `series_details` / `details`.

- [ ] **Step 3: Implement**

In `tvmaze.py`, add to `TVMazeClient`:

```python
    async def show_details(self, tvmaze_id: str) -> MetadataResult:
        """One show with its cast and episode list embedded (details endpoint)."""
        result = show_to_result(await self._get(f"/shows/{tvmaze_id}", {"embed[]": ["cast", "episodes"]}))
        if result is None:
            raise LookupError("tvmaze show missing name")
        return result
```

In `tvdb.py`, add to `TVDBClient`:

```python
    async def series_details(self, tvdb_id: str) -> MetadataResult:
        """`/series/{id}/extended` with translations, characters included
        (no `short`), for the details endpoint."""
        body = await self._get_authed(f"/series/{quote(tvdb_id, safe='')}/extended", {"meta": "translations"})
        data = body.get("data") if isinstance(body, dict) else None
        result = series_to_result(data)
        if result is None or not isinstance(data, dict):
            raise LookupError("tvdb malformed response")
        for remote in data.get("remoteIds") or []:
            if isinstance(remote, dict) and str(remote.get("sourceName", "")).upper() == "IMDB" and remote.get("id"):
                result.payload["imdb_id"] = str(remote["id"])
                break
        return result
```

In `sources.py`, add `#   details(cfg, kind, provider_id) -> MetadataResult` to the capability comment in `OnlineSource`, then add a method to each adapter:

```python
    # TmdbSource
    async def details(self, cfg: Config, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).detail_result(provider_id, kind)

    # OmdbSource
    async def details(self, cfg: Config, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).lookup_by_imdb_id(provider_id)

    # TvmazeSource
    async def details(self, cfg: Config | None, kind: Kind, provider_id: str) -> MetadataResult:
        return await TVMazeClient(self._http).show_details(provider_id)

    # TvdbSource
    async def details(self, cfg: Config | None, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).series_details(provider_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest services/backend/tests -q && uv run mypy services/backend/arm_backend/metadata`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/metadata services/backend/tests
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(metadata): details capability for TMDb, OMDb, TVmaze and TVDB"
```

---

### Task 5: Router: facts on candidates, year sort, details endpoint, image hosts

**Files:**
- Create: `services/backend/arm_backend/metadata/details_cache.py`
- Modify: `services/backend/arm_backend/routers/metadata.py`, `services/backend/arm_backend/routers/images.py` (`_ALLOWED_IMAGE_HOSTS`, line ~34)
- Test: `services/backend/tests/test_details_cache.py` (new), `services/backend/tests/test_metadata_details_router.py` (new), `services/backend/tests/test_metadata_search_router.py`, `services/backend/tests/test_image_proxy_allowlist.py`

**Interfaces:**
- Consumes: `facts_for` (Task 2), `details` capability (Task 4), `MetadataCandidate.provider/facts` (Task 1).
- Produces: `GET /api/metadata/search?…&year=`, `GET /api/metadata/details?provider=&type=&id=` → `MetadataSearchResponse`; `TtlCache(ttl_s=3600.0, max_entries=256, clock=time.monotonic)` with `get(key)`, `put(key, value)`, `clear()`; module-level `metadata_router._details_cache`.

- [ ] **Step 1: Write the failing tests**

`services/backend/tests/test_details_cache.py`:

```python
from arm_backend.metadata.details_cache import TtlCache


def test_get_returns_until_expiry() -> None:
    now = [0.0]
    cache: TtlCache[str, int] = TtlCache(ttl_s=10, max_entries=4, clock=lambda: now[0])
    cache.put("a", 1)
    now[0] = 9.9
    assert cache.get("a") == 1
    now[0] = 10.1
    assert cache.get("a") is None


def test_oldest_entry_is_evicted_at_the_cap() -> None:
    cache: TtlCache[str, int] = TtlCache(ttl_s=100, max_entries=2, clock=lambda: 0.0)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (None, 2, 3)


def test_clear_empties() -> None:
    cache: TtlCache[str, int] = TtlCache()
    cache.put("a", 1)
    cache.clear()
    assert cache.get("a") is None
```

Append to `test_metadata_search_router.py` (uses its `_seed`, `_make_app`, `_auth`, `signing_key`):

```python
@respx.mock
def test_search_candidates_carry_provider_and_facts(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(
            200, json=[{"show": {"id": 1, "name": "Kolchak", "premiered": "1974-09-13", "ended": "1975-03-28",
                                 "rating": {"average": 8}, "genres": ["Horror"]}}]
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "kolchak", "type": "tv", "provider": "tvmaze"}, headers=_auth(token))
    cand = r.json()["candidates"][0]
    assert cand["provider"] == "tvmaze"
    assert cand["facts"]["end_year"] == 1975 and cand["facts"]["rating"] == 8.0 and cand["facts"]["genres"] == ["Horror"]


@respx.mock
def test_search_year_sorts_nearest_first_and_drops_nothing(signing_key: bytes) -> None:
    shows = [
        {"show": {"id": 1, "name": "Night Stalker", "premiered": "2005-09-29"}},
        {"show": {"id": 2, "name": "No Year"}},
        {"show": {"id": 3, "name": "Kolchak", "premiered": "1974-09-13"}},
        {"show": {"id": 4, "name": "The Night Stalker", "premiered": "1972-01-11"}},
        {"show": {"id": 5, "name": "Also 1974", "premiered": "1974-01-01"}},
    ]
    route = respx.get("https://api.tvmaze.com/search/shows").mock(return_value=httpx.Response(200, json=shows))
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "night stalker", "type": "tv", "provider": "tvmaze", "year": 1974},
            headers=_auth(token),
        )
    titles = [c["title"] for c in r.json()["candidates"]]
    assert titles == ["Kolchak", "Also 1974", "The Night Stalker", "Night Stalker", "No Year"]
    assert "year" not in route.calls.last.request.url.params


@respx.mock
def test_search_without_year_keeps_provider_order(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(200, json=[{"show": {"id": 1, "name": "B", "premiered": "2005-01-01"}},
                                               {"show": {"id": 2, "name": "A", "premiered": "1974-01-01"}}])
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "tv", "provider": "tvmaze"}, headers=_auth(token))
    assert [c["title"] for c in r.json()["candidates"]] == ["B", "A"]
```

`services/backend/tests/test_metadata_details_router.py`:

```python
"""GET /api/metadata/details (match picker spec 3.4)."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.metadata.sources import build_online_sources  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402

_TVMAZE_SHOW = {
    "id": 1,
    "name": "Kolchak: The Night Stalker",
    "premiered": "1974-09-13",
    "ended": "1975-03-28",
    "summary": "<p>A reporter.</p>",
    "rating": {"average": 8},
    "externals": {"imdb": "tt0071003", "thetvdb": 77170},
    "image": {"medium": "https://static.tvmaze.com/a.jpg"},
    "_embedded": {"cast": [{"person": {"name": "Darren McGavin"}}], "episodes": [{"id": 1}, {"id": 2}]},
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    metadata_router._details_cache.clear()
    yield
    metadata_router._details_cache.clear()


def _client(**keys: str | None) -> tuple[TestClient, dict[str, str]]:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1, musicbrainz_user_agent="arm/test", **keys)]
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.state.online_sources = build_online_sources(app.state.http)
    app.include_router(metadata_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


@respx.mock
def test_tvmaze_details_return_full_facts() -> None:
    respx.get("https://api.tvmaze.com/shows/1").mock(return_value=httpx.Response(200, json=_TVMAZE_SHOW))
    client, auth = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.status_code == 200, r.text
    [cand] = r.json()["candidates"]
    assert cand["provider"] == "tvmaze"
    assert cand["external_ids"]["tvmaze"] == "1" and cand["external_ids"]["imdb"] == "tt0071003"
    assert cand["facts"]["cast"] == ["Darren McGavin"] and cand["facts"]["episode_count"] == 2
    assert cand["facts"]["overview"] == "A reporter."


@respx.mock
def test_details_are_cached_per_provider_type_and_id() -> None:
    route = respx.get("https://api.tvmaze.com/shows/1").mock(return_value=httpx.Response(200, json=_TVMAZE_SHOW))
    client, auth = _client()
    params = {"provider": "tvmaze", "type": "tv", "id": "1"}
    with client:
        client.get("/api/metadata/details", params=params, headers=auth)
        r = client.get("/api/metadata/details", params=params, headers=auth)
    assert r.json()["candidates"][0]["title"] == "Kolchak: The Night Stalker"
    assert route.call_count == 1


@respx.mock
def test_details_errors_are_reported_and_not_cached() -> None:
    route = respx.get("https://api.tvmaze.com/shows/1").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=_TVMAZE_SHOW)]
    )
    client, auth = _client()
    params = {"provider": "tvmaze", "type": "tv", "id": "1"}
    with client:
        first = client.get("/api/metadata/details", params=params, headers=auth).json()
        second = client.get("/api/metadata/details", params=params, headers=auth).json()
    assert first["candidates"] == [] and "tvmaze" in first["detail"]
    assert len(second["candidates"]) == 1
    assert route.call_count == 2


def test_details_missing_key_is_a_200_with_a_message() -> None:
    client, auth = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvdb", "type": "tv", "id": "9"}, headers=auth)
    assert r.status_code == 200
    assert r.json() == {"candidates": [], "detail": "no tvdb key configured"}


@respx.mock
def test_details_transport_error_is_reported() -> None:
    respx.get("https://api.tvmaze.com/shows/1").mock(side_effect=httpx.ConnectError("boom"))
    client, auth = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.json()["candidates"] == [] and r.json()["detail"]


def test_details_bad_params() -> None:
    client, auth = _client(tmdb_api_key="k")
    with client:
        assert client.get("/api/metadata/details", params={"provider": "imdb", "type": "tv", "id": "1"}, headers=auth).status_code == 422
        assert client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "movie", "id": "1"}, headers=auth).status_code == 400
        assert client.get("/api/metadata/details", params={"provider": "tmdb", "type": "tv"}, headers=auth).status_code == 422


def test_details_requires_auth() -> None:
    client, _ = _client()
    with client:
        assert client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}).status_code == 401
```

Append to `test_image_proxy_allowlist.py`:

```python
def test_tvmaze_and_tvdb_poster_hosts_are_allowed():
    from arm_backend.routers import images

    assert images._host_allowed("static.tvmaze.com")
    assert images._host_allowed("artworks.thetvdb.com")
    assert not images._host_allowed("static.tvmaze.com.evil.example")
    assert not images._host_allowed("evil-artworks.thetvdb.com")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_details_cache.py services/backend/tests/test_metadata_details_router.py services/backend/tests/test_metadata_search_router.py services/backend/tests/test_image_proxy_allowlist.py -q`
Expected: FAIL (`details_cache` missing; no `/details`; no `facts`; hosts not allowed).

- [ ] **Step 3: Implement**

`services/backend/arm_backend/metadata/details_cache.py`:

```python
"""A small in-process TTL cache for match details (match picker spec 3.4)."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TtlCache(Generic[K, V]):
    """Entries expire `ttl_s` after they were put; past `max_entries` the
    oldest put is evicted. Not shared across processes."""

    def __init__(
        self, ttl_s: float = 3600.0, max_entries: int = 256, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_s
        self._max = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, value = entry
        if self._clock() >= expires:
            del self._entries[key]
            return None
        return value

    def put(self, key: K, value: V) -> None:
        self._entries.pop(key, None)
        self._entries[key] = (self._clock() + self._ttl, value)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
```

In `routers/metadata.py`:

1. Imports: `from arm_backend.metadata.details_cache import TtlCache` and `from arm_backend.metadata.facts import facts_for`.
2. In `_to_candidate`, add two keyword arguments to `MetadataCandidate(...)`:

```python
        provider=r.provider,
        facts=facts_for(r.provider, r.kind, payload),
```

3. Add after `_to_candidate`:

```python
def _nearest_year_first(candidates: list[MetadataCandidate], year: int | None) -> list[MetadataCandidate]:
    """Stable sort by distance from `year`; candidates without a year go
    last. Nothing is dropped: a wrong disc year must not hide the title."""
    if year is None:
        return candidates
    return sorted(candidates, key=lambda c: (c.year is None, abs(c.year - year) if c.year is not None else 0))


# (provider, type, id) -> details response; errors are never cached.
_details_cache: TtlCache[tuple[str, str, str], MetadataSearchResponse] = TtlCache()
```

4. In `search_metadata`, add the parameter `year: int | None = None,` after `provider`, and change the final return to:

```python
    candidates = [_to_candidate(r) for r in results]
    return MetadataSearchResponse(candidates=_nearest_year_first(candidates, year))
```

5. Add the endpoint after `search_metadata`:

```python
@router.get("/details", response_model=MetadataSearchResponse)
async def match_details(
    request: Request,
    provider: SearchProvider,
    id: str,
    type: SearchType = "movie",
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    """One title's full record for the match picker's detail pane. `id` is
    the provider's own id (TMDb id, IMDb id for OMDb, TVmaze id, TVDB id)."""
    cfg = await _config(db)
    source = _registry(request).get(provider)
    if source is None or type not in source.media_types:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"{provider} has no {type} details")
    if source.configured(cfg) is not None:
        return MetadataSearchResponse(candidates=[], detail=f"no {provider} key configured")
    key = (provider, type, id)
    cached = _details_cache.get(key)
    if cached is not None:
        return cached
    fetch = capability(source, "details")
    if fetch is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"{provider} has no details")
    try:
        result = await fetch(cfg, type, id)
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{provider}: {exc}")
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{provider} unavailable: {exc}")
    result.provider = source.id
    response = MetadataSearchResponse(candidates=[_to_candidate(result)])
    _details_cache.put(key, response)
    return response
```

The `fetch is None` branch is unreachable with today's four adapters; mark it `# pragma: no cover` only if the coverage gate flags it (check the repo for existing `pragma: no cover` usage first and follow it). Otherwise cover it with a test that registers a stub source lacking `details` in `app.state.online_sources`.

In `routers/images.py`, add to `_ALLOWED_IMAGE_HOSTS`:

```python
    "static.tvmaze.com",  # TVmaze posters (checked 2026-10-16: direct 200, no redirect)
    "artworks.thetvdb.com",  # TVDB posters (checked 2026-10-16: direct 200, no redirect)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest services/backend/tests -q && uv run mypy services/backend/arm_backend`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend services/backend/tests
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(metadata): facts on search results, nearest-year sort, cached details endpoint; allow TVmaze and TVDB posters"
```

---

### Task 6: Resolve saves a picked match as a whole identity

**Files:**
- Modify: `services/backend/arm_backend/routers/jobs.py` (`resolve_identity` ~line 1213; the `if req.external_ids is not None:` block ~line 1244; after `job.year = req.year` ~line 1287)
- Test: `services/backend/tests/test_resolve_match.py` (new)

**Interfaces:**
- Consumes: `ResolveMatch`, `IdentityFacts`, `JobIdentity.facts/facts_fetched_at` (Task 1).
- Produces: `_apply_match(md: JobMetadata, req: ResolveRequest, now: datetime) -> bool` (returns show_changed). Request contract used by the UI (Task 11): `{"title", "year", "media_type", "external_ids": {imdb, tmdb, tmdb_kind, tvdb, tvmaze}, "match": {provider, poster_url, poster_is_manual, facts}}`.

- [ ] **Step 1: Write the failing tests** `services/backend/tests/test_resolve_match.py`

Reuse helpers from `test_jobs_router.py` by importing them:

```python
"""POST /api/jobs/{id}/resolve with a `match` block (match picker spec 3.6)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from arm_common import JobStatus
from tests._fakes import FakeSession
from tests.test_jobs_router import _StageRunner, _auth, _job, _make_app, signing_key  # noqa: F401

_FACTS = {"genres": ["Horror"], "cast": ["Darren McGavin"], "overview": "A reporter.", "episode_count": 20}


def _identified(ids: dict[str, str]) -> object:
    job = _job(status=JobStatus.IDENTIFIED, meta={"identity": {"provider": "tmdb", "external_ids": ids}})
    job.poster_url = "https://image.tmdb.org/old.jpg"
    job.poster_url_manual = "https://image.tmdb.org/manual-old.jpg"
    return job


def _post(signing_key: bytes, job: object, body: dict) -> tuple[dict, _StageRunner, FakeSession]:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [job]
    runner = _StageRunner()
    app.state.episode_stage = runner
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/resolve", json=body, headers=_auth(token))  # type: ignore[attr-defined]
    assert r.status_code == 200, r.text
    return r.json()["job"], runner, db


def _match_body(**match: object) -> dict:
    return {
        "title": "Kolchak: The Night Stalker",
        "year": 1974,
        "media_type": "tv",
        "external_ids": {"imdb": "tt0071003", "tmdb": None, "tmdb_kind": None, "tvdb": "77170", "tvmaze": "1"},
        "match": {"provider": "tvmaze", "poster_url": "https://static.tvmaze.com/k.jpg", "facts": _FACTS, **match},
    }


def test_match_replaces_ids_wholesale_and_clears_a_stale_tmdb(signing_key: bytes) -> None:
    job = _identified({"tmdb": "999", "tmdb_kind": "tv", "imdb": "tt9", "musicbrainz_release": "mb1"})
    out, runner, _ = _post(signing_key, job, _match_body())
    ids = out["metadata_json"]["identity"]["external_ids"]
    assert ids["imdb"] == "tt0071003" and ids["tvdb"] == "77170" and ids["tvmaze"] == "1"
    assert ids.get("tmdb") is None and ids.get("tmdb_kind") is None
    assert ids["musicbrainz_release"] == "mb1"  # not a show id; kept
    assert runner.scheduled == [job.id]


def test_match_records_provider_overview_facts_and_time(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({"tmdb": "999"}), _match_body())
    identity = out["metadata_json"]["identity"]
    assert identity["provider"] == "tvmaze"
    assert identity["overview"] == "A reporter."
    assert identity["facts"]["cast"] == ["Darren McGavin"] and identity["facts"]["episode_count"] == 20
    assert identity["facts_fetched_at"] and identity["identified_at"]


def test_match_poster_goes_to_poster_url_and_clears_manual(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({"tmdb": "999"}), _match_body())
    assert out["poster_url"] == "https://static.tvmaze.com/k.jpg"
    assert out["poster_url_manual"] is None


def test_match_with_edited_poster_saves_it_as_manual(signing_key: bytes) -> None:
    out, _, _ = _post(
        signing_key, _identified({"tmdb": "999"}), _match_body(poster_url="https://x.example/p.jpg", poster_is_manual=True)
    )
    assert out["poster_url_manual"] == "https://x.example/p.jpg"
    assert out["poster_url"] == "https://image.tmdb.org/old.jpg"


def test_match_without_facts_leaves_snapshot_empty(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({}), _match_body(facts=None))
    identity = out["metadata_json"]["identity"]
    assert identity.get("facts") is None and identity.get("facts_fetched_at") is None


def test_match_show_change_forgets_episode_show_ids(signing_key: bytes, monkeypatch) -> None:
    from arm_backend.routers import jobs as jobs_router

    forgotten: list[str] = []
    monkeypatch.setattr(jobs_router, "forget_episode_show_ids", lambda job: forgotten.append(job.id))
    job = _identified({"tmdb": "999", "tmdb_kind": "tv"})
    _post(signing_key, job, _match_body())
    assert forgotten == [job.id]


def test_same_show_match_does_not_forget_episode_ids(signing_key: bytes, monkeypatch) -> None:
    from arm_backend.routers import jobs as jobs_router

    forgotten: list[str] = []
    monkeypatch.setattr(jobs_router, "forget_episode_show_ids", lambda job: forgotten.append(job.id))
    job = _identified({"imdb": "tt0071003", "tvdb": "77170", "tvmaze": "1"})
    _post(signing_key, job, _match_body())
    assert forgotten == []


def test_match_on_a_job_with_no_identity(signing_key: bytes) -> None:
    job = _job(status=JobStatus.AWAITING_REVIEW, meta={})
    out, _, _ = _post(signing_key, job, _match_body())
    assert out["metadata_json"]["identity"]["external_ids"]["tvmaze"] == "1"


def test_resolve_without_match_still_merges(signing_key: bytes) -> None:
    job = _identified({"tmdb": "999", "tmdb_kind": "tv"})
    out, _, _ = _post(signing_key, job, {"title": "X", "external_ids": {"tvdb": "5"}})
    ids = out["metadata_json"]["identity"]["external_ids"]
    assert ids["tmdb"] == "999" and ids["tvdb"] == "5"
    assert out["metadata_json"]["identity"]["provider"] == "tmdb"
    assert out["poster_url_manual"] == "https://image.tmdb.org/manual-old.jpg"
```

Check `_job`'s signature in `test_jobs_router.py` (line ~120) accepts `status=` and `meta=` as used by `_kind_job`; it does. If `forget_episode_show_ids` is imported into `routers/jobs.py` by name (line 26), the monkeypatch on `jobs_router.forget_episode_show_ids` works as written. If importing `signing_key` from `test_jobs_router` does not register the fixture, copy the fixture into this file instead:

```python
import secrets
import pytest

@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/backend/tests/test_resolve_match.py -q`
Expected: FAIL (tvmaze not saved, provider unchanged, poster untouched).

- [ ] **Step 3: Implement** in `routers/jobs.py`

Add near `_SHOW_ID_FIELDS`:

```python
# Ids a picked match states; the rest (musicbrainz_release, anidb) are kept.
_MATCH_ID_FIELDS: tuple[str, ...] = ("imdb", "tmdb", "tmdb_kind", "tvdb", "tvmaze")


def _apply_match(md: JobMetadata, req: ResolveRequest, now: datetime) -> bool:
    """A picked search result states the whole show (match picker spec 3.6):
    its ids replace the stored show ids wholesale, tvmaze included, and the
    identity records the provider and a facts snapshot. Returns whether a
    stored show id changed or was cleared (a show change)."""
    assert req.match is not None
    sent = req.external_ids or ExternalIds()
    old = md.identity.external_ids if md.identity is not None else ExternalIds()
    show_changed = any(
        getattr(old, name) is not None and getattr(old, name) != getattr(sent, name)
        for name in ("imdb", "tmdb", "tvdb", "tvmaze")
    )
    ids = old.model_copy()
    for name in _MATCH_ID_FIELDS:
        setattr(ids, name, getattr(sent, name))
    facts = req.match.facts
    md.identity = JobIdentity(
        provider=req.match.provider,
        external_ids=ids,
        overview=facts.overview if facts is not None else None,
        identified_at=now,
        facts=facts,
        facts_fetched_at=now if facts is not None else None,
    )
    return show_changed
```

Import `ExternalIds` and `JobIdentity` from `arm_common.schemas.job_metadata` if not already imported in this module (`JobIdentity` already is; check `ExternalIds`).

In `resolve_identity`, change `if req.external_ids is not None:` (the id merge block) to:

```python
    if req.match is not None:
        show_changed = _apply_match(md, req, datetime.now(timezone.utc))
    elif req.external_ids is not None:
```

Leave the body of the existing branch unchanged.

After `job.year = req.year`, add:

```python
    if req.match is not None:
        # A picked match's poster is the automatic one; an operator-edited
        # URL stays a manual override (match picker spec 3.6).
        if req.match.poster_is_manual:
            job.poster_url_manual = req.match.poster_url
        else:
            job.poster_url = req.match.poster_url
            job.poster_url_manual = None
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest services/backend/tests -q && uv run mypy services/backend/arm_backend`
Expected: PASS, including the existing resolve tests in `test_jobs_router.py`, `test_resolve_fanout.py`, `test_resolve_disc_fields.py`.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/routers/jobs.py services/backend/tests/test_resolve_match.py
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(resolve): a picked match replaces the show ids and saves provider, poster and facts"
```

---

### Task 7: Wire contract and UI API helpers

**Files:**
- Modify: `services/ui-neu/openapi.snapshot.json`, `services/ui-neu/frontend/src/lib/types/api.gen.ts` (generated)
- Modify: `services/ui-neu/frontend/src/lib/api/jobs.ts` (`searchMetadata` ~line 197, `resolveJob` ~line 145; add `fetchMatchDetails`)
- Test: `services/ui-neu/frontend/src/lib/api/jobs.test.ts` (create if absent; if a jobs API test exists under another name, e.g. `lib/api/__tests__/jobs.test.ts`, add there)

**Interfaces:**
- Produces: `searchMetadata(query, type?, provider?, year?: number | null)`, `fetchMatchDetails(provider: MatchProvider, type: 'movie' | 'tv', id: string): Promise<MetadataSearchResponse>`, `export type MatchProvider = 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb'`, `resolveJob(jobId, body)` where body accepts `external_ids?: ExternalIds` and `match?: ResolveMatch`. Generated types used later: `IdentityFacts`, `MetadataCandidate` (with `provider`, `facts`), `ResolveMatch`, `ExternalIds`.

- [ ] **Step 1: Regenerate the contract**

Run: `bash devtools/regen-openapi-snapshot.sh && bash services/ui-neu/scripts/codegen.sh`
Then: `grep -n "IdentityFacts\|ResolveMatch\|/api/metadata/details" services/ui-neu/frontend/src/lib/types/api.gen.ts | head`
Expected: all three names present.

- [ ] **Step 2: Write the failing test**

Look at how existing API tests mock `apiFetch` (search `vi.mock('$lib/api/client'` or similar under `src/lib/api`) and follow that pattern. The test:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({ apiFetch: vi.fn(() => Promise.resolve({ candidates: [] })) }));

import { apiFetch } from '$lib/api/client';
import { fetchMatchDetails, searchMetadata } from './jobs';

describe('match picker API helpers', () => {
	beforeEach(() => vi.mocked(apiFetch).mockClear());

	it('searchMetadata sends the year when given', async () => {
		await searchMetadata('kolchak', 'tv', 'tmdb', 1974);
		expect(vi.mocked(apiFetch).mock.calls[0][0]).toBe(
			'/api/metadata/search?title=kolchak&type=tv&provider=tmdb&year=1974'
		);
	});

	it('searchMetadata omits a missing year', async () => {
		await searchMetadata('kolchak', 'tv', undefined, null);
		expect(vi.mocked(apiFetch).mock.calls[0][0]).toBe('/api/metadata/search?title=kolchak&type=tv');
	});

	it('fetchMatchDetails builds the details URL', async () => {
		await fetchMatchDetails('tvmaze', 'tv', '1');
		expect(vi.mocked(apiFetch).mock.calls[0][0]).toBe('/api/metadata/details?provider=tvmaze&type=tv&id=1');
	});
});
```

Use the real module path of `apiFetch` (check the import at the top of `jobs.ts`).

- [ ] **Step 3: Run to verify failure**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/api/jobs.test.ts`
Expected: FAIL (`fetchMatchDetails` is not exported; year not sent).

- [ ] **Step 4: Implement** in `jobs.ts`

```ts
export type MatchProvider = 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb';

export function searchMetadata(
	query: string,
	type?: 'movie' | 'tv',
	provider?: MatchProvider,
	year?: number | null
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ title: query });
	if (type) params.set('type', type);
	if (provider) params.set('provider', provider);
	if (year != null) params.set('year', String(year));
	return apiFetch<MetadataSearchResponse>(`/api/metadata/search?${params}`);
}

// One title's full record for the match picker's detail pane (cached server side).
export function fetchMatchDetails(
	provider: MatchProvider,
	type: 'movie' | 'tv',
	id: string
): Promise<MetadataSearchResponse> {
	const params = new URLSearchParams({ provider, type, id });
	return apiFetch<MetadataSearchResponse>(`/api/metadata/details?${params}`);
}
```

In `resolveJob`'s body type, add `match?: ResolveMatch;` (import `ResolveMatch` from `$lib/types/api.gen`) and make sure `external_ids?: ExternalIds;` is present. Update the comment above `resolveJob` to list `external_ids` and `match`.

- [ ] **Step 5: Run to verify pass**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/api && npm run check`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts services/ui-neu/frontend/src/lib/api
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(ui-api): regenerate contract; details fetch, search year and resolve match"
```

---

### Task 8: `lib/utils/match.ts`

**Files:**
- Create: `services/ui-neu/frontend/src/lib/utils/match.ts`
- Test: `services/ui-neu/frontend/src/lib/utils/match.test.ts`

**Interfaces:**
- Produces: `isSeriesKind(kind: string): boolean`, `formatYears(year, endYear, kind): string`, `kindLabel(kind): string`, `formatVotes(n): string`, `detailsId(c: MetadataCandidate): string | null`, `candidateKey(c): string`, `mergeCandidate(row, detail): MetadataCandidate`, `RATING_LABEL: Record<string, string>`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import type { MetadataCandidate } from '$lib/types/api.gen';
import {
	candidateKey,
	detailsId,
	formatVotes,
	formatYears,
	isSeriesKind,
	kindLabel,
	mergeCandidate
} from './match';

const cand = (o: Partial<MetadataCandidate> = {}): MetadataCandidate => ({ title: 'K', kind: 'tv', ...o });

describe('match utils', () => {
	it('isSeriesKind', () => {
		expect([isSeriesKind('tv'), isSeriesKind('series'), isSeriesKind('movie')]).toEqual([true, true, false]);
	});

	it('formatYears', () => {
		expect(formatYears(1974, 1975, 'tv')).toBe('1974–1975');
		expect(formatYears(1974, 1974, 'tv')).toBe('1974');
		expect(formatYears(2005, null, 'tv')).toBe('2005');
		expect(formatYears(1972, 1999, 'movie')).toBe('1972');
		expect(formatYears(null, 1975, 'tv')).toBe('');
	});

	it('kindLabel', () => {
		expect(kindLabel('tv')).toBe('TV Series');
		expect(kindLabel('series')).toBe('TV Series');
		expect(kindLabel('movie')).toBe('Movie');
	});

	it('formatVotes', () => {
		expect(formatVotes(1)).toBe('1 vote');
		expect(formatVotes(950)).toBe('950 votes');
		expect(formatVotes(9812)).toBe('9.8K votes');
		expect(formatVotes(12000)).toBe('12K votes');
		expect(formatVotes(1_250_000)).toBe('1.3M votes');
	});

	it('detailsId picks the provider-native id', () => {
		const ids = { imdb: 'tt1', tmdb: '5', tvdb: '9', tvmaze: '7' };
		expect(detailsId(cand({ provider: 'tmdb', external_ids: ids }))).toBe('5');
		expect(detailsId(cand({ provider: 'omdb', external_ids: ids }))).toBe('tt1');
		expect(detailsId(cand({ provider: 'omdb', provider_id: 'tt2' }))).toBe('tt2');
		expect(detailsId(cand({ provider: 'tvmaze', external_ids: ids }))).toBe('7');
		expect(detailsId(cand({ provider: 'tvdb', external_ids: ids }))).toBe('9');
		expect(detailsId(cand({ provider: null, external_ids: ids }))).toBeNull();
		expect(detailsId(cand({ provider: 'tvdb' }))).toBeNull();
	});

	it('candidateKey is stable per provider and id', () => {
		expect(candidateKey(cand({ provider: 'tvmaze', external_ids: { tvmaze: '7' } }))).toBe('tvmaze:7');
		expect(candidateKey(cand({ provider: null, title: 'X', year: 1999 }))).toBe(':X:1999');
	});

	it('mergeCandidate prefers detail values and keeps row values the detail lacks', () => {
		const row = cand({
			poster_url: 'row.jpg',
			external_ids: { imdb: 'tt1', tvmaze: '7' },
			facts: { genres: ['Horror'], cast: [], creators: [], rating: 8, rating_source: 'tvmaze' }
		});
		const detail = cand({
			poster_url: null,
			external_ids: { imdb: null, tvdb: '9' },
			facts: { genres: [], cast: ['Darren McGavin'], creators: [], episode_count: 20 }
		});
		const m = mergeCandidate(row, detail);
		expect(m.poster_url).toBe('row.jpg');
		expect(m.external_ids).toMatchObject({ imdb: 'tt1', tvmaze: '7', tvdb: '9' });
		expect(m.facts).toMatchObject({
			genres: ['Horror'],
			cast: ['Darren McGavin'],
			rating: 8,
			rating_source: 'tvmaze',
			episode_count: 20
		});
	});
});
```

If the generated `IdentityFacts` type requires every field, build facts objects with a small local `facts(...)` helper that fills defaults instead of literal partial objects.

- [ ] **Step 2: Run to verify failure**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/utils/match.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `src/lib/utils/match.ts`

```ts
// Display and merge helpers for the match picker (match picker spec 4.1).
import type { ExternalIds, IdentityFacts, MetadataCandidate } from '$lib/types/api.gen';

export const RATING_LABEL: Record<string, string> = { imdb: 'IMDb', tmdb: 'TMDb', tvmaze: 'TVmaze' };

export function isSeriesKind(kind: string): boolean {
	return kind === 'tv' || kind === 'series';
}

/** "1974–1975" for a finished run; the start year alone otherwise (a running
 * show and an unknown end look the same). */
export function formatYears(year: number | null | undefined, endYear: number | null | undefined, kind: string): string {
	if (year == null) return '';
	if (isSeriesKind(kind) && endYear != null && endYear !== year) return `${year}–${endYear}`;
	return String(year);
}

export function kindLabel(kind: string): string {
	return isSeriesKind(kind) ? 'TV Series' : 'Movie';
}

export function formatVotes(n: number): string {
	if (n >= 1_000_000) return `${trim(n / 1_000_000)}M votes`;
	if (n >= 1000) return `${trim(n / 1000)}K votes`;
	return `${n} ${n === 1 ? 'vote' : 'votes'}`;
}

function trim(x: number): string {
	return x >= 10 ? String(Math.round(x)) : x.toFixed(1).replace(/\.0$/, '');
}

/** The provider's own id, which GET /api/metadata/details takes. */
export function detailsId(c: MetadataCandidate): string | null {
	const ids = c.external_ids ?? {};
	switch (c.provider) {
		case 'tmdb':
			return ids.tmdb ?? null;
		case 'omdb':
			return ids.imdb ?? c.provider_id ?? null;
		case 'tvmaze':
			return ids.tvmaze ?? null;
		case 'tvdb':
			return ids.tvdb ?? null;
		default:
			return null;
	}
}

export function candidateKey(c: MetadataCandidate): string {
	const id = detailsId(c);
	return id ? `${c.provider}:${id}` : `${c.provider ?? ''}:${c.title}:${c.year ?? ''}`;
}

function present<T extends object>(o: T | null | undefined): Partial<T> {
	return Object.fromEntries(
		Object.entries(o ?? {}).filter(([, v]) => v != null && !(Array.isArray(v) && v.length === 0))
	) as Partial<T>;
}

/** A row with its fetched details laid over it: detail values win, row
 * values the detail lacks stay. */
export function mergeCandidate(row: MetadataCandidate, detail: MetadataCandidate): MetadataCandidate {
	return {
		...row,
		...present(detail),
		external_ids: { ...(row.external_ids ?? {}), ...present<ExternalIds>(detail.external_ids) },
		facts: { ...(row.facts ?? {}), ...present<IdentityFacts>(detail.facts) } as IdentityFacts
	};
}
```

- [ ] **Step 4: Run to verify pass**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/utils/match.test.ts && npm run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/utils/match.ts services/ui-neu/frontend/src/lib/utils/match.test.ts
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(ui): match picker display and merge helpers"
```

---

### Task 9: `MatchResultRow` and `MatchDetailPane`

**Files:**
- Create: `services/ui-neu/frontend/src/lib/components/match/MatchResultRow.svelte`, `MatchDetailPane.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/match/MatchResultRow.test.ts`, `MatchDetailPane.test.ts`

**Interfaces:**
- Consumes: Task 8 helpers; `PosterImage` (`$lib/components/PosterImage.svelte`, props `url`, `alt`, `class`).
- Produces: `MatchResultRow` props `{ candidate: MetadataCandidate; selected: boolean; onselect: () => void }`. `MatchDetailPane` props `{ candidate; loading: boolean; error: string | null; canUse: boolean; useLabel: string; applying: boolean; onuse: () => void; children?: Snippet }`; the Use button's accessible name is `useLabel` (or "Applying..." while applying); the IMDb link's name is "Open on IMDb ↗"; skeleton element has `data-testid="match-pane-skeleton"`.

- [ ] **Step 1: Write the failing tests**

`MatchResultRow.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import MatchResultRow from './MatchResultRow.svelte';

const kolchak = {
	title: 'Kolchak: The Night Stalker',
	year: 1974,
	kind: 'tv',
	provider: 'tmdb',
	poster_url: 'https://image.tmdb.org/k.jpg',
	facts: { end_year: 1975, rating: 7.9, cast: ['Darren McGavin', 'Simon Oakland', 'Jack Grinnage'], genres: [], creators: [] }
};

describe('MatchResultRow', () => {
	afterEach(cleanup);

	it('shows title, years and type, two cast names and the rating', () => {
		renderComponent(MatchResultRow, { props: { candidate: kolchak, selected: false, onselect: vi.fn() } });
		expect(screen.getByText('Kolchak: The Night Stalker')).toBeInTheDocument();
		expect(screen.getByText('1974–1975 · TV Series')).toBeInTheDocument();
		expect(screen.getByText('Darren McGavin, Simon Oakland')).toBeInTheDocument();
		expect(screen.getByText('★ 7.9')).toBeInTheDocument();
	});

	it('omits cast and rating when absent', () => {
		renderComponent(MatchResultRow, {
			props: { candidate: { title: 'X', year: 1972, kind: 'movie', facts: null }, selected: false, onselect: vi.fn() }
		});
		expect(screen.getByText('1972 · Movie')).toBeInTheDocument();
		expect(screen.queryByText(/★/)).toBeNull();
	});

	it('reports selection and click', async () => {
		const onselect = vi.fn();
		renderComponent(MatchResultRow, { props: { candidate: kolchak, selected: true, onselect } });
		const row = screen.getByRole('button', { name: /Kolchak/ });
		expect(row).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(row);
		expect(onselect).toHaveBeenCalledOnce();
	});
});
```

`MatchDetailPane.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import MatchDetailPane from './MatchDetailPane.svelte';

const full = {
	title: 'Kolchak: The Night Stalker',
	year: 1974,
	kind: 'tv',
	provider: 'omdb',
	external_ids: { imdb: 'tt0071003' },
	facts: {
		end_year: 1975,
		episode_count: 20,
		rating: 7.9,
		rating_source: 'imdb',
		votes: 9812,
		overview: 'A reporter investigates.',
		genres: ['Horror', 'Mystery'],
		creators: ['Jeff Rice'],
		cast: ['Darren McGavin', 'Simon Oakland']
	}
};
const base = { loading: false, error: null, canUse: true, useLabel: 'Use this match', applying: false };

describe('MatchDetailPane', () => {
	afterEach(cleanup);

	it('shows the full record', () => {
		renderComponent(MatchDetailPane, { props: { ...base, candidate: full, onuse: vi.fn() } });
		expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
		expect(screen.getByText('1974–1975 · TV Series · 20 episodes')).toBeInTheDocument();
		expect(screen.getByText('IMDb')).toBeInTheDocument();
		expect(screen.getByText('★ 7.9')).toBeInTheDocument();
		expect(screen.getByText('9.8K votes')).toBeInTheDocument();
		expect(screen.getByText('tt0071003')).toBeInTheDocument();
		expect(screen.getByText('A reporter investigates.')).toBeInTheDocument();
		expect(screen.getByText('Horror, Mystery')).toBeInTheDocument();
		expect(screen.getByText('Creator')).toBeInTheDocument();
		expect(screen.getByText('Jeff Rice')).toBeInTheDocument();
		expect(screen.getByText('Darren McGavin, Simon Oakland')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Open on IMDb ↗' })).toHaveAttribute(
			'href',
			'https://www.imdb.com/title/tt0071003/'
		);
		expect(screen.queryByTestId('match-pane-skeleton')).toBeNull();
	});

	it('labels a movie director as Director and hides the IMDb link without an id', () => {
		renderComponent(MatchDetailPane, {
			props: { ...base, candidate: { title: 'M', year: 1972, kind: 'movie', facts: { creators: ['D'], genres: [], cast: [] } }, onuse: vi.fn() }
		});
		expect(screen.getByText('Director')).toBeInTheDocument();
		expect(screen.queryByRole('link', { name: 'Open on IMDb ↗' })).toBeNull();
	});

	it('shows a skeleton while loading and the error note on failure', async () => {
		const { rerender } = renderComponent(MatchDetailPane, {
			props: { ...base, loading: true, candidate: { title: 'X', kind: 'tv' }, onuse: vi.fn() }
		});
		expect(screen.getByTestId('match-pane-skeleton')).toBeInTheDocument();
		await rerender({ ...base, loading: false, error: 'tvdb: miss', candidate: { title: 'X', kind: 'tv' }, onuse: vi.fn() });
		expect(screen.queryByTestId('match-pane-skeleton')).toBeNull();
		expect(screen.getByText('tvdb: miss')).toBeInTheDocument();
	});

	it('Use calls onuse; hidden when not allowed; disabled while applying', async () => {
		const onuse = vi.fn();
		const { rerender } = renderComponent(MatchDetailPane, { props: { ...base, candidate: full, onuse } });
		await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
		expect(onuse).toHaveBeenCalledOnce();
		await rerender({ ...base, applying: true, candidate: full, onuse });
		expect(screen.getByRole('button', { name: 'Applying...' })).toBeDisabled();
		await rerender({ ...base, canUse: false, candidate: full, onuse });
		expect(screen.queryByRole('button', { name: 'Use this match' })).toBeNull();
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/match`
Expected: FAIL (components missing).

- [ ] **Step 3: Implement**

`MatchResultRow.svelte`:

```svelte
<script lang="ts">
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { formatYears, kindLabel } from '$lib/utils/match';

	interface Props {
		candidate: MetadataCandidate;
		selected: boolean;
		onselect: () => void;
	}

	let { candidate, selected, onselect }: Props = $props();

	let sub = $derived(
		[formatYears(candidate.year, candidate.facts?.end_year, candidate.kind), kindLabel(candidate.kind)]
			.filter(Boolean)
			.join(' · ')
	);
	let cast = $derived((candidate.facts?.cast ?? []).slice(0, 2).join(', '));
	let rating = $derived(candidate.facts?.rating ?? null);
</script>

<button type="button" class="match-row" aria-pressed={selected} onclick={onselect}>
	{#if candidate.poster_url}
		<PosterImage url={candidate.poster_url} alt="" class="match-row-thumb" />
	{:else}
		<span class="match-row-thumb match-row-thumb-empty" aria-hidden="true"></span>
	{/if}
	<span class="match-row-text">
		<span class="match-row-title">{candidate.title}</span>
		<span class="match-row-sub">{sub}</span>
		{#if cast}<span class="match-row-cast">{cast}</span>{/if}
	</span>
	{#if rating != null}<span class="match-row-rating">★ {rating.toFixed(1)}</span>{/if}
</button>

<style>
	.match-row {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 0.75rem;
		border: 1px solid transparent;
		border-radius: var(--radius-md);
		padding: 0.5rem;
		text-align: left;
		transition: border-color var(--motion-fast) var(--ease);
	}
	.match-row:hover {
		border-color: var(--color-border-strong);
	}
	.match-row[aria-pressed='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-1);
	}
	/* :global: also passed as PosterImage's class prop, landing on its own <img> */
	:global(.match-row-thumb) {
		width: 2.25rem;
		height: 3.25rem;
		flex: none;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.match-row-thumb-empty {
		background: var(--color-primary-tint-2);
	}
	.match-row-text {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
	}
	.match-row-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.match-row-sub,
	.match-row-cast {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.match-row-cast {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.match-row-rating {
		flex: none;
		font-size: 0.8125rem;
		color: var(--color-text);
	}
</style>
```

`MatchDetailPane.svelte`:

```svelte
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { formatVotes, formatYears, isSeriesKind, kindLabel, RATING_LABEL } from '$lib/utils/match';

	interface Props {
		candidate: MetadataCandidate;
		loading: boolean;
		error: string | null;
		canUse: boolean;
		useLabel: string;
		applying: boolean;
		onuse: () => void;
		children?: Snippet;
	}

	let { candidate, loading, error, canUse, useLabel, applying, onuse, children }: Props = $props();

	let facts = $derived(candidate.facts);
	let imdb = $derived(candidate.external_ids?.imdb ?? null);
	let episodes = $derived(facts?.episode_count ? `${facts.episode_count} episodes` : '');
	let sub = $derived(
		[formatYears(candidate.year, facts?.end_year, candidate.kind), kindLabel(candidate.kind), episodes]
			.filter(Boolean)
			.join(' · ')
	);
	let rows = $derived(
		[
			{ label: 'Genres', value: (facts?.genres ?? []).join(', ') },
			{ label: isSeriesKind(candidate.kind) ? 'Creator' : 'Director', value: (facts?.creators ?? []).join(', ') },
			{ label: 'Stars', value: (facts?.cast ?? []).join(', ') }
		].filter((r) => r.value)
	);
</script>

<div class="match-pane">
	{#if candidate.poster_url}
		<PosterImage url={candidate.poster_url} alt={candidate.title} class="match-pane-poster" />
	{/if}
	<div class="match-pane-body">
		<h4 class="match-pane-title">{candidate.title}</h4>
		<p class="match-pane-sub">{sub}</p>
		{#if facts?.rating != null || imdb}
			<div class="match-pane-rating">
				{#if facts?.rating != null}
					<span class="match-pane-source">{RATING_LABEL[facts.rating_source ?? ''] ?? 'Rating'}</span>
					<span>★ {facts.rating.toFixed(1)}</span>
					{#if facts.votes}<span class="match-pane-muted">{formatVotes(facts.votes)}</span>{/if}
				{/if}
				{#if imdb}<span class="match-pane-muted mono">{imdb}</span>{/if}
			</div>
		{/if}
		{#if facts?.overview}<p class="match-pane-overview">{facts.overview}</p>{/if}
		{#if rows.length}
			<dl class="match-pane-facts">
				{#each rows as row (row.label)}
					<dt>{row.label}</dt>
					<dd>{row.value}</dd>
				{/each}
			</dl>
		{/if}
		{#if loading}
			<div class="match-pane-skeleton" data-testid="match-pane-skeleton" aria-hidden="true">
				<span></span><span></span><span></span>
			</div>
		{/if}
		{#if error}<p class="field-help">{error}</p>{/if}
		<div class="match-pane-actions">
			{#if canUse}
				<button type="button" class="btn btn-primary" disabled={applying} onclick={onuse}>
					{applying ? 'Applying...' : useLabel}
				</button>
			{/if}
			{#if imdb}
				<a class="btn" href="https://www.imdb.com/title/{imdb}/" target="_blank" rel="noopener noreferrer">
					Open on IMDb ↗
				</a>
			{/if}
		</div>
		{@render children?.()}
	</div>
</div>

<style>
	.match-pane {
		display: flex;
		gap: 1rem;
	}
	/* :global: also passed as PosterImage's class prop, landing on its own <img> */
	:global(.match-pane-poster) {
		width: 7rem;
		flex: none;
		align-self: flex-start;
		aspect-ratio: 2 / 3;
		border-radius: var(--radius-md);
		object-fit: cover;
	}
	.match-pane-body {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
		gap: 0.5rem;
	}
	.match-pane-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.match-pane-sub,
	.match-pane-muted {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.match-pane-rating {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
	}
	.match-pane-source {
		border-radius: var(--radius-sm);
		background: var(--color-warning);
		padding: 0 0.375rem;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--color-on-warning, #000);
	}
	.match-pane-overview {
		font-size: 0.875rem;
		color: var(--color-text);
	}
	.match-pane-facts {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.25rem 1rem;
		font-size: 0.8125rem;
	}
	.match-pane-facts dt {
		color: var(--color-text-muted);
	}
	.match-pane-skeleton {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}
	.match-pane-skeleton span {
		height: 0.625rem;
		border-radius: var(--radius-sm);
		background: var(--color-primary-tint-2);
	}
	.match-pane-skeleton span:nth-child(2) {
		width: 80%;
	}
	.match-pane-skeleton span:nth-child(3) {
		width: 60%;
	}
	.match-pane-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	@media (max-width: 640px) {
		.match-pane {
			flex-direction: column;
		}
	}
</style>
```

Check the token names used (`--color-warning`, `--color-on-warning`, `--radius-sm`) exist in `src/lib/styles`: `grep -rn "\-\-color-warning:\|\-\-radius-sm:\|\-\-color-on-warning" src/lib/styles src/app.css`. Replace any missing token with the nearest existing one (for the IMDb badge, the existing `.badge-imdb` class from the job page is the visual reference; reuse that class instead of `.match-pane-source` styling if it exists globally).

- [ ] **Step 4: Run to verify pass**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/match && npm run check && npm run lint:styles`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components/match
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(ui): match result row and detail pane"
```

---

### Task 10: `MatchPicker`

**Files:**
- Create: `services/ui-neu/frontend/src/lib/components/match/MatchPicker.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/match/MatchPicker.test.ts`

**Interfaces:**
- Consumes: Tasks 7–9 (`fetchMatchDetails`, `MatchProvider`, utils, row, pane).
- Produces: `MatchPicker` props `{ results: MetadataCandidate[]; query: string; year: string; providerLabel: string; canUse: boolean; useLabel: string; applying: boolean; onclose: () => void; onselect?: (c: MetadataCandidate, index: number) => void; onuse: (c: MetadataCandidate) => void; children?: Snippet }`. `onselect` fires on every selection and again when that selection's details arrive (same index). `onuse` receives the merged candidate.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MatchPicker from './MatchPicker.svelte';

vi.mock('$lib/api/jobs', () => ({ fetchMatchDetails: vi.fn() }));
import { fetchMatchDetails } from '$lib/api/jobs';
const mockDetails = vi.mocked(fetchMatchDetails);

const rows = [
	{ title: 'Kolchak: The Night Stalker', year: 1974, kind: 'tv', provider: 'tvmaze', external_ids: { tvmaze: '1' }, facts: null },
	{ title: 'The Night Stalker', year: 1972, kind: 'tv', provider: 'tvmaze', external_ids: { tvmaze: '2' }, facts: null }
];
const props = (o = {}) => ({
	results: rows,
	query: 'Kolchak: The Night Stalker',
	year: '1974',
	providerLabel: 'TVmaze',
	canUse: true,
	useLabel: 'Use this match',
	applying: false,
	onclose: vi.fn(),
	onuse: vi.fn(),
	...o
});
const detail = (title: string, cast: string[]) => ({
	candidates: [{ title, kind: 'tv', provider: 'tvmaze', facts: { cast, genres: [], creators: [] } }]
});

describe('MatchPicker', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('shows the header and selects the first row, fetching its details', async () => {
		mockDetails.mockResolvedValue(detail('Kolchak: The Night Stalker', ['Darren McGavin']));
		renderComponent(MatchPicker, { props: props() });
		expect(screen.getByText('2 RESULTS')).toBeInTheDocument();
		expect(screen.getByText('"Kolchak: The Night Stalker" · 1974 · TVmaze')).toBeInTheDocument();
		expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);
		expect(mockDetails).toHaveBeenCalledWith('tvmaze', 'tv', '1');
		await screen.findByText('Darren McGavin');
	});

	it('picking another row fetches its details once and reuses them later', async () => {
		mockDetails.mockImplementation(async (_p, _t, id) =>
			id === '1' ? detail('Kolchak: The Night Stalker', ['A']) : detail('The Night Stalker', ['B'])
		);
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('A');
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		await screen.findByText('B');
		await fireEvent.click(screen.getByRole('button', { name: /^Kolchak/ }));
		expect(screen.getByText('A')).toBeInTheDocument();
		expect(mockDetails).toHaveBeenCalledTimes(2);
	});

	it('a slow first details response does not replace the newer selection', async () => {
		let release!: (v: unknown) => void;
		mockDetails.mockImplementation((_p, _t, id) =>
			id === '1'
				? (new Promise((r) => (release = r)) as never)
				: Promise.resolve(detail('The Night Stalker', ['B']))
		);
		const onselect = vi.fn();
		renderComponent(MatchPicker, { props: props({ onselect }) });
		await fireEvent.click(screen.getByRole('button', { name: /^The Night Stalker/ }));
		await screen.findByText('B');
		release(detail('Kolchak: The Night Stalker', ['A']));
		await waitFor(() => expect(mockDetails).toHaveBeenCalledTimes(2));
		expect(screen.getByRole('heading', { name: 'The Night Stalker' })).toBeInTheDocument();
		expect(onselect.mock.lastCall?.[1]).toBe(1);
	});

	it('a details error keeps the row and shows a note', async () => {
		mockDetails.mockResolvedValue({ candidates: [], detail: 'tvmaze: miss' });
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('tvmaze: miss');
		expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
	});

	it('a rejected details call shows its message', async () => {
		mockDetails.mockRejectedValue(new Error('network down'));
		renderComponent(MatchPicker, { props: props() });
		await screen.findByText('network down');
	});

	it('Use passes the merged candidate; Close calls onclose', async () => {
		mockDetails.mockResolvedValue(detail('Kolchak: The Night Stalker', ['Darren McGavin']));
		const onuse = vi.fn();
		const onclose = vi.fn();
		renderComponent(MatchPicker, { props: props({ onuse, onclose }) });
		await screen.findByText('Darren McGavin');
		await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
		expect(onuse.mock.calls[0][0]).toMatchObject({ external_ids: { tvmaze: '1' }, facts: { cast: ['Darren McGavin'] } });
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(onclose).toHaveBeenCalledOnce();
	});

	it('a row without a provider id skips the details call', () => {
		renderComponent(MatchPicker, { props: props({ results: [{ title: 'X', kind: 'movie', provider: null }] }) });
		expect(mockDetails).not.toHaveBeenCalled();
		expect(screen.getByText('1 RESULT')).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/match/MatchPicker.test.ts`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement** `MatchPicker.svelte`

```svelte
<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { MetadataCandidate } from '$lib/types/api.gen';
	import { fetchMatchDetails, type MatchProvider } from '$lib/api/jobs';
	import { candidateKey, detailsId, isSeriesKind, mergeCandidate } from '$lib/utils/match';
	import MatchResultRow from './MatchResultRow.svelte';
	import MatchDetailPane from './MatchDetailPane.svelte';

	interface Props {
		results: MetadataCandidate[];
		query: string;
		year: string;
		providerLabel: string;
		canUse: boolean;
		useLabel: string;
		applying: boolean;
		onclose: () => void;
		onselect?: (c: MetadataCandidate, index: number) => void;
		onuse: (c: MetadataCandidate) => void;
		children?: Snippet;
	}

	let { results, query, year, providerLabel, canUse, useLabel, applying, onclose, onselect, onuse, children }: Props =
		$props();

	let selectedIndex = $state(0);
	// Fetched details by candidate key; errors by key. Kept for the life of
	// this result list, so going back to a row costs no second call.
	let details = $state<Record<string, MetadataCandidate>>({});
	let errors = $state<Record<string, string>>({});
	let loading = $state<Record<string, boolean>>({});

	let selectedRow = $derived(results[selectedIndex] ?? null);
	let selectedKey = $derived(selectedRow ? candidateKey(selectedRow) : null);
	let merged = $derived(
		selectedRow && selectedKey && details[selectedKey] ? mergeCandidate(selectedRow, details[selectedKey]) : selectedRow
	);

	// A new result list starts on its first row.
	$effect(() => {
		const list = results;
		untrack(() => {
			details = {};
			errors = {};
			loading = {};
			if (list.length) select(0);
		});
	});

	async function select(index: number) {
		const row = results[index];
		if (!row) return;
		selectedIndex = index;
		const key = candidateKey(row);
		onselect?.(details[key] ? mergeCandidate(row, details[key]) : row, index);
		const id = detailsId(row);
		if (!row.provider || !id || details[key] || loading[key]) return;
		loading = { ...loading, [key]: true };
		const { [key]: _drop, ...rest } = errors;
		errors = rest;
		try {
			const resp = await fetchMatchDetails(row.provider as MatchProvider, isSeriesKind(row.kind) ? 'tv' : 'movie', id);
			const found = resp.candidates[0];
			if (found) {
				details = { ...details, [key]: found };
				// Report the details only if this row is still the one shown.
				if (selectedIndex === index && results[index] === row) onselect?.(mergeCandidate(row, found), index);
			} else {
				errors = { ...errors, [key]: resp.detail ?? 'No details found.' };
			}
		} catch (e) {
			errors = { ...errors, [key]: e instanceof Error ? e.message : 'Could not load details' };
		} finally {
			loading = { ...loading, [key]: false };
		}
	}
</script>

<div class="match-picker">
	<div class="match-picker-head">
		<span class="match-picker-count">{results.length} {results.length === 1 ? 'RESULT' : 'RESULTS'}</span>
		<span class="match-picker-query">"{query}"{year ? ` · ${year}` : ''} · {providerLabel}</span>
		<button type="button" class="match-picker-close" onclick={onclose}>Close</button>
	</div>
	<div class="match-picker-body">
		<div class="match-picker-list">
			{#each results as row, i (i)}
				<MatchResultRow candidate={row} selected={i === selectedIndex} onselect={() => select(i)} />
			{/each}
		</div>
		{#if merged && selectedKey}
			<div class="match-picker-pane">
				<MatchDetailPane
					candidate={merged}
					loading={!!loading[selectedKey]}
					error={errors[selectedKey] ?? null}
					{canUse}
					{useLabel}
					{applying}
					onuse={() => onuse(merged)}
				>
					{@render children?.()}
				</MatchDetailPane>
			</div>
		{/if}
	</div>
</div>

<style>
	.match-picker {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
	.match-picker-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		border-bottom: 1px solid var(--color-border);
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
	}
	.match-picker-count {
		font-weight: 700;
		letter-spacing: 0.05em;
		color: var(--color-primary-text);
	}
	.match-picker-query {
		flex: 1;
		color: var(--color-text-muted);
	}
	.match-picker-close {
		color: var(--color-text-muted);
	}
	.match-picker-close:hover {
		color: var(--color-text);
	}
	.match-picker-body {
		display: grid;
		grid-template-columns: minmax(0, 45%) minmax(0, 1fr);
	}
	.match-picker-list {
		display: flex;
		max-height: 24rem;
		flex-direction: column;
		gap: 0.25rem;
		overflow-y: auto;
		border-right: 1px solid var(--color-border);
		padding: 0.5rem;
	}
	.match-picker-pane {
		padding: 0.75rem 1rem;
	}
	@media (max-width: 640px) {
		.match-picker-body {
			grid-template-columns: 1fr;
		}
		.match-picker-list {
			border-right: 0;
			border-bottom: 1px solid var(--color-border);
		}
	}
</style>
```

The `const { [key]: _drop, ...rest } = errors;` line may trip ESLint's unused-var rule; if `npm run lint` flags it, replace it with `errors = Object.fromEntries(Object.entries(errors).filter(([k]) => k !== key));`.

- [ ] **Step 4: Run to verify pass**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/match && npm run check && npm run lint && npm run lint:styles`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components/match
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(ui): match picker with per-row details fetch"
```

---

### Task 11: `TitleSearch` uses the picker and saves a match

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/TitleSearch.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/TitleSearch.test.ts`, `services/ui-neu/frontend/src/lib/components/__tests__/IdentifyDialog.test.ts`

**Interfaces:**
- Consumes: `MatchPicker` (Task 10), `searchMetadata(…, year)`, `resolveJob` body `match` (Task 7), `isSeriesKind` (Task 8).
- Produces: unchanged `TitleSearch` props (`job`, `onapply`, `onresolved`, `onseries`, `initialType`).

- [ ] **Step 1: Write the new failing tests** (append to `TitleSearch.test.ts`, inside `describe('TitleSearch', …)`)

Add `fetchMatchDetails: vi.fn(() => Promise.resolve({ candidates: [] }))` to the existing `vi.mock('$lib/api/jobs', …)` factory at the top of the file, and import it.

```ts
	describe('match picker', () => {
		const tvmazeRow = createCandidate({
			title: 'Kolchak: The Night Stalker',
			year: 1974,
			kind: 'tv',
			provider: 'tvmaze',
			poster_url: 'https://static.tvmaze.com/k.jpg',
			external_ids: { imdb: 'tt0071003', tvdb: '77170', tvmaze: '1' },
			facts: { genres: ['Horror'], cast: [], creators: [] }
		});

		it('sends the year and shows results in the picker with the first selected', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', year: 1974, media_type: 'tv' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			expect(mockSearchMetadata).toHaveBeenCalledWith('Kolchak', 'tv', 'tmdb', 1974);
			expect(await screen.findByText('1 RESULT')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
		});

		it('Use this match resolves with every show id and the match block', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1]).toEqual({
				title: 'Kolchak: The Night Stalker',
				year: 1974,
				media_type: 'tv',
				external_ids: { imdb: 'tt0071003', tmdb: null, tmdb_kind: null, tvdb: '77170', tvmaze: '1' },
				match: {
					provider: 'tvmaze',
					poster_url: 'https://static.tvmaze.com/k.jpg',
					poster_is_manual: false,
					facts: { genres: ['Horror'], cast: [], creators: [] }
				}
			});
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('an edited poster is sent as manual', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			await fireEvent.input(screen.getByLabelText('Poster URL'), { target: { value: 'https://x.example/p.jpg' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].match).toMatchObject({
				poster_url: 'https://x.example/p.jpg',
				poster_is_manual: true
			});
		});

		it('editing the type to the other kind sends no ids and no match', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'movie' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			const body = mockResolve.mock.calls[0][1];
			expect(body.media_type).toBe('movie');
			expect(body.match).toBeUndefined();
			expect(body.external_ids).toBeUndefined();
		});

		it('Close clears the results', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
			expect(screen.queryByText('1 RESULT')).toBeNull();
		});
	});
```

`createCandidate` already exists in the test file; its `overrides` type is `Partial<MetadataCandidate>`, which now includes `provider` and `facts`.

- [ ] **Step 2: Run to verify failure**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/TitleSearch.test.ts -t "match picker"`
Expected: FAIL.

- [ ] **Step 3: Implement** in `TitleSearch.svelte`

Script changes:

1. Imports: replace `PosterImage` and `Glyph` imports with `import MatchPicker from './match/MatchPicker.svelte';` and `import { isSeriesKind } from '$lib/utils/match';`. Import the `ExternalIds` type from `$lib/types/api.gen`. Remove `reveal` only if nothing else uses it (the feedback span keeps using it; keep it).
2. Remove the `detail`, `loadingDetail` state, the `$effect` that copies `detail` into the edit fields, `handleSelect` and `backToResults`.
3. Add:

```ts
	// "Edit before using": the edit fields start from the selected match and,
	// once opened, are what Use applies (spec 4.2).
	let editing = $state(false);
	let selectedIndex = $state(-1);

	function fillEdit(c: MetadataCandidate) {
		editTitle = c.title;
		editYear = c.year != null ? String(c.year) : '';
		editType = isSeriesKind(c.kind) ? 'series' : 'movie';
		editPosterUrl = c.poster_url ?? '';
	}

	function handlePickerSelect(c: MetadataCandidate, index: number) {
		if (index !== selectedIndex) {
			editing = false;
			feedback = null;
		}
		selectedIndex = index;
		selected = c;
	}

	function toggleEdit() {
		if (!editing && selected) fillEdit(selected);
		editing = !editing;
	}

	function closeResults() {
		results = [];
		selected = null;
		selectedIndex = -1;
		editing = false;
	}

	let providerLabel = $derived(sourceOptions.find((o) => o.id === source)?.label ?? '');
	let parsedSearchYear = $derived(/^\d{4}$/.test(yearInput.trim()) ? Number(yearInput.trim()) : null);
```

4. `handleSearch`: the IMDb branch becomes

```ts
		if (imdb) {
			searching = true;
			searchError = null;
			closeResults();
			try {
				const resp = await fetchMediaDetail(imdb);
				results = resp.candidates.slice(0, 1);
				if (!results.length) searchError = 'No match found for that IMDb ID.';
			} catch (e) {
				searchError = e instanceof Error ? e.message : 'IMDb lookup failed';
			} finally {
				searching = false;
			}
			return;
		}
```

and the title branch calls `closeResults()` instead of resetting `results/selected/detail`, then `searchMetadata(query.trim(), searchType, source, parsedSearchYear)`.

5. Replace `applyResult` with:

```ts
	async function applyResult(c: MetadataCandidate) {
		selected = c;
		const values = editing
			? { title: editTitle.trim(), year: editYear.trim(), isSeries: editType === 'series', poster: editPosterUrl.trim() || null }
			: { title: c.title, year: c.year != null ? String(c.year) : '', isSeries: isSeriesKind(c.kind), poster: c.poster_url ?? null };
		if (!values.title) {
			feedback = { type: 'error', message: 'Title is required' };
			return;
		}
		applying = true;
		feedback = null;
		const parsedYear = values.year ? Number(values.year) : null;
		const year = Number.isFinite(parsedYear as number) ? parsedYear : null;
		const mediaType = values.isSeries ? 'tv' : 'movie';
		// The candidate's ids name a title of its own kind; after a type edit they don't apply.
		const idsApply = isSeriesKind(c.kind) === values.isSeries;
		let resolved: ResolveResponse | undefined;
		try {
			if (canResolve && idsApply && c.provider) {
				// A picked match states the whole show (spec 3.6): every show id,
				// nulls included, plus provider, poster and facts in one call.
				const ids = c.external_ids ?? {};
				const externalIds: ExternalIds = {
					imdb: ids.imdb ?? null,
					tmdb: ids.tmdb ?? null,
					tmdb_kind: ids.tmdb_kind ?? null,
					tvdb: ids.tvdb ?? null,
					tvmaze: ids.tvmaze ?? null
				};
				resolved = await resolveJob(job.id, {
					title: values.title,
					year,
					media_type: mediaType,
					external_ids: externalIds,
					match: {
						provider: c.provider as MatchProvider,
						poster_url: values.poster,
						poster_is_manual: values.poster !== (c.poster_url ?? null),
						facts: c.facts ?? null
					}
				});
				feedback = { type: 'success', message: 'Identified' };
			} else if (canResolve) {
				resolved = await resolveJob(job.id, { title: values.title, year, media_type: mediaType });
				let message = 'Identified';
				if (values.poster !== (job.poster_url_manual ?? null)) {
					try {
						await updateJobTitle(job.id, { poster_url_manual: values.poster });
					} catch {
						message = 'Identified; poster not saved';
					}
				}
				feedback = { type: 'success', message };
			} else {
				// Non-resolvable status (created/ripping/failed/abandoned): poster only.
				await updateJobTitle(job.id, { poster_url_manual: values.poster });
				feedback = { type: 'success', message: 'Poster updated' };
			}
			if (resolved) onresolved?.(resolved);
			if (values.isSeries && canResolve) onseries?.();
			else onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed' };
		} finally {
			applying = false;
		}
	}
```

Import `type MatchProvider` from `$lib/api/jobs` alongside the existing imports. Note the old behaviour sent `external_ids` (present ids only) on the non-match resolve path; the new non-match path (no provider, or a type edit) sends none. That is intended: without a provider the ids can't be trusted to describe one show (Review Focus 3).

Markup: replace everything from `<!-- Results grid` to the end of the detail panel `{/if}` with:

```svelte
	{#if results.length > 0}
		<MatchPicker
			{results}
			query={query.trim()}
			year={yearInput.trim()}
			{providerLabel}
			canUse={$isAdmin}
			useLabel={canResolve ? 'Use this match' : 'Use poster'}
			{applying}
			onclose={closeResults}
			onselect={handlePickerSelect}
			onuse={applyResult}
		>
			{#if $isAdmin}
				<button type="button" class="title-search-edit-toggle" aria-expanded={editing} onclick={toggleEdit}>
					Edit before using
				</button>
				{#if editing}
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<label class="field sm:col-span-2">
							<span class="field-label">Title</span>
							<input type="text" bind:value={editTitle} />
						</label>
						<label class="field">
							<span class="field-label">Year</span>
							<input type="text" bind:value={editYear} />
						</label>
						<label class="field">
							<span class="field-label">Type</span>
							<select bind:value={editType}>
								<option value="movie">Movie</option>
								<option value="series">Series</option>
							</select>
						</label>
						<label class="field sm:col-span-2">
							<span class="field-label">Poster URL</span>
							<input type="text" bind:value={editPosterUrl} placeholder="https://..." />
						</label>
					</div>
				{/if}
			{/if}
			{#if feedback}
				<span in:reveal class="title-search-feedback" data-tone={feedback.type}>{feedback.message}</span>
			{/if}
		</MatchPicker>
	{/if}
```

Styles: delete the now-unused rules (`.title-search-card*`, `:global(.title-search-poster)`, `.title-search-placeholder`, `.title-search-loading`, `.title-search-success-btn`, `.badge[data-kind=…]`, and `.title-search-action-btn` if Apply no longer uses it). Add:

```css
	.title-search-edit-toggle {
		align-self: flex-start;
		font-size: 0.75rem;
		color: var(--color-primary-text);
		text-decoration: underline;
	}
```

`npm run check` reports any rule left unused ("Unused CSS selector"); delete those.

- [ ] **Step 4: Update the existing tests that drove the old grid**

Run (from `services/ui-neu/frontend`): `npx vitest run src/lib/components/TitleSearch.test.ts src/lib/components/__tests__/IdentifyDialog.test.ts`

Fix each failure with this mapping, keeping every test's intent:

| Old step | New step |
|---|---|
| `fireEvent.click(screen.getByText('<title>'))` to pick a grid card | nothing when it is the first result (it is selected automatically); otherwise `fireEvent.click(screen.getByRole('button', { name: /^<title>/ }))` |
| `getByRole('button', { name: 'Apply' })` | `getByRole('button', { name: 'Use this match' })` |
| `'Apply Poster'` | `'Use poster'` |
| editing `Title` / `Year` / `Type` / `Poster URL` fields | first `fireEvent.click(screen.getByRole('button', { name: 'Edit before using' }))` |
| `'Back to results'` | delete the step; the list stays visible beside the pane |
| `getByText('Search')` when a result row title also contains "Search" | `getByRole('button', { name: 'Search' })` |
| expecting `resolveJob` body `external_ids` with only present ids | for candidates **with** `provider`: expect all five show ids plus `match` (see the new tests); for candidates built without `provider` (the default `createCandidate`), expect no `external_ids` |
| expecting `updateJobTitle` after a resolve | only for candidates without `provider`; with `provider`, the poster travels in `match` and `updateJobTitle` is not called |
| `expect(mockSearchMetadata).toHaveBeenCalledWith(q, type, source)` | add the fourth argument: the job fixture's year as a number when the Year box holds four digits, else `null` (check `createJob`'s default `year`) |
| `fetchMediaDetail` result shown directly in the detail panel | the single result appears in the picker, selected; Use this match works the same |

For guest tests ("guest write-control gating"), the expectation becomes: no `Use this match`/`Use poster` button and no `Edit before using` button.

- [ ] **Step 5: Run the full UI gate**

Run (from `services/ui-neu/frontend`): `npm run check && npm run lint:styles && npm run lint && npm run format:check && npx vitest run`
Expected: all pass. If `format:check` fails, run `npx prettier --write` on the changed files and re-run.

- [ ] **Step 6: Commit**

```bash
git add services/ui-neu/frontend/src
git -c user.name=uprightbass360 -c user.email=uprightbass360@gmail.com commit -m "feat(ui): title search shows the match picker and saves a whole match"
```

---

### Task 12: Visual check, full gate, PR, deploy

**Files:**
- No source changes expected; fix-ups go in the task whose code they touch.

- [ ] **Step 1: Full backend and contract gate**

Run from the worktree root:
```bash
uv run pytest -q
uv run pre-commit run --all-files
bash devtools/regen-openapi-snapshot.sh && bash services/ui-neu/scripts/codegen.sh && git status --short services/ui-neu
```
Expected: tests pass with 100% Backend statement coverage; pre-commit clean; the regen leaves no diff.

- [ ] **Step 2: Visual check with mocked API**

From `services/ui-neu/frontend`, start `npm run dev -- --port 5199 --strictPort` (background). With the Playwright MCP `browser_run_code_unsafe`:
- `addInitScript` sets `localStorage.arm_token = 'mock'` and `localStorage.arm_role = 'admin'`.
- `page.route((url) => url.pathname.startsWith('/api/'), …)` serves: a job detail for a TV Blu-ray in `awaiting_review` (title "Kolchak: The Night Stalker", year 1974) on `GET /api/jobs/<id>`; four TMDb candidates on `GET /api/metadata/search` (Kolchak 1974–1975 series with cast and rating 7.9; The Night Stalker 1972; The Night Strangler 1973; Night Stalker 2005–2006); a full record on `GET /api/metadata/details`; `{}` or `[]` for anything else the page asks for.
- Open `/jobs/<id>`, click Search, run the search. Screenshot at 1280px and 390px wide into `/home/upb/src/automatic-ripping-machine/.playwright-mcp/`.

Check against the mockup: the header line, rows with thumbnail, years · type, cast, ★ rating, the pane with poster, rating badge, votes, IMDb id, plot, Genres/Creator/Stars, the two buttons; at 390px the pane stacks under the list with no horizontal scroll. Stop the dev server by its PID (never `pkill -f` with a pattern that matches your own shell).

- [ ] **Step 3: Push and open the PR**

```bash
env -u GITHUB_TOKEN git push -u origin feat/match-picker
env -u GITHUB_TOKEN gh pr create --repo shitwolfymakes/automatic-ripping-machine --base identification/3-review-and-cd \
  --head feat/match-picker --title "Match picker: richer title search results" --body-file <scratchpad>/body-match-picker.md
```

The body summarises the spec sections (data, details endpoint, resolve `match`, UI, tests) and links the spec and plan paths. No "Generated with" footer. Wait for CI; fix any failure in the task that owns the code.

- [ ] **Step 4: Deploy to hifi** (backend and UI both change)

1. In `/home/upb/src/arm-wt-deploy-identity`: `git -c user.name=upb -c user.email=uprightbass360@gmail.com merge --no-ff feat/match-picker -m "Merge feat/match-picker"`; run `npm run check` and the TitleSearch/match vitest files there.
2. On hifi (`ssh -i ~/.ssh/id_ed25519_docker-server upb@192.168.0.69`, checkout `~/src/automatic-ripping-machine-v3`): check for active rips and held ISO jobs with `/tmp/iso-q.sql` against the `jobs` table; do not restart during an active rip.
3. `git checkout -q main` on hifi; locally `git push hifi deploy/identity-20261015`; on hifi `git checkout -q deploy/identity-20261015`.
4. On hifi: `nohup bash -c "bash devtools/setup-dev.sh up; echo EXIT \$?" > ~/arm/deploy-match-picker.log &`, then confirm the log ends with `EXIT 0`.
5. Ask the owner to try a search on a disc in review.
