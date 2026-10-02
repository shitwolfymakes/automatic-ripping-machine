# TV episode matching in ui-neu: design

Status: draft for review, 2026-10-02.
Branch: `feat/tv-episode-match-ui`, stacked on `feat/identity-settings` (#100).

## 1. Why

The backend can already match a TV disc's tracks to episodes: the episode
stage (`identity/episode_stage.py`) compares track runtimes against TMDb,
TVmaze and TVDB episode lists, applies confident results, stores uncertain
ones as suggestions, and re-runs whenever a job's media type, season, disc
number or show identity changes. Operators are meant to act on it through
four endpoints (`docs/developers/architecture/02-job-lifecycle.md`, "Episode
matching"). **ui-neu uses none of them.**

What the job page has instead:

- `EpisodeMatch.svelte` and `TvdbMatch.svelte`, ported from the v2 UI, call
  `tvdbMatch` / `fetchTvdbEpisodes`, which reject at runtime ("MISSING in
  v3"). Nothing renders them.
- `TitleSearch` searches **movies only**: it calls `/api/metadata/search`
  without `type`, and the backend defaults to `movie`. Its "Match Episodes"
  button never appears because the page passes no `onepisodes` handler.

The case that exposed it: *Kolchak: The Night Stalker* (an untouched BD-50
folder, five ~51 minute episodes and a 9 minute extra) identified as a TMDb
placeholder movie, "Kolchak: The Night Stalker Collection". Identify now
prefers TV for discs like this (integration `065d96d4`), but when it does
get the type wrong there is no way in the UI to pick the series, and when a
job is TV there is no way to see or correct its episodes.

## 2. Goals

1. Flip a job between movie and TV: by picking the right title (movie or
   series) in the title search, or with a quick type switch that keeps the
   current title.
2. A **Match Episodes** tab, shown whenever the job is TV, to:
   - review the automatic placement (which source, applied or suggestion,
     how confident, how many tracks placed);
   - accept a suggestion;
   - re-run with another source, season, disc number or tolerance, preview
     the result against the current placement, then apply and pin it;
   - fix any track by hand, and revert a hand fix.
3. Remove the dead v2 matcher so there is one episode UI.

Non-goals: changes to the matching algorithm, providers, or the existing
Settings > Metadata > TV episodes section.

## 3. Flipping between movie and TV

### 3.1 Title search: Movie / TV toggle

- `TitleSearch` and `TrackTitleSearch` gain a **Movie / TV** toggle that sets
  `type` on `searchMetadata(query, type)` (`GET /api/metadata/search?type=tv`
  already exists; TMDb TV candidates or OMDb `type=series`).
- Default: the job's `media_type` when known; otherwise **TV** when
  `job.looks_episodic` is true (3.3), else Movie.
- Results keep their Movie / Series badge. Picking a result fills the edit
  form as today, with the form's Type following the result's kind.
- Applying a **TV** result goes through the existing `resolveJob` call
  (title, year, `media_type: "tv"`, provider ids, poster) and then switches
  the page to the Match Episodes tab. The backend re-runs the episode stage
  on the media-type / show-id change by itself; the tab shows it arriving
  (4.1).

### 3.2 Job header: quick type switch

- A small **Movie | TV** segmented control in the job header, admin only.
- It changes `media_type` alone through the existing job `PATCH`
  (`JobUpdateRequest`), recorded as the operator's own value; title, year
  and ids are kept. For a job whose title is right but whose type is wrong.
- To TV: the Match Episodes tab appears; the backend re-runs the episode
  stage.
- To Movie: the tab hides. Episode values stay on the tracks but no longer
  drive a movie's naming. When any track carries a **hand-set** episode
  (provenance `manual`), the switch asks for confirmation first, naming how
  many tracks are affected.

### 3.3 `JobView.looks_episodic` (the only backend change)

- `JobView` gains `looks_episodic: bool`: `identity.disc_shape.looks_episodic`
  over the job's stored `scan_result.titles` (false with no scan).
- The rule (at least three 18-70 minute titles within 15% of their median, no
  feature-length title other than a "play all" of roughly their total) is
  the one identify uses, so UI and identify never disagree.
- `identity/disc_shape.py` and its tests currently exist only on
  `integration/all-prs-3` (`065d96d4`). This branch brings that module over
  as-is; the dispatcher half of `065d96d4` stays where it is.
- Regenerate the OpenAPI snapshot and `api.gen.ts`.

## 4. The Match Episodes tab

### 4.1 Visibility and data

- Shown as a tab next to **Search Title** whenever `job.media_type === "tv"`
  (like **Match CD** for CD jobs). Read-only for guests; actions are admin
  only (the write endpoints require a writer).
- Data: `GET /api/jobs/{id}/identity` (`IdentityView`):
  - `sources`: source id -> `SourceSummary` (`status` ok / miss / skipped /
    error, `detail`, `run_at`, `suggestion`, `inputs`, `alternatives`,
    `extra`);
  - `pin`: e.g. `{"episode": "tmdb"}`;
  - `tracks[]`: `TrackIdentityView` (`role`, `season`, `episode_number`,
    `episode_number_end`, `episode_name`, `excluded`, `identity_provenance`,
    `proposals` keyed by source).
- Live: refetch on the existing `job.identity_updated` WS event (emitted
  whenever the stage or these endpoints run the resolver), so a re-run after
  a flip, a season edit or rip start appears without a reload.

### 4.2 What it shows

- A status line: the source whose placement is in effect, whether it was
  **applied** automatically or is a **suggestion** (stored, too uncertain to
  auto-apply), the **pinned** source if any, and "N of M tracks placed".
  Other sources' outcomes are available (e.g. "TVmaze: no match") without
  crowding the line.
- One row per video track: track ref, length, current placement
  (`S01E03 The Vampire`; a span `S01E03-E04`; or **Extra** / **Trailer** /
  **Other**), and where it came from: automatic (source), suggestion, or
  **you** (provenance `manual`).
- A file-name preview from the existing `GET /api/jobs/{id}/naming-preview`.

### 4.3 Actions

1. **Accept a suggestion**: `POST /api/jobs/{id}/identity/match`
   `{source, apply: true}` pins that source and applies its stored
   placement.
2. **Re-run with other settings**: source (`tmdb` / `tvmaze` / `tvdb`),
   season, disc number, and tolerance under "advanced" (1-1800 s).
   - **Preview**: the same call with `apply: false`. Nothing is written; the
     response's `outcomes[]` (`matches[]` with season / episode /
     episode_end / name / confidence, `coverage`, `score`, `suggestion`)
     is shown next to the current placement, differences highlighted.
   - **Apply & pin**: `apply: true`. A season or disc number sent with an
     apply is kept as the operator's own value (backend behaviour).
   - **Unpin**: `DELETE /api/jobs/{id}/identity/pin`, back to the automatic
     ranking.
3. **Fix a track by hand**: a per-row picker filled from
   `GET /api/jobs/{id}/identity/episodes?source=&season=` (`EpisodeListView`:
   episodes with number, name, runtime, `special`) plus **Extra**,
   **Trailer** and **Other**. There is no "play all" role (`TrackRole` is
   main / episode / extra / trailer / other): a play-all title is set to
   **Other** or excluded. Saves through the existing job `PATCH`
   (`tracks: [{track_id, role, season, episode_number, episode_number_end,
   episode_name}]`), which records operator values that outrank any source.
   A multi-episode title sets `episode_number_end`.
4. **Revert a hand fix**: the same `PATCH` with `revert_fields` for those
   fields; the row returns to the matcher's placement.

### 4.4 States

| State | When | Shows |
|---|---|---|
| No series yet | TV job without a show id | Prompt to search the series (links to Search Title, TV) |
| Matching | flip / apply just happened, no outcome yet | Pending indicator until `job.identity_updated` |
| Applied | a source's placement in effect, not a suggestion | Rows + status |
| Suggestion | best outcome stored as a suggestion | Rows from the suggestion + **Accept** |
| Pinned | `pin.episode` set | Pinned source + **Unpin** |
| No match | every source miss / skipped | Explanation + Re-run controls |
| Unavailable | `browse_episodes` 503 / no provider configured | Link to Settings > Metadata > TV episodes |
| Provider error | preview / apply error | Inline error; current placement untouched |
| Guest | not a writer | Everything read-only |

## 5. Removal

Delete `EpisodeMatch.svelte`, `TvdbMatch.svelte`, their tests, and the
`tvdbMatch` / `fetchTvdbEpisodes` "not available" stubs in
`lib/api/jobs.ts`. Remove `TitleSearch`'s dead `onepisodes` /
"Match Episodes" button in favour of switching to the tab.

## 6. Design handoff

The look and interaction details come from Claude Design, using the prompt
in section 10. The operator reviews the prompt, runs it, and the approved
screens become the target the UI is built and reviewed against. No UI code
is written before that.

## 7. Testing

Test-first throughout; every suite's exit code checked, not only its
summary line.

- **Backend (pytest)**: `JobView.looks_episodic` for an episodic scan, a
  feature disc, and a job with no scan.
- **UI (vitest)**, identity API mocked at the module boundary:
  - toggle default (job type, `looks_episodic`, movie) and the `type=tv`
    search request;
  - applying a TV result calls `resolveJob` with `media_type: "tv"` and
    opens the tab;
  - header switch: TV/Movie `PATCH`, confirmation only with hand-set
    episodes;
  - tab visibility by media type;
  - each state in 4.4;
  - Preview sends `apply: false`, Apply & pin `apply: true`, Unpin the
    `DELETE`; hand fix and revert send the expected `PATCH` bodies;
  - refetch on `job.identity_updated`.
- **Live (hifi)**: flip Kolchak to TV through the search, watch the
  automatic match land, preview TVmaze against TMDb, set the 9 minute title
  to Extra by hand, revert it, check the naming preview.

## 8. Delivery

- Spec, then implementation plan, on `feat/tv-episode-match-ui`.
- New PR stacked on #100; mirrored to `integration/all-prs-3`.
- OpenAPI snapshot and TS types regenerated with the `JobView` change.

## 9. Open questions (resolve while planning, before UI code)

1. **A TV job carrying a movie id.** The header switch keeps the job's ids,
   so Kolchak switched with it would be TV with TMDb *movie* id 1749913.
   Verify how the episode stage resolves the show for such a job (search by
   title, or use the stored id), and how the tab can tell. If the stage
   cannot recover, the tab treats it as **No series yet** and asks for a
   series search; the header switch may then also offer "Search the series"
   right after flipping to TV.
2. **"No series yet" detection.** Confirm which field marks a job as having
   a series (a TV provider id in `metadata_json.identity.external_ids`, or a
   source summary's `inputs`), so 4.4's first state keys off real data.

## 10. Claude Design prompt

> Copy everything in this section into Claude Design.

---

**Design the TV episode matching experience for ARM's job page.**

**Product.** ARM (Automatic Ripping Machine) rips DVDs and Blu-rays (from a
drive, an ISO file or a disc folder) into MKV files and files them into a
media library. Each rip is a *job* with a detail page. For TV discs, ARM
has to know which episode each ripped title is, so files are named like
`Kolchak - S01E03 - The Vampire.mkv`. A background matcher compares title
runtimes against episode lists from TMDb, TVmaze and TVDB and either applies
a confident placement or stores an uncertain one as a *suggestion*. The
operator needs to see that result and correct it.

**Who.** A home-lab operator (admin) on desktop or phone, usually right after
a rip or while it runs. Guests can view but not change anything.

**Existing UI to fit into.** ui-neu, a SvelteKit app with its own design
system: cards, panels, chips/badges, segmented controls, tables that stack
into cards on phones, light and dark themes, an accent per status. Recurring
elements are shared components (status badges, chips, close buttons,
progress bars); designs must reuse those patterns, not one-offs. The job
page has a header (poster, title, year, type, disc type, status), a panel bar
with tabs (**Search Title**; **Match CD** for audio CDs), and a tracks table.

**Design these.**

1. **Movie / TV toggle in the title search panel.** Searching "Kolchak"
   as Movie returns "Kolchak: The Night Stalker Collection" (no year, no
   poster, a placeholder); as TV it returns "Kolchak: The Night Stalker"
   (1974, poster). Results carry a Movie / Series badge. Applying a series
   result switches the page to the Match Episodes tab.
2. **Quick Movie | TV switch in the job header** (admin only). It changes
   only the type. Switching a job with hand-set episodes back to Movie asks
   for confirmation ("2 tracks have episodes you set by hand. Switch to
   Movie anyway?").
3. **The Match Episodes tab**, shown only for TV jobs:
   - **Status line**: the source in effect (TMDb / TVmaze / TVDB), whether
     it was applied automatically or is a suggestion, whether a source is
     pinned, "6 of 6 tracks placed". Other sources' outcomes reachable but
     secondary ("TVmaze: matched 5 of 6", "TVDB: not configured").
   - **Track rows**: track (t00...t05), length, placement, origin
     (auto: TMDb / suggestion / you). Placement is an episode
     ("S01E03 The Vampire"), a span ("S01E03-E04"), or Extra / Trailer /
     Other. Each row (admin) has a picker listing the season's episodes
     (number, name, runtime; specials marked) plus Extra, Trailer, Other.
     Hand-set rows show a Revert.
   - **Re-run controls**: source, season, disc number; tolerance under
     "advanced" (seconds). **Preview** shows the proposed placement next to
     the current one with differences highlighted and per-track confidence;
     then **Apply & pin** or discard. A pinned source shows **Unpin**.
   - **Accept** for a suggestion.
   - **File-name preview** for the current placement.
4. **States** (one screen each): no series picked yet (prompt to search the
   series); matching in progress; applied; suggestion; pinned; no match;
   episode providers not configured (link to Settings > Metadata > TV
   episodes); provider error during preview (inline, current placement kept);
   guest (read-only).

**Sample data (Kolchak: The Night Stalker, disc 1; confidences are
illustrative).**

| Track | Length | TMDb placement | Confidence |
|---|---|---|---|
| t00 | 51:33 | S01E01 The Ripper | 0.94 |
| t01 | 50:33 | S01E02 The Zombie | 0.91 |
| t02 | 51:32 | S01E03 They Have Been, They Are, They Will Be... | 0.93 |
| t03 | 51:10 | S01E04 The Vampire | 0.90 |
| t04 | 51:18 | S01E05 The Werewolf | 0.92 |
| t05 | 9:02 | Extra (no episode) | n/a |

Use it for the applied state; for the suggestion state, use the same rows
with lower confidence (0.55-0.70) and "suggestion" status; for a preview,
show TVmaze proposing E02/E01 swapped on t00/t01.

**Constraints.**

- Light and dark themes; phone width (rows become stacked cards, 16px side
  gutter, no horizontal page scroll); keyboard reachable; screen-reader
  labels on pickers and status.
- Admin vs guest: guests see everything, with no controls.
- Long episode names truncate gracefully, with the full name available.
- Never imply ARM guessed when it didn't: origin is always visible.

**Deliver.** Desktop and phone screens for 1-4 (each state of 3 as its own
frame), plus short notes on interactions: what is clickable, what Preview
changes on screen, how Revert and Unpin confirm, loading and error
treatment.

---
