# Automation gap analysis: unattended rip → transcode

Status: draft, 2026-09-12. Written against `integration/all-prs` at `65a39959`
(which includes the pre-rip session parking fix, cherry-picked from
`feat/media-identification`). Evidence is cited as `file:line` on that tree
or as observations from the live stack on hifi-server.

The question this answers: **what stands between ARM v3 today and a disc
going in one end and a correctly named, correctly encoded file coming out
the other, with no clicks in between**, across DVD, Blu-ray, 4K UHD,
multi-title discs and TV box sets. A second section audits the free-form
JSON bags (chiefly `jobs.metadata_json`) and recommends a schema.

## 1. The automated path as it exists

```
insert ──▶ scan ──▶ identify ──▶ [hold/review] ──▶ rip-start ──▶ rip ──▶ rip-complete ──▶ auto-apply ──▶ dispatch ──▶ transcode
            │          │                              │                        │
            │          │ miss + block_on_miss         │ preset = per DISC TYPE │ drain parked apps (new)
            │          └──▶ awaiting_user_id          │ (never the session's)  │ then drive.default_session_id
            │               (needs a human)           │                        │ only if auto_transcode_on_idle
            └ disc_type ∈ {dvd, bluray, cd, data}     └ Track rows created HERE
```

Facts that drive everything below:

| Fact | Where |
|---|---|
| Rip preset is chosen by disc type only: DVD and Blu-ray → `rpr_builtin_movie_archive` (every title), CD → music standard, data → copy. The session's `rip_preset_id` is never read at rip time; only its `min_length_seconds` override is, and only when the rip was started with a session chosen up front. | `routers/ripper.py:65` (`_DEFAULT_RIP_PRESET_BY_DISC_TYPE`), `rip_start` |
| Track rows are created at rip-start (or at identify when `hold_for_review` is on). Nothing before that has tracks. | `rip_start`, `_persist_review_tracks` |
| Auto-apply after a rip needs both `drives.default_session_id` and `config.auto_transcode_on_idle=true`. The flag has no idle logic; it is a plain enable switch. Default is off. | `auto_session.py:resolve_effective_session_id`, `config_metadata.py:167` |
| The scan classifies discs as `dvd`/`bluray`/`cd`/`data`/`unknown`. UHD is `bluray`. Titles carry duration, chapters, size and source file; no resolution, no HDR flag. | `enums.DiscType`, `schemas/ripper.py:ScanTitle`, `scan/makemkv.py:63` |
| Identify searches TMDB movies, then TV, then OMDb, then the ARM 1337 server. The result has a `kind` (movie/tv/music) that is **not stored on the job**. Jobs have no `media_type` column. | `metadata/dispatcher.py:112`, `metadata/base.py:26`, `routers/ripper.py:471` |
| The session's `media_type` is never checked against the disc. A movie session auto-applied to a CD finds zero video tracks. | `transcode_apply.py:_track_kinds_for_media`, `auto_session.py` |
| Multi-title selection rules: `main_feature` = longest title ≥ 45 min (else longest); `all_tracks` = everything ≥ 60 s; `archive` = everything; `custom` = declarative filters. MakeMKV itself drops titles < 120 s. | `track_selection.py:4-5,68-83`, `ripper/config.py:38` |
| TV naming is deliberately mechanical: `{show} ({year})/Season {season}/{show} - S{season}D{disc}T{track} …`. No auto `SxxEyy`. Episode fields on tracks are filled only by TheDiscDB (`Episode` items) or operator edits. | `seeders.py` TV session, `thediscdb/matcher.py:129-142`, `docs/arch/02-job-lifecycle.md:207-221` |
| On hifi-server today: `auto_rip_on_insert=true`, `block_on_miss=true`, `hold_for_review=false`, `auto_transcode_on_idle=false`, drive `default_session_id=NULL`. Nothing happens after a rip without a click. | live DB, 2026-09-12 |

### 1.1 How a disc gets identified

One identity per disc, produced by this ladder. It never learns that a disc
has many titles or that a Blu-ray is 4K.

| Step | What happens | Where |
|---|---|---|
| Scan | MakeMKV info yields the disc-type string, the volume label and per-title duration / chapters / size / source file. The ripper also reads the raw device with PyCdlib for two fingerprints: pydvdid CRC64 (DVD only, from `VIDEO_TS`) and the TheDiscDB content hash (MD5 over file sizes: `BDMV/STREAM/*.m2ts` for BD and UHD, `VIDEO_TS/*` for DVD). | `scan/makemkv.py`, `scan/disc_probe.py`, `scan/thediscdb_hash.py` |
| Dedupe | Any shared fingerprint on a non-terminal job for the drive reuses that job and skips identification. | `disc_dedupe.py` |
| TheDiscDB | Content hash → local snapshot. On a hit the per-title map (type `MainMovie` / `Episode` / extras, title, season, episode) is stored and the release's IMDb id goes to TMDB `/find` for an exact movie or TV identity. | `routers/ripper.py:425-440`, `thediscdb/matcher.py`, `metadata/tmdb.py:153` |
| 1337 server | DVD only, by CRC64. Returns title, year, IMDb id, `video_type`, `multi_title`. | `metadata/arm_server.py` |
| Volume label | Label normalised (NTSC, `_BD`, Blu-ray branding stripped; underscores to spaces; trailing year extracted) then TMDB movie search → TMDB TV search → OMDb movie. | `metadata/dispatcher.py:95-130` |
| Miss | `block_on_miss` parks the job at `awaiting_user_id`; otherwise it proceeds under the volume label with `unidentified=true`. | `routers/ripper.py:490-497` |

**Multi-title disc.** The job gets one title and year; only track selection
sees the title count. With a TheDiscDB match every title gets a role, episodes
get names and numbers, and non-feature titles are excluded. Without one, a box
set label such as `WEST_WING_S3_D2` is searched as "WEST WING S3 D2", movie
search runs first, and the usual outcome is a park for a human. A double
feature identifies as whichever film the label names; per-track title, year,
IMDb id and episode fields are editable afterwards (`TrackEditRequest`).

**4K UHD Blu-ray.** MakeMKV reports "Blu-ray disc", so it is `bluray` with
nothing marking UHD. No CRC64, so no 1337 lookup. The TheDiscDB hash works
without decryption and TheDiscDB keeps separate releases per format, so a UHD
disc matches its UHD release, but ARM reads only the release's slug,
contributors and external ids and discards the format. Without a match the
label search runs; `UHD` / `4K` tokens are not in the branding strip list.
Reading the disc at all needs a UHD-friendly drive and a live MakeMKV beta.

## 2. Gap register

Severity: **critical** = blocks unattended operation or silently loses work;
**major** = wrong output without a human; **minor** = confusing or dead code.
IDs are stable so they can be referenced from issues and PRs.

### Session routing

| ID | Sev | Gap | Evidence | Proposal |
|---|---|---|---|---|
| G-01 | critical | The session's rip preset is ignored. "Movie to Plex 1080p" (main feature) still rips every title, then transcodes every title into the movie folder as `Track NN` files; Plex shows them as versions. | `ripper.py:65`, `rip_start`; live job `job_01M1TGZ8…` (4 titles: 76 m, 67 m, 4 m, 3 m) | `rip_start` resolves the effective session via `resolve_effective_session_id` and uses its `rip_preset_id`; falls back to the disc-type default only when no session is known. |
| G-02 | critical | One default session per drive, regardless of what was inserted. A TV box set, a CD and a UHD movie all get the same session. | `drives.default_session_id`, `maybe_auto_apply_session` | Replace with a routing table keyed by (`media_type`, `disc_type`) with a fallback chain; keep the drive default as an override. Needs G-03. |
| G-03 | critical | The identified kind (movie/tv/music) is discarded. Nothing downstream can tell a TV disc from a movie. | `ripper.py:471` merges `result.payload` but drops `result.kind` | Add `jobs.media_type` (VARCHAR, app-validated per repo rule) set at identify and editable at resolve. |
| G-04 | major | Media-type mismatch produces an empty application. On a ripped job with zero candidate tracks the fan-out still creates a `queued` application with no tasks; the orphan sweep on integration fails it after 90 s with a "crash/eviction" message. | `auto_session.py:_fan_out_tasks_for_application`, `transcode_dispatcher.py:sweep_orphaned_applications` | Auto-apply checks `session.media_type` against `job.media_type` and skips with a WARN; manual apply returns 422 with a clear reason when no track qualifies. |
| G-05 | done | A session applied or resolved before rip-start was promoted to an empty queued application and lost. | fixed in `35ed68d8` / `65a39959` | Parked until rip-complete; `skipped_reason="no_tracks"` on resolve. |
| G-06 | minor | "Auto-transcode when idle" has no idle semantics. | `config_metadata.py:170` | Relabel to "Auto-apply the drive/route default session after each rip", or implement real idle gating and keep the name. |
| G-07 | minor | Manual applies record no user. | `routers/jobs.py:998` passes `created_by_user_id=None` | Pass the authenticated user id. |
| G-08 | major | Overwrite eviction matches on `output_path` only, across jobs. Re-ripping a disc and applying with overwrite deletes the older job's finished tasks and application. Observed today: the 05:09 application on `job_01M1TGZ8…` vanished when the older duplicate rip was re-applied at 13:56. | `auto_session.py:_evict_colliding_tasks` | Scope eviction to the same job by default; cross-job overwrite becomes an explicit confirm with the other job named. |
| G-09 | minor | `JobStatus.RIPPED_AWAITING_IDENTIFY` is defined and accepted by resolve but never assigned. | `enums.py:80`, `routers/jobs.py:877` | Either assign it in placeholder rips (rip-complete on an `unidentified` job) or delete it. |

### Disc types

| ID | Sev | Gap | Evidence | Proposal |
|---|---|---|---|---|
| G-10 | major | UHD is indistinguishable from Blu-ray. No per-title resolution or HDR information reaches the backend, so no rule can pick a 2160p session or an HDR-aware preset. | `DiscType`, `ScanTitle` | Extend `ScanTitle` with `width`, `height`, `hdr` (from MakeMKV's per-title video stream info, `SINFO` lines), keep `disc_type=bluray`, and route on `height >= 2160`. |
| G-11 | major | The only 2160p preset is software HandBrake `H.265 MKV 2160p60 4K` with `hw_preference=None`. HDR10 / Dolby Vision passthrough is unverified; a 4K encode on CPU is hours per title. | `seeders.py:248-255` | Add a `tpr_builtin_plex_2160p_hevc_gpu` (NVENC 10-bit) and verify HDR metadata survives; document DV as unsupported unless proven. |
| G-12 | note | UHD needs a friendly drive and an unexpired MakeMKV beta; BD/UHD silently fail (`MSG:5021`) when the beta lapses. Not a code gap, but an unattended run has no way to notice except failed rips. | `docs/ops/makemkv.md:33-47` | Surface MakeMKV expiry as a health check and notification. |

### Multi-title and TV

| ID | Sev | Gap | Evidence | Proposal |
|---|---|---|---|---|
| G-13 | major | Main-feature detection is "longest title ≥ 45 min". Play-all titles, alternate cuts and extended editions defeat it; there is no play-all heuristic despite the data-model doc promising one. | `track_selection.py:71-74`, `docs/arch/04-data-model.md:111` | Add a play-all guard (a title whose duration ≈ sum of others), prefer TheDiscDB `MainMovie` when matched, and expose `edition` from TheDiscDB in naming. |
| G-14 | major | TV `{season}` and `{disc}` are read from free-form metadata keys, while resolve stores disc number in the `disc_number` column. The two can disagree and the template silently renders an empty segment. | `transcode_apply.py:_build_track_ctx`, `routers/jobs.py` resolve | Read `{disc}` from `job.disc_number`; promote `season` to a column (see §3). |
| G-15 | major | No episode numbering for TV without TheDiscDB. Volume-label hints (`WEST_WING_S03_D02`) are not parsed; every TV rip without a match lands in `awaiting_user_id` for season and disc. | `docs/arch/02-job-lifecycle.md:207` (by design), `identify` | Parse `S\d+` / `D\d+` from the volume label as defaults; keep the "no guessed `SxxEyy`" rule for episodes. |
| G-16 | latent | With `hold_for_review` on, Track rows exist before the rip. The new "no tracks" guard does not fire in that state, so a session applied then would fan out tasks against files that do not exist yet. Unreachable today because apply rejects `awaiting_review` with 409. | `_persist_review_tracks`, `auto_session._APPLY_OK_STATUSES` | Gate fan-out on `job.status ∈ {ripped, ripped_partial}` rather than on track presence when the parking logic is next touched. |
| G-17 | major | Music CDs are routed like video: the drive default (a movie session) yields G-04. Music sessions exist but nothing selects them. | `seeders.py` music sessions, G-02 | Covered by the routing table (G-02) once `media_type` exists. |

### Identification

| ID | Sev | Gap | Evidence | Proposal |
|---|---|---|---|---|
| G-22 | major | A TheDiscDB match carries the release format (the disc's own record says whether it is DVD, Blu-ray or UHD), and ARM discards it. This is the cheapest UHD signal available and it is already in memory at identify time. | `thediscdb/matcher.py` reads only `Slug`, `Contributors`, `ExternalIds` | Read the format from the matched release and stamp it on the job (feeds G-10 routing). Verify the upstream field name against the data repo. |
| G-23 | minor | Volume-label normalisation strips NTSC, `_BD` and Blu-ray branding but not `UHD` / `4K` / `2160`, so a label like `MOVIE_UHD` reaches TMDB with the suffix attached. | `metadata/dispatcher.py:_normalize_volume_label` | Add the tokens to the strip list; also record "label mentioned UHD" as a weak format hint. |
| G-24 | major | Fuzzy identify searches TMDB movies before TV. A show sharing a name with a film (or a box-set label that reduces to a common phrase) identifies as the film with no warning. | `metadata/dispatcher.py:112-115` | When the scan looks like a box set (many titles of similar episode length, or an `S\d+` / `D\d+` hint in the label), search TV first; otherwise keep movie first. Surface both candidates when both hit. |
| G-25 | note | The TheDiscDB snapshot indexes only the `movie` and `series` trees; `sets` (box-set collections, multi-film releases) is skipped, so exactly the discs that most need per-title help get none. | `thediscdb/snapshot.py:39` | Index `sets` once its grouping shape is handled. |
| G-26 | note | Identity is one-per-job. A double feature or a compilation disc identifies as one film; the other titles can only be corrected by editing per-track fields after the fact. Whether the UI offers a per-track title search was not checked. | `TrackEditRequest`, `_build_track_ctx` per-track overrides | Add a per-track "identify this title" action that runs the same ladder against a typed name and writes the track's identity fields. |

### Unidentified discs and operations

| ID | Sev | Gap | Evidence | Proposal |
|---|---|---|---|---|
| G-18 | note | `block_on_miss=false` (placeholder mode) rips and transcodes under the volume label, and ARM never renames afterwards. Correct per design, but an unattended run needs the operator to know this trade-off. | `ripper.py:495-497`, `02-job-lifecycle.md` | Keep `block_on_miss=true` as the unattended default; document placeholder mode as "you will rename". |
| G-19 | verify | `rip.needs_user_input` is emitted on an identify miss. Whether the notification catalog exposes it (so an unattended operator is paged) was not verified in this pass. | `ripper.py:518`, `notifications/catalog.py` | Confirm it is in the catalog; if not, add it. |
| G-20 | major | No `/raw` retention is implemented. `default_retention_policy` exists in config (default `keep_forever`) but nothing prunes. Unattended runs fill the raw volume. | grep: only drive pruning exists (`drive_scanner.py`) | Implement `prune_after_session`: when every task derived from a job is terminal, remove `/raw/{job_id}` per policy. |
| G-21 | note | Disc dedupe reuses pre-rip jobs across days (today's job was created 09-06 and ripped 09-12). A ripped disc re-inserted creates a new job whose outputs collide with the old one, which is how G-08 bites. | `disc_dedupe.py` | With G-08 scoped, offer "already ripped on {date}: skip / rip again" on re-insert. |

## 3. Free-form metadata: inventory and schema recommendation

### 3.1 The bags

| Column | Table | Schema today | Who writes | Who reads |
|---|---|---|---|---|
| `metadata_json` | jobs | none (`dict[str, Any]`) | identify (provider payloads), resolve (arbitrary `req.metadata` merge), manual trigger (`pending_session_id`), TheDiscDB matcher, placeholder path | rip-start, auto-apply, naming ctx, TheDiscDB `apply_map`, ui-neu `job-fields.ts`, ui-neu track list (`scan_result`) |
| `overrides_json` | sessions, session_applications | none; docs promise "CRF 22 instead of 20" | UI session editor | only `min_length_seconds` (`ripper.py:91`) |
| `track_filters_json` | rip_presets | **`TrackFilters` Pydantic model** (min/max duration, include/exclude indices) | preset editor | `track_selection.py` |
| `preset_json` | transcode_presets | none; inline HandBrake preset export | preset editor | transcode container (passthrough) |
| `rip_params_json` | drives | none | nothing found | nothing found |
| `payload_json` | events | none | every `hub.emit` | UI, notifications field map |
| `config` | notification_channels | per-channel, validated by channel code | channel editor | listeners |

`track_filters_json` is the pattern that works: a Pydantic model in
`arm_common.schemas`, validated at the API boundary, dumped to JSONB, parsed on
read. Everything else is a dictionary with conventions in comments.

### 3.2 What actually lives in `jobs.metadata_json`

| Key | Written by | Read by | Notes |
|---|---|---|---|
| `scan_result` | identify | rip-start, review tracks, UI | Full `ScanResult` dump. Load-bearing; already has a Pydantic model. |
| `pending_session_id` | identify (from manual trigger) | auto-apply, min-length override, UI | Really a job column in disguise. |
| `unidentified` | identify (placeholder) | UI | bool |
| `dispatch_timeout` | identify | nobody | diagnostic bool |
| `thediscdb` | identify | `apply_map` | `{title→entry map, matched_at}` |
| `season`, `disc` | resolve (UI free-form) | naming ctx (`{season}`, `{disc}`) | Stringified on read; `disc` duplicates the `disc_number` column (G-14). |
| `artist`, `album`, `disc`, `tracks[]` | MusicBrainz provider | naming ctx (`{artist}`, `{album}`, `{track_title}`) | Music only. |
| raw TMDB payload (`id`, `title`/`name`, `overview`, `poster_path`, `genre_ids`, `release_date`/`first_air_date`, `vote_average`, …) | identify | UI (`tmdb_id` via ad-hoc mapping) | Merged at **top level**. |
| raw OMDb payload (`Title`, `Year`, `Type`, `Poster`, `imdbID`, …) | identify | UI | Merged at top level, PascalCase. |
| ARM 1337-server payload (`title`, `year`, `video_type`, `imdb_id`, `tmdb_id`, `multi_title`, `source_type`, …) | identify | UI (`job-fields.ts`), dispatcher kind detection | The only provider whose keys the UI understands. |
| anything at all | resolve `metadata:` body | — | No validation; merged over existing keys. |

### 3.3 Problems this causes

1. **Namespace collisions.** Provider payloads land at the top level next to
   ARM's own keys. TMDB and OMDb use different casing for the same facts;
   re-identifying with a different provider leaves the first provider's keys
   behind (merge never deletes). The bag grows and contradicts itself.
2. **Provider-specific readers.** The UI knows `video_type`, `imdb_id`,
   `multi_title`, `source_type` because the 1337 server emits them; a TMDB
   hit shows nothing for "type" because the kind was thrown away (G-03).
3. **No validation at the boundary.** `POST /resolve` accepts any object and
   merges it. A typo in `seasn` is silently ignored and the TV template
   renders an empty folder segment.
4. **Facts that drive behaviour live next to facts that are decoration.**
   `pending_session_id`, `season`, `disc` and the identified kind steer
   routing and naming; `overview` and `vote_average` do not. Mixing them makes
   both harder to reason about and impossible to index.
5. **The wire contract cannot help.** OpenAPI exposes `metadata_json` as
   `object`, so both UIs hand-roll readers (`job-fields.ts`) and CI's drift
   gate cannot catch a renamed key.

### 3.4 Recommendation: typed core, namespaced raw, columns for behaviour

Yes, it should have a schema. Not a rigid one: a typed core with a
namespaced escape hatch, following the `TrackFilters` precedent.

**Promote to columns** (they drive routing, naming or queries):

- `jobs.media_type` (movie / tv / music / data / iso), set at identify from
  `result.kind`, editable at resolve. Unblocks G-02, G-04, G-17.
- `jobs.season` (int, nullable). `disc_number` already exists; the naming
  context reads both columns (fixes G-14).
- `jobs.pending_session_id` (FK, nullable). It is already treated as a column
  by three readers.

**Define `JobMetadata` in `arm_common.schemas`** and validate on every write:

```python
class ExternalIds(BaseModel):
    imdb: str | None = None
    tmdb: str | None = None
    tvdb: str | None = None
    musicbrainz_release: str | None = None

class Identity(BaseModel):
    provider: Literal["tmdb", "omdb", "arm_server", "musicbrainz", "thediscdb", "manual"]
    external_ids: ExternalIds = ExternalIds()
    poster_url: str | None = None
    overview: str | None = None
    identified_at: datetime

class MusicMeta(BaseModel):
    artist: str | None = None
    album: str | None = None
    disc: int | None = None
    tracks: list[MusicTrackMeta] = []

class JobMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")   # forward-compat, but see below
    scan_result: ScanResult | None = None
    identity: Identity | None = None
    music: MusicMeta | None = None
    thediscdb: TheDiscDBMap | None = None
    flags: JobFlags = JobFlags()                # unidentified, dispatch_timeout
    provider_raw: dict[str, dict[str, Any]] = {}   # keyed by provider name
```

Rules that go with it:

- Identify writes `identity` and stores the raw payload under
  `provider_raw[provider]`; nothing from a provider lands at the top level.
- Resolve accepts a typed `ResolveRequest` (title, year, season, disc_number,
  disc_total, external_ids) and rejects unknown keys with 422. The free-form
  `metadata:` field goes away.
- Readers call `JobMetadata.model_validate(job.metadata_json)` once and use
  attributes. `extra="allow"` is kept for one release so unknown keys from
  older rows are preserved, then tightened to `forbid`.
- The OpenAPI schema gains `JobMetadata`; both UIs regenerate and delete
  their hand-rolled readers.
- One Alembic data migration lifts existing rows: known top-level keys move
  into `identity`/`music`/`flags`, provider-looking keys move under
  `provider_raw["legacy"]`, `season`/`disc` are copied into the new columns.
  v3 is pre-release, so a one-shot migration is acceptable; no dual-read
  period is needed beyond the `extra="allow"` grace.

**Do the same, smaller, for the other bags:**

- `SessionOverrides` model: `min_length_seconds` now; add fields only when a
  reader exists. Stop the docs promising CRF overrides until they do.
- `preset_json`: validate the HandBrake export shape (`PresetList[0]` with
  `PresetName`) at save time so a bad paste fails in the editor, not in a
  transcoder container an hour later.
- `rip_params_json` on drives: unused; drop it or give it a model when the
  first reader appears.
- `events.payload_json`: leave free-form; it is an audit log, not a contract.

## 4. Sequencing

Ordered so each step has a reader for what it adds.

1. **Now (branch `fix/parked-session-survives-rip`, then cherry-pick):** G-01
   rip-start honours the effective session's rip preset; G-06 relabel; G-07
   user id; G-09 remove the dead status.
2. **Data model:** `jobs.media_type`, `jobs.season`, `jobs.pending_session_id`
   columns; `JobMetadata` schema with migration; typed `ResolveRequest`;
   regenerate OpenAPI and both UIs (G-03, G-14, §3).
3. **Routing:** defaults table by (`media_type`, `disc_type`) with drive
   override; media-type check on auto-apply (G-02, G-04, G-17); scope
   eviction to the job (G-08).
4. **Disc awareness:** format from the TheDiscDB release (G-22) and
   `UHD`/`4K` label tokens (G-23) as the cheap signals; `ScanTitle.width/
   height/hdr` from MakeMKV as the general one; UHD routing; NVENC 10-bit
   2160p preset and HDR verification (G-10, G-11); MakeMKV expiry health
   check (G-12).
5. **Multi-title and TV:** TV-first search when the scan looks like a box
   set (G-24); play-all guard and TheDiscDB `MainMovie` preference (G-13);
   volume-label season/disc hints (G-15); status-based fan-out gate (G-16);
   per-track identify (G-26); index TheDiscDB `sets` (G-25).
6. **Operations:** `/raw` retention pruning (G-20); re-insert prompt
   (G-21); confirm `rip.needs_user_input` is notifiable (G-19).

Steps 2 and 3 are the ones that turn "automatic" from a per-drive switch into
a policy the system can apply per disc. Everything after them is refinement.
