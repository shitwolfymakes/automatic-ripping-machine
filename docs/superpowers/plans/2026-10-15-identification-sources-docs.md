# Identification Sources PR 4: Docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the user guide and the developer lifecycle doc in line with the Identification and Keys tabs, the renamed wizard step, the suggestion review, and the registry-driven pipeline; and make the "review gate" wording in the UI match the field it names.

**Architecture:** Docs only, plus one string-consistency fix. The user docs are served inside the app's Help viewer from `docs/user/*.md` (GitHub-style heading anchors), so renamed headings need their cross-links updated. The prose below is the content; implementers transcribe it, adjust only where the code contradicts it, and keep the surrounding file's voice.

**Tech Stack:** Markdown; vitest/arm_common pytest only for Task 3's string fix.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` §6 item 5 ("`02-job-lifecycle.md` gains the table in §2; the Identification tab help text, including D-10 and D-11"), §10 (label-hint note for the Step 1/Advanced help), D-3, D-10, D-11. Branch: `feat/identification-sources-docs` from `feat/identification-sources-ui` (PR #368).

## Global Constraints

- **Voice.** Match each file's existing voice: second person, short sentences, bold for UI names (`**Settings, Keys**`), tables for settings, and the files' own spaced-dash habit (` — `) at about their current rate in prose you add; do not rewrite untouched paragraphs. Avoid the AI-writing tells the humanizer skill lists: no "not X but Y" contrasts, no one-line closers that restate, no forced triads, no bold labels with colons on every list item, no "crucial / robust / seamless / landscape" filler, no chat residue. State facts; the docs do not sell.
- **Facts (from the code on this branch; do not contradict).** Field labels and defaults: `TheDiscDB disc map` (`thediscdb_enabled`, on), `ARM community database (CRC64)` (on, DVDs only, no key), `Movie sources` TMDb, OMDb; `Episode sources` (shown as **TV shows**) TMDb, TVmaze, TVDB; `Music sources` MusicBrainz; `Match tolerance (seconds)` 300, range 1–1800, narrowed to a tenth of the episode's runtime and never below 60 s; `Apply confident matches` for Movies, TV shows and Music, all on; Advanced `Ignore the disc title metadata` / `Ignore the volume label`, both off; `Search movies with` TMDb or OMDb, `Search TV with` TMDb, OMDb, TVmaze or TVDB, `Search music with` MusicBrainz. Keys tab: `TMDb API key` (free), `OMDb API key` (1000 requests a day free), `TVDb API key`, `TheDiscDB refresh interval (days)` 7, `MakeMKV key`. Ripping tab labels: `Hold discs for review`, `Review countdown (seconds)` 60, `Block on metadata miss`, `When a disc was ripped before`. The `MusicBrainz user-agent` setting is no longer on the Settings page (not in the field metadata): drop its row.
- **Pipeline facts.** Disc hints (Blu-ray disc title metadata, volume label; the disc's own metadata beats the label; order fixed in code) → TheDiscDB disc map (a match labels titles and picks the main feature; its IMDb id is resolved through the first capable online source in the list; with none, the release names the disc) → for DVDs the CRC64 community database → online sources in the list order, as a movie or a TV show by the disc's shape (several same-length titles read as TV) → trust: applied, or held as a suggestion when the type's switch is off. A CD is matched by its track layout (MusicBrainz disc id). A miss follows `Block on metadata miss`. Keyless and working: TheDiscDB, the CRC64 database, TVmaze, MusicBrainz. Environment variables seed a key once at first boot (name only the variables that exist in `.env.example`; the former `OMDB_API_KEY` override no longer has any effect after boot).
- **Suggestion review facts.** With a type's switch off, the review card and the job page show **ARM found a match** with the title, year and source; **Use this title** applies it (the rip starts, or the review countdown starts when discs are held for review; a paused ripper keeps it held); **Search instead** opens the title search; the disc is held with no countdown until then; **Start rip** without confirming rips a placeholder you name afterwards.
- **Headings and links.** `Configuring-ARM.md` section heading becomes `### Identification and Keys` (anchor `#identification-and-keys`); every link to `#metadata--identification` is updated (`FAQ.md`, `Web-UI.md` if present). The wizard step is **Identification**.
- **Developer doc.** `02-job-lifecycle.md` gains a subsection `### How identify decides` with the table in Task 2, placed right after "A disc that was ripped before", and a one-line note under the state machine that `awaiting_review` (review gate, previously-ripped hold, suggestion hold) sits between `created` and `identified`/`ripping` and is not drawn.
- **String fix (Task 3).** Every help string and card description that says `Ripping › Review first` says `Ripping › Hold discs for review` instead (the field's real label), in `packages/arm_common/arm_common/config_metadata.py` (three auto-apply helps) and `services/ui-neu/frontend/src/lib/components/settings/IdentityCard.svelte` (Step 4 description), with their tests updated.
- Commits carry no attribution trailers.

## Review Focus

1. The FAQ's claim about what works without a key must list exactly the four keyless sources and must not say the CRC64 database is "tried first" for everything (it is DVD-only and after TheDiscDB) (Task 1).
2. The Advanced note "a DVD with no disc title metadata gets no automatic title search" must appear in the Configuring-ARM table (spec §10) (Task 1).
3. The lifecycle table must name the registry functions that exist on this branch (`sources_for`, `fingerprint_sources`, `identify_from_imdb`, `fill_external_ids`, `auto_apply_for`, `suggest_identity`, `source_ranks`, `disabled_source_ids`) and no removed ones (`_with_tmdb_ids`, `metadata_provider`) (Task 2).
4. The renamed heading must not break the Help viewer's anchors: every in-repo link to the old anchor is updated (Task 1 grep).
5. After Task 3, the arm_common test that pins the episode help string must assert the new text verbatim (Task 3).

---

### Task 1: User docs

**Files:**
- Modify: `docs/user/Configuring-ARM.md` (the "Metadata / identification" section), `docs/user/Setup-Walkthrough.md` (§5), `docs/user/Getting-Started.md` (step 5), `docs/user/Web-UI.md` (Settings list; Jobs section), `docs/user/FAQ.md` ("Do I need API keys?")

- [ ] **Step 1: Configuring-ARM.md** — replace the section from `### Metadata / identification` up to `### Rip / transcode behaviour` with:

```markdown
### Identification and Keys

Two tabs cover how ARM names a disc. **Identification** is what ARM reads from
the disc, which services it asks, and when it trusts the answer. **Keys** holds
the API keys those services need.

#### Identification

**Search** picks the service behind the job page's search box, one per media
type: Movies (TMDb or OMDb), TV shows (TMDb, OMDb, TVmaze or TVDB) and Music
(MusicBrainz). A service whose key is not saved cannot be picked.

**Identity** shows the pipeline as four steps, in the order ARM runs them. The
Blu-ray | DVD | CD selector above the summary only changes what the summary
shows; nothing is saved for it.

| Step | Setting | Default | Effect |
|---|---|---|---|
| 1 On the disc | — | — | ARM reads the Blu-ray disc title metadata and the volume label on every disc, and the track layout on a CD. When they disagree, the disc's own metadata beats its label. CD-TEXT is planned. |
| 2 Disc database | **TheDiscDB disc map** | on | Matches the disc itself against a local snapshot of TheDiscDB, labels its titles and picks the main feature. A match beats the disc's labels; ARM then confirms the title with the first online source below. |
| 2 Disc database | **ARM community database (CRC64)** | on | Sends a DVD's CRC64 fingerprint to the ARM project's database and takes its title when it has one. DVDs only, no key. |
| 3 Online lookup | **Movies**, **TV shows**, **Music** | TMDb, OMDb · TMDb, TVmaze, TVDB · MusicBrainz | Tried top to bottom; the first confident match wins. Untick a source to skip it, move it to change the order. A source whose key is not saved shows "Needs … key" and is skipped. With every source unticked, ARM makes no online lookup for that type. |
| 3 Online lookup | **Match tolerance (seconds)** | 300 | How far a track's runtime may differ from an episode's and still match, 1 to 1800. ARM narrows it to a tenth of the episode's runtime and never below 60 seconds. |
| 4 Trust | **Apply confident matches** (Movies, TV shows, Music) | on | With a switch on, a match is applied and the disc rips (or waits in the review gate when **Ripping › Hold discs for review** is on). With it off, the match waits on the job page for you to confirm it and the disc is held with no countdown. The review gate still holds every disc; the switch only decides whether a match is applied without you. |
| Advanced | **Ignore the disc title metadata**, **Ignore the volume label** | off | For collections where the disc's own text is usually wrong. ARM stops reading that hint on every disc; fix a single disc from its job page instead. With the volume label ignored, a DVD with no disc title metadata gets no automatic title search at all. |

A disc with no confident match follows **Ripping › Block on metadata miss**:
held for you to identify, or ripped as a placeholder you name afterwards.

#### Keys

| Setting | Default | Effect |
|---|---|---|
| **TMDb API key** | empty | The Movie Database, free. Names movies and TV shows. Get one at <https://www.themoviedb.org/settings/api>. |
| **OMDb API key** | empty | Open Movie Database, 1000 requests a day free. Get one at <https://www.omdbapi.com/apikey.aspx>. |
| **TVDb API key** | empty | TVDB. TV show titles and episode numbers. Get one at <https://thetvdb.com/api-information>. |
| **TheDiscDB refresh interval (days)** | 7 | How often ARM refreshes its TheDiscDB snapshot from GitHub. |
| **MakeMKV key** | empty | The purchased key or the free monthly beta key. See [MakeMKV](MakeMKV). |

Press **Test** next to a key to check it. Keys live here only: an environment
variable in `.env` seeds a key once at first boot, and after that only what is
saved here is used.

ARM works with no keys at all. TheDiscDB, the CRC64 database, TVmaze and
MusicBrainz need none; a TMDb or OMDb key is what names most movies.
```

Check `.env.example` for the key variables that actually exist and name them in the "environment variable" sentence (for example "`TMDB_API_KEY` in `.env`"); if none seed keys any more, drop that clause. Keep the `MakeMKV` link only if `docs/user/MakeMKV.md` exists (it does on this branch).

- [ ] **Step 2: Setup-Walkthrough.md §5** — replace the section with:

```markdown
## 5. Identification (optional)

Add a free TMDb or OMDb key so ARM can name movies, and press **Test** to
check it. TVDB adds TV episode numbering. TheDiscDB, the ARM disc database,
TVmaze and MusicBrainz need no key. Skip this and ARM still identifies what it
can without a key and names the rest from the disc label for you to confirm.
Later: **Settings, Identification** and **Settings, Keys**.
```

- [ ] **Step 3: Getting-Started.md step 5** — `5. **Identification** (optional). Add a free [TMDb](https://www.themoviedb.org/settings/api) and/or [OMDb](https://www.omdbapi.com/apikey.aspx) key and test it in place. TV shows and music CDs work without one.`

- [ ] **Step 4: Web-UI.md** — in Settings, replace the Metadata bullet with `- **Identification**, **Keys** and **Ripping**: how discs are identified, the API keys, and rip behaviour. Every field is documented in [Configuration § Identification and Keys](Configuring-ARM#identification-and-keys) and [§ Rip / transcode behaviour](Configuring-ARM#rip--transcode-behaviour).` In Jobs, after the Match Episodes paragraph, add:

```markdown
When a media type's **Apply confident matches** switch is off (Settings,
Identification, step 4), a match ARM found waits for you instead of being
applied. The review card on the dashboard and the job page show **ARM found a
match** with the title, year and source. **Use this title** applies it: the
rip starts, or the review countdown starts when discs are held for review.
**Search instead** opens the title search. The disc is held with no countdown
until you do one or the other; **Start rip** without confirming rips a
placeholder you name afterwards.
```

- [ ] **Step 5: FAQ.md** — replace the "Do I need API keys?" answer with:

```markdown
No, but they help. TheDiscDB, the ARM community CRC64 database (DVDs), TVmaze
(TV shows) and MusicBrainz (audio CDs) need no key. A free TMDb key, or an OMDb
key, is what names most movies. Add keys on **Settings, Keys** — see
[Configuration](Configuring-ARM#identification-and-keys).
```

- [ ] **Step 6: Links** — `grep -rn 'metadata--identification\|Find titles\|Settings, Metadata' docs services/ui-neu/frontend/src` must find nothing outside `docs/superpowers`. Run `uv run pre-commit run --files <the five files>`.

- [ ] **Step 7: Commit** — `git commit -m "docs(user): Identification and Keys tabs, the Identification wizard step, confirming a held match"`.

---

### Task 2: Developer lifecycle doc and spec

**Files:**
- Modify: `docs/developers/architecture/02-job-lifecycle.md`, `docs/superpowers/specs/2026-10-14-identification-sources-design.md`

- [ ] **Step 1: Lifecycle note** — under the state machine diagram, after the "Terminal states" paragraph, add: `Not drawn: `awaiting_review` sits between `created` and `identified`/`ripping` for the timed review gate (`hold_for_review`), a previously-ripped hold, and a suggestion hold (next section); `ripped_awaiting_identify` is a placeholder rip waiting for a title.`

- [ ] **Step 2: Lifecycle table** — after the "A disc that was ripped before" section, add:

```markdown
### How identify decides

`POST /api/ripper/identify` (`routers/ripper.py`) runs these steps in order. Every online call goes through the source registry (`metadata/sources.py`, accessors in `identity/sources/registry.py`); `sources_for(cfg, media_type)` is the only place that decides which sources run and in which order.

| Step | Code | Settings |
|---|---|---|
| Fingerprints stored; a re-scan reuses the pre-rip job; an earlier rip of the disc follows the duplicate policy | `identify`, `disc_dedupe.find_reusable_job_for_disc`, `find_previous_rips` | `on_previously_ripped` |
| Disc hints (Blu-ray disc title metadata, volume label) → claims plus a cleaned search title | `pipeline.run_disc_hints(sources=enabled_hint_sources(cfg))` | `disc_hint_sources` (a set; the order is fixed, `bd_title` before `label`) |
| TheDiscDB content-hash match → track claims | the `thediscdb` store lookup, `thediscdb.build_claims` | `thediscdb_enabled` |
| TheDiscDB IMDb id → the ranked sources for the release's kind (`lookup_imdb`); with no capable source the release itself names the disc (provider `thediscdb`) | `dispatcher.has_imdb_lookup`, `dispatcher.identify_from_imdb`, `thediscdb.release_result` | `movie_sources` / `episode_sources` and their keys |
| CD: disc-id walk | `dispatcher._identify_cd` → `sources_for(cfg, "music")` → `lookup_disc_id` | `music_sources` |
| Video: CRC64 fingerprint (DVD) | `fingerprint_sources(cfg)` → `lookup_fingerprint` | `crc64service_enabled` |
| Video: title candidates (the hint title; the volume label only while `label` is enabled) searched per kind in the order the disc's shape suggests | `dispatcher._identify_video`, `_search_kind` → `search_title` | `movie_sources`, `episode_sources`, `disc_hint_sources` |
| External ids filled in (a non-TMDb hit with an IMDb id gets its TMDb id) | `dispatcher.fill_external_ids` | TMDb key |
| Hit: applied, or held as a suggestion when the kind's switch is off; miss: held for identification or ripped as a placeholder | `auto_apply_for`, `identity.apply.apply_identity_result`, `suggest_identity`; `hold_for_review` branch; miss title = BDMT name → release title → raw label | `movie_auto_apply`, `episode_auto_apply`, `music_auto_apply`, `hold_for_review`, `block_on_miss` |
| Episode stage (TV jobs, in the background) | `stage_runner`, `episode_stage` | `episode_sources`, `episode_match_tolerance_seconds`, `episode_auto_apply`, job pin |
| Resolver: claim precedence manual > TheDiscDB > episode match > hints > preset | `pipeline.resolve_job` → `resolver.resolve(tiers, ranks=source_ranks(cfg), disabled=disabled_source_ids(cfg))` | `disc_hint_sources` (enablement), job pin |

The interactive routes read the same registry: `GET /api/metadata/search` validates `provider` against `known_source_ids(type)` and defaults to `search_provider_<type>`; `GET /api/metadata/lookup` takes a `type` and walks `sources_for`; the music routes use `search_source(cfg, "music")`; `PATCH /api/config` validates every ranked list and search select against the registry and rejects a select set to a source whose key is not saved.
```

Verify each named function exists on this branch (`grep -n "def <name>" services/backend/arm_backend -r`) and correct any name that differs; do not invent one.

- [ ] **Step 3: Spec** — §6 item 5: append ` — landed in PR 4` ; §10: add `- Resolved in PR 4: the user guide and the lifecycle doc describe the Identification and Keys tabs and the registry pipeline; the auto-apply help strings name the field by its label, Ripping › Hold discs for review.`

- [ ] **Step 4:** `uv run pre-commit run --files <both files>`; commit `docs(architecture): how identify decides; PR 4 recorded in the spec`.

---

### Task 3: "Review first" says the field's label

**Files:**
- Modify: `packages/arm_common/arm_common/config_metadata.py` (the three `*_auto_apply` helps), `services/ui-neu/frontend/src/lib/components/settings/IdentityCard.svelte` (Step 4 description)
- Test: `packages/arm_common/tests/test_config_metadata.py` (the verbatim episode help assertion and the `"Review first" in help` checks), `services/ui-neu/frontend/src/lib/components/settings/__tests__/IdentityCard.test.ts` (if it asserts the description)

- [ ] **Step 1:** update the tests to the new wording (`Ripping › Hold discs for review still holds every disc.`), run `uv run pytest packages/arm_common/tests/test_config_metadata.py -q` and `npx vitest run src/lib/components/settings/__tests__/IdentityCard.test.ts` → failures.
- [ ] **Step 2:** change the four strings; run the same tests, then `uv run pytest packages/arm_common -q`, `cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint`; pre-commit ruff/ruff-format/mypy on the Python file and eslint/prettier on the Svelte file.
- [ ] **Step 3:** commit `fix(config): auto-apply help names Hold discs for review` (no trailers).

---

## Self-review notes

- Spec §6 item 5 → Tasks 1–2; D-10 interplay and D-11 tolerance rules → Task 1 table rows; §10 label-hint note → Task 1 Advanced row; D-3 → Keys paragraph.
- The settings table rows are the field labels on this branch; Task 3 fixes the one string that named a field by a label it does not have.
- Review Focus 1 → FAQ text; 2 → Advanced row; 3 → Task 2 verification step; 4 → Task 1 Step 6 grep; 5 → Task 3 Step 1.
