# Match picker: richer title search results

Status: draft for review, 2026-10-16.
Branch: `feat/match-picker`, stacked on `identification/3-review-and-cd` (#376).

## 1. Why

When an operator searches for a disc's show or movie, the results are a grid
of posters with a title, a year and a kind badge. That is not enough to tell
apart *Kolchak: The Night Stalker* (1974–1975 series), *The Night Stalker*
(1972 TV movie) and *Night Stalker* (2005 series). The operator wants what a
person uses to decide: years run, type, rating, cast, plot, genres, creator
and episode count.

Most of that data already reaches the backend and is dropped:

- TMDb search returns `overview` and `vote_average`, and the search already
  makes one `/{kind}/{id}/external_ids` call per result.
- TVmaze search returns `genres`, `rating`, `ended` and `summary`.
- OMDb `?i=` returns Plot, Genre, Actors, Director, Writer, imdbRating and
  imdbVotes, but search (`?s=`) returns only Title, Year, imdbID and Poster.
- TVDB search returns little; `/series/{id}/extended` has the rest.

`MetadataCandidate` (`arm_common/schemas/metadata.py`) has no field for any
of it.

Two smaller gaps ride along:

- The image proxy allowlist (`routers/images.py`) lacks TVmaze and TVDB, so
  their posters do not load through the proxy.
- The search row's Year box is never sent or used.

## 2. Decisions (agreed 2026-10-16)

- **Light rows, full detail on pick.** Result rows show what the search
  already has. Picking a result calls a details endpoint for the full record.
  One extra upstream call per pick, never per result.
- **Cast in rows only where free.** TMDb rows carry cast (its existing
  per-result call becomes a detail call). OMDb, TVmaze and TVDB rows show
  years, type and rating; their cast appears in the detail pane.
- **One shared component.** The Home review card, the job page and the
  Identify dialog all use `TitleSearch`, which renders the new picker.
- **Year sorts, never filters.** Results are ordered nearest the Year box
  first; a wrong disc year cannot hide the right title.
- **A picked match replaces the identity.** Use this match states the whole
  show: its ids replace the stored set, and the job records the provider,
  the poster and a snapshot of the facts. Other resolve callers keep today's
  merge rules.
- **Facts are snapshotted on the job** (option b). Refreshing a stale
  snapshot is left for later.
- **Allowlist** gains `static.tvmaze.com` and `artworks.thetvdb.com`
  (checked 2026-10-16: both serve posters with a direct 200, no redirect).

## 3. Backend

### 3.1 Schema

`MetadataCandidate` gains `provider: str | None` (the source that produced
it: `tmdb`, `omdb`, `tvmaze`, `tvdb`) and `facts: IdentityFacts | None`.
`IdentityFacts` (in `arm_common/schemas/job_metadata.py`, shared with the
snapshot in 3.6) holds these fields, all defaulting to `None` or empty:

| Field | Type | Meaning |
|---|---|---|
| `end_year` | `int \| None` | Last year of a series run; `None` while running or for a movie |
| `overview` | `str \| None` | Plot, plain text (HTML stripped) |
| `rating` | `float \| None` | 0–10 |
| `rating_source` | `"imdb" \| "tmdb" \| "tvmaze" \| None` | Whose rating `rating` is |
| `votes` | `int \| None` | Vote count behind `rating` |
| `genres` | `list[str]` | |
| `creators` | `list[str]` | Series creators, or a movie's directors |
| `cast` | `list[str]` | Top three billed |
| `episode_count` | `int \| None` | Series only |

`provider` plus `external_ids` lets the UI ask for details without a separate
opaque id. Existing clients ignore the new fields.

### 3.2 Facts extraction

A new module `metadata/facts.py` holds one pure function per provider that
reads a raw payload and returns `IdentityFacts`. It has no I/O.
`_to_candidate` in `routers/metadata.py` calls it, so search and details share
one mapping. `MetadataResult` is unchanged; its `payload` already carries the
raw body.

Per provider:

- **TMDb**: title/name, years from `release_date` / `first_air_date` and
  `last_air_date` (end year only when `status` is Ended or Canceled),
  `overview`, `vote_average`/`vote_count` (`rating_source: tmdb`), `genres[].name`,
  `created_by[].name` (TV) or crew with job Director (movie), cast from
  `aggregate_credits` (TV) or `credits` (movie), `number_of_episodes`.
- **OMDb**: `Year` ("1974–1975" splits into year and end year), `Plot`,
  `imdbRating`/`imdbVotes` (`rating_source: imdb`; commas stripped), `Genre`,
  `Actors`, `Director` (movie) or `Writer` (series, as creator), `totalSeasons`
  is not an episode count and is ignored. "N/A" means absent.
- **TVmaze**: `premiered`/`ended`, `summary` (HTML stripped), `rating.average`
  (`rating_source: tvmaze`, no vote count), `genres`, cast from
  `_embedded.cast[].person.name`, episode count from `_embedded.episodes`
  length when embedded.
- **TVDB**: `year`, `overview` (English translation when present), `genres[].name`,
  characters with `peopleType` Actor for cast, `status` and `lastAired` for end
  year. TVDB's `score` is not on a 0–10 scale, so no rating.

### 3.3 Search changes

- **TMDb**: in `_search_candidates`, the per-result `get_external_id_map` call
  becomes `get_detail(tmdb_id, kind)`:
  `/{kind}/{id}?append_to_response=external_ids,{credits|aggregate_credits}`.
  Same call count. The external ids it returns feed the existing id mapping,
  and the detail body is merged into the result's payload. The dispatcher's
  own `get_external_id_map` call (`dispatcher.py:312`) is untouched.
- **TVmaze**: nothing new; the search body already carries the row facts.
- **OMDb, TVDB**: unchanged.
- **Year**: `GET /api/metadata/search` takes an optional `year`. When present,
  candidates are stably sorted by `abs(candidate.year - year)`, candidates
  with no year last. Nothing is dropped and the year is not sent upstream.

### 3.4 Details endpoint

`GET /api/metadata/details?provider=&type=&id=` returns
`MetadataSearchResponse` with one fully populated candidate (the existing
shape, so error handling matches search).

- `id` is the provider's own id: TMDb id, IMDb id for OMDb, TVmaze id, TVDB id.
- Upstream calls: TMDb `get_detail`; OMDb `?i=&plot=short`; TVmaze
  `/shows/{id}?embed[]=cast&embed[]=episodes`; TVDB
  `/series/{id}/extended?meta=translations` (without `short`, so characters
  are included).
- A missing key, an upstream error or a miss returns 200 with no candidate
  and a `detail` message, as search does. A bad `provider`/`type` is a 422.
- Results are cached in process for one hour, keyed by
  `(provider, type, id)`, capped at 256 entries (oldest evicted). Errors are
  not cached.
- Auth matches `/api/metadata/search`.

### 3.5 Image allowlist

Add `static.tvmaze.com` and `artworks.thetvdb.com` to `_ALLOWED_IMAGE_HOSTS`.

### 3.6 Saving a match (resolve)

Today `POST /api/jobs/{id}/resolve` merges ids one by one, and the UI sends
only the ids the picked candidate has. Two failures follow once operators
switch providers and search again:

- **Mixed shows.** A job holding `tmdb=A` that gets a TVmaze or OMDb result
  for show B (no TMDb id) keeps `tmdb=A` beside `imdb=B, tvdb=B`; the show
  change rule (`jobs.py` ~1255) only fires when a stored id is *replaced*.
  The episode stage tries TMDb first by default and matches show A.
- **Lost TVmaze id.** `_SHOW_ID_FIELDS` excludes `tvmaze`, so a picked TVmaze
  result drops the one id it is sure of.

Also, `identity.provider` is never updated by resolve, and the picker saves
the poster as `poster_url_manual`, which then hides any later automatic
poster.

**Change.** `ResolveRequest` gains an optional `match`:

```
match: {
  provider: "tmdb" | "omdb" | "tvmaze" | "tvdb"
  poster_url: str | None        # the candidate's poster, edited or not
  poster_is_manual: bool        # true when edited under "Edit before using"
  poster_url_manual: str | None # the edited poster (null clears the override)
  facts: IdentityFacts | None   # snapshot, see below
}
```

When `match` is present:

- `external_ids` **replaces** `identity.external_ids` wholesale, `tvmaze`
  included; ids the request lacks become `None`. (`musicbrainz_release` and
  `anidb` are not show ids for this path and are kept.) The exception is a
  re-pick of the **same show**: at least one of imdb/tmdb/tvdb/tvmaze agrees
  with the stored id and none disagrees. Then the sent ids only fill in, and
  the ids the picked provider lacks (TMDb has no TVmaze id, OMDb only IMDb)
  are kept. That is not a show change.
- `identity.provider = match.provider`, `identity.identified_at = now`,
  `identity.overview = facts.overview`.
- `identity.facts = match.facts` with `identity.facts_fetched_at = now`.
- Poster: `poster_url = match.poster_url`, unless that is null and the show
  did not change (the stored poster is still this show's). When
  `poster_is_manual` is true, `poster_url_manual = match.poster_url_manual`
  (a cleared field clears the override, so the new automatic poster shows);
  otherwise a match with a poster sets `poster_url_manual = None`, and one
  without keeps the override.
- Everything else (title, year, media_type, status promotion, fan-out,
  episode re-run via `_identity_snapshot`, `forget_episode_show_ids` on a show
  change) runs as today. Ids that changed count as a show change.

Without `match` the endpoint behaves exactly as today (Edit identity, the
Info form and the suggestion accept path are unchanged).

**Snapshot model.** `IdentityFacts` in `arm_common/schemas/job_metadata.py`
is the model from 3.1 (`end_year`, `overview`, `rating`, `rating_source`,
`votes`, `genres`, `creators`, `cast`, `episode_count`). `JobIdentity` gains `facts: IdentityFacts | None` and
`facts_fetched_at: datetime | None`. Both live in `metadata_json`, a JSON
column, so **no migration** is needed. The facts are sent by the UI (it
already holds the fetched details); the backend validates the shape but does
not refetch. A later identify or accept replaces `identity` wholesale, which
drops the snapshot, as it should for a different identification.

`JobView` exposes nothing new in this change; a later change can show the
snapshot on the job page.

**UI side.** `TitleSearch.applyResult` sends every show id field of the
picked candidate (nulls included) plus `match`, instead of filtering to the
non-null ids.

### 3.7 Wire contract

Regenerate `openapi.snapshot.json` and `api.gen.ts`
(`devtools/regen-openapi-snapshot.sh`, `services/ui-neu/scripts/codegen.sh`).

## 4. UI

### 4.1 Components

- **`MatchPicker.svelte`** (new, `lib/components/match/`): props `results`,
  `query`, `year`, `providerLabel`, `onclose`, `onuse(candidate)`, plus an
  `edit` snippet slot for the editable fields. It owns the selection and the
  details fetch.
- **`MatchResultRow.svelte`**: poster thumb, title, `years · kind`, cast line
  when present, ★ rating.
- **`MatchDetailPane.svelte`**: poster, title, `years · kind · N episodes`,
  rating badge (IMDb/TMDb/TVmaze) with rating and votes, IMDb id, plot,
  then a Genres / Creator (Director for a movie) / Stars list. Buttons:
  **Use this match** and **Open on IMDb ↗** (only with an IMDb id).
- **`lib/utils/match.ts`**: pure helpers: `formatYears(year, end_year, kind)`
  ("1974–1975", "1972"; no end year shows the start year alone, since a
  running show and an unknown end look the same), `kindLabel` ("TV Series",
  "Movie"), `formatVotes` ("9.8K votes").

`TitleSearch.svelte` keeps the search row and the apply logic and replaces its
poster grid and detail panel with `MatchPicker`.

### 4.2 Behaviour

- **Header**: "N RESULTS · "query" · year · Provider" and a Close button
  that clears the results.
- **Selection**: the first result is selected when results arrive. Picking a
  row shows its known facts in the pane at once and fetches details; missing
  fields show skeleton lines until the fetch lands. A details error shows a
  one-line note in the pane and keeps the row's facts.
- **Use this match** resolves with the merged candidate and `match` (3.6),
  so ids, provider, poster and facts save in one call. When the job cannot
  resolve, it saves the poster only, as today. Admin only, as today.
- **Edit before using**: a toggle under the buttons reveals today's editable
  Title / Year / Type / Poster URL fields, prefilled; Use applies the edited
  values.
- **IMDb id lookup** (the IMDb box) yields one result and opens it the same
  way.
- **Layout**: list left (about 45%), pane right; under 640px the pane stacks
  below the list. The list scrolls inside a max height so the card stays
  compact.

## 5. Testing

- **Backend** (respx, zero infra, 100% statement coverage kept):
  - `facts.py`: one test per provider from recorded payload fixtures, plus
    absent / "N/A" / HTML-summary cases.
  - TMDb search uses `get_detail` (one call per result) and fills cast.
  - Year sort: nearest first, stable, no-year last, nothing dropped.
  - Details endpoint: each provider, cache hit skips upstream, errors not
    cached, missing key, 422 on bad params.
  - Allowlist: the two new hosts pass; a look-alike host fails.
  - Resolve with `match`: ids replaced wholesale (stale `tmdb=A` cleared when
    a TVmaze result for B is applied); `tvmaze` saved; provider, overview,
    facts and `facts_fetched_at` written; poster to `poster_url` with manual
    cleared, or to `poster_url_manual` when `poster_is_manual`; episode stage
    rescheduled and episode show ids forgotten on a show change.
  - Resolve without `match`: today's merge tests still pass unchanged.
- **UI** (vitest): `match.ts` helpers; `MatchResultRow` (cast present /
  absent, rating); `MatchDetailPane` (skeleton, filled, IMDb link
  present/absent); `MatchPicker` (first selected, pick fetches details,
  details error, Use and Edit); updated `TitleSearch` tests.
- **Visual**: Playwright with the mocked `/api/**` recipe, Kolchak results,
  wide and 390px widths.
- **Gate**: `npm run check`, `lint:styles`, `lint`, `format:check`,
  `npx vitest run`; `uv run pytest`; OpenAPI drift clean.

## 6. Out of scope

- Caching search responses or adding rate limiting to the metadata clients.
- Sending the year to providers as a filter.
- TVDB ratings.
- Refreshing a stale facts snapshot, and showing the snapshot on the job
  page.
- Changing episode matching or the identify pipeline's own provider calls.
