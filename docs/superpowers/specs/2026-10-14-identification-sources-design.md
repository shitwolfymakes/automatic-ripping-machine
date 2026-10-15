# Identification sources: one registry for order, enablement and keys

**Status:** design spec for review, 2026-10-14
**Parent:** #258 (Settings › Identification tab and Identity card, design v4.2)
**Closes when done:** #287 (D-158), #313 (D-184, the provider literal half)
**Supersedes:** the scoping draft `2026-10-14-identification-pipeline-decoupling.md`

## 1. Goal

Make the Identity card's three promises true in the backend:

1. Online sources are tried in the operator's order, per media type.
2. A source that is unchecked, unkeyed or unknown is never called.
3. An empty list means no online lookup for that media type.

Today provider choice is made in nine places, most of them by "is a TMDb key saved". This
spec replaces those with one registry that every decision site reads, and fixes the
behaviours the earlier review found untrue (the TheDiscDB handover, the ignored volume
label, the undisclosed community-database lookup, the hidden OMDb key).

### Non-goals

- Cross-job series operations (upstream #1605) and anything else #258 lists as out of scope.
- Changing how disc hints, TheDiscDB claims, the episode stage or the claim resolver work.
  Steps 2, 3, 6 and 7 of the pipeline already obey settings and are kept as they are.
- Circuit breaker or "unreachable since" status (the old §9a). Dropped from v4.2; a later
  spec can add a `source_status` accessor to the registry without changing its callers.
- New sources (CD-TEXT, Discogs, AniDB). The registry makes them one adapter each; none is
  added here.

## 2. The pipeline today

Entry: `POST /api/ripper/identify` (`services/backend/arm_backend/routers/ripper.py:531-760`).

| Step | Code | Driven by settings? |
|---|---|---|
| 1. Store fingerprints | `ripper.py:596-608` | n/a |
| 2. Disc hints (BDMT title, volume label) → claims + hint title | `ripper.py:611-616` → `pipeline.run_disc_hints(sources=enabled_hint_sources(cfg))` | Yes: `disc_hint_sources` |
| 3. TheDiscDB content-hash match → claims | `ripper.py:618-631` | Yes: `thediscdb_enabled` |
| 4a. TheDiscDB IMDb id → exact resolve | `ripper.py:654-660` → `dispatcher.identify_from_imdb` (`dispatcher.py:228-238`) | No: TMDb `/find` only, gated on the TMDb key |
| 4b. Dispatcher, CD | `dispatcher._identify_cd` (`:103-107`) | No: MusicBrainz disc-id lookup, no switch |
| 4c. Dispatcher, video, community DB | `dispatcher._identify_video:122-130` | No: 1337server CRC64 lookup runs first on every DVD with a CRC64; no key, no switch, not on the card |
| 4d. Dispatcher, video, candidates | `dispatcher._identify_video:132-154` | Partly: hint title comes from the enabled hints, but the normalized volume label is always added as a second candidate |
| 4e. Dispatcher, video, provider walk | `_search_kind` (`:179-193`), `_search_title` (`:195-226`) | No: TMDb if keyed, then OMDb if keyed; kind order (movie/tv) by heuristic |
| 4f. TMDb id enrichment | `_with_tmdb_ids` (`:240-260`) | TMDb key only |
| 5. Result → job title, kind, `provider_raw`; hold or miss | `ripper.py:683-725` | Yes: `hold_for_review`, `block_on_miss` |
| 6. Episode stage | `stage_runner.build_providers` (`:93-101`), `episode_stage._ordered_providers` (`:118-131`) | Yes: `episode_sources`, `configured(cfg)`, job pin, `only_source` |
| 7. Resolver (claim precedence) | `pipeline.resolve_job` → `resolver.resolve(tiers, ranks=source_ranks(cfg), disabled=disabled_source_ids(cfg))` | Yes: both ranked lists |

Interactive paths that decide on their own:

| Route | Code | Decides by |
|---|---|---|
| `GET /api/metadata/search` | `routers/metadata.py:67-99` | `provider` param, else `metadata_provider`, else TMDb; `SearchProvider = Literal["tmdb","omdb"]` |
| `GET /api/metadata/lookup?imdb_id` | `routers/metadata.py:101-140` | `metadata_provider` → TMDb `/find` or OMDb `i=` |
| `GET /api/metadata/music/search`, `/music/{id}` | `routers/metadata.py:145-195` | MusicBrainz, hard-coded |
| `PATCH /api/config` validation | `routers/config.py:153-156` | duplicated `("tmdb","omdb")` literal (#313) |

Hidden input: `main.py:202` passes the `OMDB_API_KEY` environment variable as
`omdb_api_key_override`, which the dispatcher prefers over the saved key
(`dispatcher.py:189, 215`).

## 3. Defects this spec fixes

| # | Defect | Where | What the card promises instead |
|---|---|---|---|
| S-1 | Title search order is TMDb then OMDb regardless of settings (#287) | `_search_kind`, `_search_title` | Step 3 Movies order |
| S-2 | TheDiscDB IMDb handover resolves through TMDb only; OMDb-only installs lose the exact match although `OMDBClient.lookup_by_imdb_id` exists | `identify_from_imdb` | Step 2 and Step 3; empty list means no call |
| S-3 | 1337server CRC64 lookup is an undisclosed, non-disableable online call before every ranked source | `_identify_video:122-130` | Offline promise; nothing on the card names it |
| S-4 | `OMDB_API_KEY` env override bypasses the Keys tab and the "Needs key" chips | `main.py:202`, `dispatcher.py:76-78` | Key status on the card |
| S-5 | Volume label is searched even when the `label` hint is ignored; a miss titles the job with the raw label | `_identify_video:145-154`, `ripper.py:712-725` | "Ignore the volume label" acceptance criterion |
| S-6 | Manual search and IMDb lookup choose by `metadata_provider`, which #258 PR 1 deletes | `routers/metadata.py:79, 122` | Search card select per type |
| S-7 | CD identification has no switch and no list | `_identify_cd` | Step 3 Music list, Step 4 Music trust |
| S-8 | Provider identity is spelled four ways (`_PROVIDER_BY_LABEL_PREFIX`, `SearchProvider`, config literal, `MetadataResult.provider`) | dispatcher, metadata router, config router | one id per source (#313) |
| S-9 | Movie-first vs TV-first is a disc heuristic inside the provider walk | `_identify_video:156-172` | Lists are per media type; the disc picks which type is tried first |
| S-10 | `_with_tmdb_ids` enrichment is TMDb-only; TVmaze/TVDB series hits (PR 2b) need the same id fan-out | `_with_tmdb_ids` | Poster and episode stage for non-TMDb hits |

## 4. Decisions

Each is the recommended option from the review. Override at spec review if you disagree.

- **D-1 Exact-id handover walks the ranked list (S-2, "Option A").** When TheDiscDB
  returns an IMDb id, ARM asks the first enabled source for the matched media type that
  offers an IMDb lookup, in rank order. If no enabled source offers one, no online call is
  made and the job is identified from the TheDiscDB release metadata (title, year, kind).
  The Step 2 copy becomes: "…When it matches, it wins over the disc's labels, and ARM
  confirms the title with the first online source below."
- **D-2 The community database becomes a Step 2 row (S-3).** New boolean
  `crc64service_enabled` (default true, so behaviour is unchanged). Step 2 gains a second row,
  "ARM community database (CRC64)", with a `DVD` chip, under TheDiscDB. Its help text says
  it sends the disc's CRC64 fingerprint to the ARM project's server.
- **D-3 No key outside the Keys tab (S-4).** The `OMDB_API_KEY` environment override is
  removed outright in PR 0, together with the `Settings.OMDB_API_KEY` field and the
  `.env.example` line. No seeding: the Keys tab is the only place a key comes from.
- **D-4 Ignoring the volume label means ignoring it everywhere (S-5).** The dispatcher
  adds the normalized label as a search candidate only when `label` is in
  `enabled_hint_sources(cfg)`. On a miss, the job title is the hint title if there is one,
  else the TheDiscDB release title, else the raw volume label (the raw label is the last
  resort only, so a disc with every hint off still has a name).
- **D-5 CDs get a list but no new flow (S-7).** `music_sources` holds `musicbrainz` only.
  Step 1 shows CDs as "Disc ID (track layout)" with a `CD` chip, not as a volume label. The
  CD path becomes a walk over `sources_for(cfg, "music")` with the disc-id capability, so an
  empty list disables online lookup for CDs like any other type.
- **D-6 Kind order stays a heuristic (S-9).** `prefer_tv` and `title_hint_is_tv` decide
  whether movie or TV is tried first. The lists are per media type. The design copy says so.
- **D-7 Field names follow the #258 comments.** `movie_sources`, `episode_sources`
  (existing), `music_sources`; `search_provider_movie`, `search_provider_tv`,
  `search_provider_music`; `movie_auto_apply`, `episode_auto_apply` (existing),
  `music_auto_apply`; `crc64service_enabled`. `metadata_provider` is dropped.
- **D-8 Migration seeds order from the old setting.** `movie_sources` is seeded as the
  former `metadata_provider` first, then the other movie source, so no install changes
  behaviour on upgrade. `search_provider_movie` is seeded from `metadata_provider`;
  `search_provider_tv` from `metadata_provider` as well (the TV search box used it before); `search_provider_music` to
  `musicbrainz`.
- **D-9 Setup wizard.** The "metadata" wizard step is renamed Identification and shows the
  three API keys and the MakeMKV key only (`setup_step="identification"` on those fields).
  Ranked lists, trust and Step 2 rows keep their defaults and are not in the wizard.
- **D-10 Trust versus the review gate.** Ripping › Review (`hold_for_review`) is the
  global gate and still wins. "Auto-apply" per media type only decides whether a confident
  match is applied without a hold when the review gate is off. The Identification tab's
  help text names the Review setting so the interplay is visible.
- **D-11 Tolerance help text keeps its rules.** The episode tolerance field keeps the
  range (1–1800 s), the default (300 s) and the narrowing rule (tightened to a tenth of the
  runtime, never below 60 s).

## 5. Design

### 5.1 `identity/sources/online.py`: the source protocol

```python
class OnlineSource(Protocol):
    id: str                      # "tmdb" | "omdb" | "tvmaze" | "tvdb" | "musicbrainz" | "arm_server"
    media_types: frozenset[str]  # {"movie", "tv"} | {"tv"} | {"music"}
    requires_key: str | None     # Config key the UI chip and configured() both read
    def configured(self, cfg: Config) -> str | None: ...   # reason it cannot run, or None
    # Capabilities. Each is optional; an adapter that lacks one is skipped for that step.
    async def search_title(self, kind, title, year) -> MetadataResult | None: ...
    async def search_candidates(self, kind, title, limit) -> list[MetadataResult]: ...  # Search card
    async def lookup_imdb(self, imdb_id) -> MetadataResult | None: ...                  # D-1, /lookup
    async def lookup_disc_id(self, disc_id) -> MetadataResult | None: ...               # CDs
    async def lookup_fingerprint(self, algo, value) -> MetadataResult | None: ...       # D-2
    async def search_show(self, title, year) -> ShowHit | None: ...                     # PR 2b
```

Adapters wrap the existing clients unchanged: `TMDBClient`, `OMDBClient`,
`MusicBrainzClient`, `ArmServerClient`, and the TVmaze and TVDB HTTP already used by the
episode providers. The adapter is the only place that knows which client method implements
which capability and which key it needs. `MetadataResult.provider` is always `source.id`;
`_PROVIDER_BY_LABEL_PREFIX` goes away.

Capability presence is checked with `hasattr`-style helpers (`has_capability(source,
"lookup_imdb")`) so a walk skips sources that cannot serve a step rather than failing.

### 5.2 Registry accessors (extend `identity/sources/registry.py`)

- `ONLINE_SOURCES: dict[str, OnlineSource]`, built once at app start with the shared
  `httpx` client, the way `stage_runner.build_providers` builds episode providers.
- `sources_for(cfg, media_type) -> tuple[OnlineSource, ...]`: the operator's list for that
  type (`movie_sources`, `episode_sources`, `music_sources`), in order, deduplicated, with
  sources dropped when `configured(cfg)` returns a reason. **This is the only function that
  decides order or enablement.**
- `search_source(cfg, media_type) -> OnlineSource | None`: the Search card's select for that
  type (`search_provider_*`), or None when it is unconfigured. The Search card's select
  offers every source in `known_source_ids(type)`; an unkeyed choice is rejected by config
  validation with the "Needs key" reason.
- `fingerprint_sources(cfg) -> tuple[OnlineSource, ...]`: Step 2 sources by their switches:
  `arm_server` when `crc64service_enabled`. TheDiscDB stays on its own path (step 3) because it
  produces claims, not a `MetadataResult`.
- `known_source_ids(media_type) -> tuple[str, ...]`: the validation list for
  `routers/config.py` and the `enum_values` of the three ranked fields, replacing the
  literals that #313 flags.

### 5.3 Consumers

| Consumer | Today | After |
|---|---|---|
| `dispatcher.identify` (video) | branches on disc type, hard-codes clients | kinds in heuristic order (D-6); for each kind, walk `sources_for(cfg, kind)` calling `search_title`; first hit wins; empty list makes no call |
| `dispatcher.identify` (CD) | MusicBrainz direct | walk `sources_for(cfg, "music")` with `lookup_disc_id` (D-5) |
| `dispatcher.identify_from_imdb` | TMDb `/find` only | walks `sources_for(cfg, kind, registry)` with `lookup_imdb`; `kind` from the TheDiscDB release; no capable source → the route identifies from the release metadata with provider `thediscdb` (D-1) |
| `dispatcher._identify_video` CRC64 | unconditional | `fingerprint_sources(cfg)` with `lookup_fingerprint` (D-2) |
| `dispatcher._identify_video` label candidate | always | only when `label` is in `disc_hint_sources`; the label year still narrows the hint; miss title = hint title → release title → raw label (D-4) |
| `dispatcher.__init__` | env OMDb override | removed in PR 0 (D-3) |
| `_with_tmdb_ids` | TMDb only | renamed `fill_external_ids`: given any hit with an IMDb id, asks each enabled source of that type with `lookup_imdb` for its own id until TMDb and TVDB ids are filled (S-10) |
| `routers/metadata.py search` | `metadata_provider` | `provider` param validated against `known_source_ids(type)`; default `search_source(cfg, type)`; uses `search_candidates` (S-6) |
| `routers/metadata.py lookup` | `metadata_provider` | walks `sources_for(cfg, type)` with `lookup_imdb`; new `type` param, default `movie` |
| `routers/metadata.py music/*` | hard-coded | `search_source(cfg, "music")`; `/music/{release_id}` keeps its MusicBrainz shape because the release detail endpoint is MusicBrainz-specific |
| `stage_runner.build_providers` | own list | unchanged in this spec; episode providers keep their protocol and share `configured()` with the TV adapters through one helper |
| `routers/config.py` | literal validation | each ranked list and each `search_provider_*` validated against `known_source_ids`; the #219 re-resolve hook fires for `movie_sources` and `music_sources` too |
| UI `RankedListField` chips | `#Metadata/{key}` | `keyTab` resolves across groups so chips link to `#Keys/{key}` (the #258 comment on #220) |

### 5.4 Data model (migration 0045)

| Column | Type | Default | Seeded from |
|---|---|---|---|
| `movie_sources` | ARRAY(str) | `{tmdb,omdb}` | `metadata_provider` first, the other second (D-8) |
| `music_sources` | ARRAY(str) | `{musicbrainz}` | default |
| `search_provider_movie` | str | `tmdb` | `metadata_provider` |
| `search_provider_tv` | str | `tmdb` | `metadata_provider` |
| `search_provider_music` | str | `musicbrainz` | default |
| `movie_auto_apply` | bool | true | default |
| `music_auto_apply` | bool | true | default |
| `crc64service_enabled` | bool | true | default |
| `metadata_provider` | dropped | | |

Enums stay VARCHAR and are validated in the app layer. The downgrade restores
`metadata_provider` from `search_provider_movie` (lossy).

`movie_auto_apply` and `music_auto_apply` exist as columns and in the view from PR 1 but are hidden from the editable surface until PR 3 reads them.

`config_metadata.py` gains the matching `ConfigFieldMeta` entries: ranked lists use
`enum_values` from `known_source_ids` and `enum_requires` for keyed sources; the three
`search_provider_*` fields are enums with the same `enum_requires`; the Keys-tab fields are
retagged `setup_step="identification"` (D-9).

### 5.5 Error handling

- A source that raises or times out is logged with its id and skipped; the walk continues.
  Per-source and per-dispatch timeouts (`PROVIDER_TIMEOUT_SECONDS`, `DISPATCH_TIMEOUT_SECONDS`)
  are unchanged.
- A ranked list naming an unknown id is rejected on write and ignored on read, with a
  warning, so a downgraded binary never crashes on a newer row.
- A source whose key disappears after it was ranked is skipped by `configured()`, and the UI
  shows the "Needs key" chip from the same `requires_key`.

## 6. Sequencing (replaces #258's PR list from PR 2 onward)

0. **PR 0 · Registry and dispatcher walk, no behaviour change.** Adapters, `sources_for`
   reading a built-in default order equal to today's (`tmdb, omdb` for movie and TV /
   `musicbrainz`), the dispatcher rewritten as walks, the metadata routes reading the
   registry (`search_source` maps `metadata_provider` until PR 1 replaces it),
   `_PROVIDER_BY_LABEL_PREFIX` removed. Closes S-8.
1. **PR 1 · Model and metadata**, as in #258, plus `crc64service_enabled`
   (D-2, D-7, D-8, D-9). Migration 0045. OpenAPI snapshot and TS types regenerated.
2. **PR 2 · Read the columns.** `online_source_ids` reads the TV list; exact-id walk (D-1); label
   gate (D-4). CRC64 gate, CD walk and the re-resolve hook landed in PR 1. Closes #287.
3. **PR 2b · Series search.** `search_show` on the TVmaze and TVDB adapters;
   `fill_external_ids` (S-10).
4. **PR 3 · Auto-apply hold path**, as in #258, with D-10's precedence.
5. **PR 4 · Docs.** `02-job-lifecycle.md` gains the table in §2; the Identification tab help
   text, including D-10 and D-11.

The UI tab and card land with PR 1 (fields) and PR 2 (behaviour), as #258 already plans.

## 7. Tests

| Suite | Today | Change |
|---|---|---|
| `tests/test_dispatcher.py` | 35 | rewritten around fake sources: same assertions on outcomes, plus order, skip-unconfigured, empty-list-no-call, exact-id walk, label gate, CRC64 gate |
| `tests/test_ripper_router.py` | 126 | the four `test_identify_thediscdb_*` tests and `test_rip_start_applies_stored_thediscdb_claims_to_new_tracks` follow D-1; the two miss-title tests follow D-4 |
| `tests/test_metadata_router.py` | none | new: provider validation, default from `search_provider_*`, lookup walk with `type`, music default |
| `tests/test_config_router.py` | existing | ranked-list and `search_provider_*` validation, re-resolve on the new lists, env-key seeding at boot |
| `packages/arm_common/tests/test_config_metadata.py` | existing | `enum_values` come from `known_source_ids`; `setup_step` retag |
| migration test | existing pattern | 0045 upgrade seeds per D-8; downgrade restores `metadata_provider` |

All stay zero-infra: adapters are faked at the `OnlineSource` boundary, not at HTTP.

## 8. Acceptance criteria

1. With Movies ranked `omdb, tmdb` and both keyed, a DVD title search calls OMDb first and
   never calls TMDb when OMDb hits.
2. With Movies empty, no title search HTTP call is made for a movie-shaped disc; the job goes
   to AWAITING_USER_ID when `block_on_miss` is on.
3. With TMDb unchecked and a TheDiscDB match carrying an IMDb id, the exact match resolves
   through OMDb; with every movie source unchecked it resolves from the release metadata
   without an online call.
4. With `label` removed from disc hints, the volume label is neither searched nor used as the
   miss title while a hint title or release title exists.
5. With `crc64service_enabled` off, no CRC64 request is made.
6. With `OMDB_API_KEY` set in the environment and the saved key blank, OMDb is not called and
   the "Needs OMDb key" chip shows: the variable has no effect.
7. A Search card select set to an unkeyed source is rejected by `PATCH /api/config` with the
   "Needs key" reason.
8. Upgrading a row with `metadata_provider = omdb` yields `movie_sources = {omdb,tmdb}` and
   `search_provider_movie = omdb`.

## 9. Design changes for v4.2

- Step 2: second row "ARM community database (CRC64)" with a `DVD` chip (D-2).
- Step 1: CD row reads "Disc ID (track layout)" with a `CD` chip (D-5).
- Step 2 copy ends "…and ARM confirms the title with the first online source below." (D-1).
- Keys tab help: keys live here only; environment variables are read once at boot (D-3).
- Trust step help names Ripping › Review as the global gate (D-10).
- Tolerance help restores the range and the narrowing rule (D-11).
- Repo mirror `2026-10-12-identity-settings-design.md` Part 5 is updated to v4.2 strings
  ("Disc text ignored", "No sources on", "Waits for review", Preview panel) and its §9a is
  struck.

## 10. Open items

- Whether the TV adapters should absorb the episode providers later (one class per source)
  or stay side by side. Not decided here; §5.3 keeps them separate.
- Whether `arm_server` should also be offered as a ranked movie source for title search.
  It has no title search today, so it is Step 2 only.
- The ripper's abcde driver sets `CDDBMETHOD="musicbrainz"`, so a CD rip queries MusicBrainz
  for tags on its own, outside the Backend. An empty Music list stops the Backend's disc-id
  lookup but not that tagging call; the Step 3 Music help text should say so, or PR 2 should
  pass the setting through to the ripper.
- Resolved in PR 2: the automatic TV title order is `episode_sources` (no OMDb row); OMDb series search remains available from the job page's TV search select. TVmaze/TVDB title search lands in PR 2b; until then a TV list naming only them yields no automatic TV title search.
- Resolved in PR 1: `search_provider_tv` offers `tmdb, omdb` (the providers that can answer today); TVmaze and TVDB join the select in PR 2b with their adapters. PR 1 already reads `movie_sources` and `music_sources` for the dispatcher's order and honours `crc64service_enabled`.
