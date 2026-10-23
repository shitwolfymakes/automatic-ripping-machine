# TV season selection: the operator's path to a correctly placed disc

Design, 2026-10-23. Builds on the identity-sources design (2026-09-28), the
episode-match UI design (2026-10-02) and the identification rework (#374 to
#379). Branch `feat/tv-season-selection`, stacked on `feat/home-episode-match`
(#379); its PR targets that branch.

## 1. Problem

A tester fed TV discs in no particular order, across seasons, with ordinary
studio labels. Discs were placed in the wrong season or held, and the UI gave
no good way to say "this is season 7, disc 3" and have ARM try again.

What the code does today, measured on 200 real discs from TheDiscDB (corpus
under `services/backend/tests/fixtures/thediscdb/`, harness
`devtools/tv-match-baseline.py`):

| Scenario | titles placed correctly | discs placed perfectly (of 189) |
|---|---|---|
| nothing known, season scan | 13% | 20 |
| season known | 24% | 37 |
| season and disc number known | 25% | 38 |
| season and disc, lower discs already ripped | 51% | 81 |

Why it is low is understood (extras inflate the anchor's title count, 42% of
discs list episodes out of MakeMKV title order, uniform runtimes are always
ambiguous). The owner's decision is to leave the alignment model alone for now, accept
held results, and make the operator's path solid:

- Season is not visible or editable before the rip. The Info form has disc
  number and total but no season; `PATCH`/`resolve` already accepts it.
- The UI assumes season 1 when none is known: the re-run form and the episode
  browser default to `job.season ?? 1` and `disc_number ?? 1`.
- The season scan stops at 10 seasons (`MAX_SEASON_SCAN`). A disc from season
  11 or later of a long-running show is never matched automatically, and the
  truncated result is held with no explanation an operator can act on.
- A held result says only that it is "too uncertain", not why.
- A TheDiscDB hit places tracks but leaves `job.season` empty, so the card
  shows no season and the re-run form opens on season 1.
- Siblings are found by exact title string, so two discs of one show
  identified through different sources are strangers to each other.

## 2. Goals, non-goals, anti-goals

Goals

0. Matching will often miss. Choosing a season and placing episodes by hand
   must be the primary path, fast enough to use on every disc, and the matcher
   must work around what the operator has placed instead of over it.
1. An operator can see the job's season, where it came from, and change it
   (or the disc number) in the same place they review the disc, before or
   after the rip. Saving re-runs episode matching and the view updates when
   the result lands.
2. Nothing in the UI implies a season that is not known. Unknown reads as
   unknown.
3. Any season the provider lists can be chosen and matched, including
   season 0 (specials) and seasons beyond 10.
4. A held result states its reasons in plain words.
5. No regression on the corpus baseline in any scenario; discs from seasons
   11 and up become matchable when nothing is known.

Non-goals

- Changing the alignment algorithm (`matcher.align`) or the sibling-conflict
  rule. Those are the next project, and this one gives it the controls and
  the corpus.
- Consuming TheDiscDB's Optical Disc Manifest sidecars. Kept open (review
  doc section 9).
- Label parser changes.

Anti-goals (this would be a failure even if it works)

- A season value shown or sent that the operator did not set and no source
  proposed.
- A full-season scan that hammers a provider: a 38-season show must not cost
  38 requests on every re-run of every disc.
- Overriding an operator's season or disc number with an automatic value.
- Extrapolating from one hand-placed track: an operator sets title 3 to
  episode 5 and ARM silently numbers the following titles 6, 7, 8 in title
  order. On the corpus, episode order differs from title order on 42% of
  discs, so a sequence guessed from one fix is wrong more often than right.

## 3. Decisions already made

- Held results are acceptable. The deliverable is the path to fix them.
- Build on the tip of the UI stack (#379). The PR targets
  `feat/home-episode-match`.
- Seasons above 10 must work; many shows run 30 or more.
- Stabilise the existing MakeMKV-based process; keep extension seams open.

## 4. Design

### 4.1 Backend

**A. Season scan without a hard cap.** `episode_stage._match` scans every
season `provider.seasons()` returns when no season is known, in an order that
puts likely seasons first. It stops early only when the season just tried
came from a hint or a sibling (steps 1 and 2 below) and its fit would apply on
its own (the `_ok_claims` suggestion predicate is false against the seasons
scanned so far). A season reached by falling through to step 3 never stops
the scan: with nothing known, every season is tried and ranked, so a
uniform-runtime show cannot be applied confidently to the wrong season. The
order:

1. the season a disc hint proposed (label or BDMT claim), even when the
   resolver did not make it `job.season`;
2. seasons that live sibling discs of the same show hold, nearest first;
3. the remaining seasons ascending.

`MAX_SEASON_SCAN` goes. `scan_truncated` is replaced by `scan_stopped_early`
in `extra` (true when the stop rule fired before every season was tried); it
is informational and does not by itself make a suggestion. `thin_win` and
`near_tie` keep comparing against the seasons that were scanned. When the
provider's season list is empty or fails, the outcome is a miss with detail,
as today.

Request budget: one `/tv/{id}` call for the season list, then one call per
season tried. A well-labelled disc costs one or two season fetches. A disc
with nothing known costs one fetch per season the first time; `SourceHttp`
caches season lists for a day, so the show's other discs reuse them. My call,
not the owner's: no new setting for the cap, and no partial scan when nothing
is known.

**B. The anchor counts episode-shaped titles only.** `_fit_season` passes
`n_titles` as the number of eligible titles whose length is within the
season's episode range (between the shortest and longest known episode
runtime, widened by the tolerance), not every eligible title. Extras and
menus no longer drive the interpolation to zero. This is a small, contained
change in `episode_stage.py`; `start_anchor` itself is unchanged.

**C. Siblings by show id.** `_sibling_rows` selects live TV jobs (not failed
or abandoned, not this job) and `_siblings` keeps the ones sharing an external
id, as it already does. The `Job.title ==` filter is dropped. A job with no
external ids has no siblings.

**D. TheDiscDB claims job-level season and disc position.** `build_claims`
adds `JobClaim(season=...)` when every placed title on the disc has the same
`Item.Season`, and `disc_number` from the disc's `Index` when the release is a
single-season release. "Single-season" is decided at index time: `_write_index`
records the set of seasons across a release's discs in the row (new column
`release_seasons`, JSON), and `build_claims` claims `disc_number` only when
that set has one element. Complete-series releases, whose `Index` runs across
seasons, claim season but not disc number. Rebuilding the index is the daily
refresh's job; an index built before this change has no `release_seasons`
and claims no disc number until it is rebuilt.

**E. Reasons on a held result.** `_ok_claims` writes `extra["hold_reasons"]`:
a list of codes from `ambiguous`, `near_tie`, `low_coverage`,
`low_confidence`, `thin_win`, `nominal_runtimes`, `sibling_conflict`,
`auto_apply_off`. `suggestion` stays the single boolean the resolver reads;
the codes explain it. Each code maps to one sentence in the UI (section
4.2 E).

**F. Forcing a scan from the re-run form.** `MatchRequest` gains
`scan_seasons: bool = False`. When true, the stage ignores `job.season` and
scans as in A (hint-ordered, no early stop unless the season came from a hint
or sibling), so an operator can get the ranked alternatives for a disc whose
label or TheDiscDB season was wrong. `season` and `scan_seasons` together are
a 422. `_known_season` returns None when the option is set.

**G. Clearing a season or disc position forgets the operator's value.** An
explicit `null` for `season`, `disc_number` or `disc_total` on `/resolve`
removes the operator's manual claim for that field instead of recording a
manual "unknown"; the resolver then re-runs and the field takes the best
remaining automatic proposal, or stays empty when there is none. Today the
null is recorded as a manual claim and outranks every later automatic value
forever, which would leave the card saying "Season not set" while the tracks
read season 7. `record_manual_job` drops the field from the manual claim when
the value is None; no new endpoint.

**I. Operator-placed tracks are constraints.** A track whose episode was set
by the operator (`identity_provenance["episode_number"] == "manual"`) is
removed from the titles the stage aligns, and its episode numbers are removed
from the season's `remaining` list exactly as sibling-held episodes are
(`claimed` in `align_runs`). A re-run therefore fills the other titles into
the episodes left over, split into runs around the operator's picks, and can
never propose an episode the operator already placed on this disc. Today the
stage re-aligns every episode-shaped title and the manual value only wins at
resolve time, so a re-run after one fix can hand the neighbouring titles a
sequence that collides with it. Specials (season 0) and tracks the operator
marked as extras are excluded the same way.

**H. Season list endpoint.** `GET /api/jobs/{id}/identity/seasons?source=`
returns `{source_id, show_id, seasons: [int]}` from `provider.seasons()` for
the job's resolved show id, with the same source resolution and error shapes
as `/identity/episodes`. Specials are not in the list (providers return
regular seasons); the UI adds season 0 itself. OpenAPI snapshot and TS types
are regenerated.

No migration: `release_seasons` lives in the sqlite snapshot index, not
Postgres.

### 4.2 UI (ui-neu)

**A. Season in the Info form, on the card and the job page.** The Disc
section becomes Season, Disc number, Disc total, in that order, same control
style. The job page mounts the same `JobInfoForm` beside the Match Episodes
panel (today it has no season or disc-position editor at all; its only season
control is the re-run form), so the three fields are edited the same way in
both places and the provenance line appears in both. Empty means unknown
(placeholder "-"); clearing a field the operator had set sends `null`, which
forgets their value (4.1 G). The form's help
text reads: "For TV box sets, the season on this disc and the disc's position
in it. Leave blank when unknown." Under the row, one muted line names the
provenance when a value is set: "Season from the disc label", "Season matched
by TMDb", "Season set by you", built from `job.identity_provenance` with the
existing source labels. The form saves through `resolveJob` as now.

**B. Re-run after a change.** When the Info save changed season or disc
number on a TV job, the host (card or job page) starts the shared
`EpisodeMatching` state for the job, exactly as picking a show in the match
picker does, so the card shows "Matching episodes…" and the panel refreshes on
`job.identity_updated`. The backend already re-schedules the stage on that
change.

**C. No implicit season.** In `EpisodeMatchPanel`:

- the re-run form opens with `season = job.season ?? null` and
  `disc = job.disc_number ?? null`; both fields show empty when unknown. The
  season select has a first entry "Scan all seasons" that sends
  `scan_seasons: true` (4.1 F); with the job's season known the select
  preselects it, so a plain Preview re-runs that season and the operator
  chooses the scan deliberately;
- the season control is a select fed by the seasons endpoint (4.1 H) for the
  chosen source, with "Specials" for 0 and the job's current season preselected when
  set; if the list cannot load, the control falls back to a number input;
- the per-track episode picker browses the track's season, else the job's;
  when neither is known, the row shows a season select first and no episode
  list until one is chosen.

**C2. Placing episodes by hand.** The per-track episode picker is built for
the common case where the match is wrong:

- The disc's season is chosen once (Info or the re-run select) and every
  track row's picker uses it; a track may still be moved to another season
  from its own row, which is how a two-season disc is placed.
- Each track row shows its length. The picker lists the season's episodes
  with their runtime, sorted by closeness to the track's length, closest
  first, so the right episode is usually at the top. Episodes already placed
  on this disc, or held by a sibling disc, are marked and sorted last.
- Picking an episode saves that track only. Nothing else on the disc changes.
- After one or more picks, a "Fill the rest" button runs a preview (4.1 F
  path, with the job's season) that places only the unplaced tracks into the
  episodes left over (4.1 I), and shows the result as the existing preview
  does, with Apply. The operator sees what would change before anything is
  saved.
- Revert per track stays as it is.

**D. Candidate seasons from the scan.** When the active source's stored
summary has `alternatives`, the panel lists them under the status line as
"Also fits: Season 3 (6 of 6 titles), Season 7 (5 of 6)". Each is a button
that runs a preview with that season. The best-fit season itself is shown the
same way when the result is held, so an operator can confirm it with one
click.

**E. Why it is held.** The suggestion alert keeps its title and adds one
sentence per `hold_reasons` code:

| code | sentence |
|---|---|
| ambiguous | The titles fit equally well one episode earlier or later. |
| near_tie | Another season fits about as well. |
| low_coverage | Fewer than half the titles found an episode. |
| low_confidence | The runtimes are a loose fit. |
| thin_win | The best season wins by a thin margin. |
| nominal_runtimes | The source lists rounded runtimes, not real ones. |
| sibling_conflict | Another disc of this season already holds some of these episodes, or its disc number is unknown. |
| auto_apply_off | Automatic apply is off in Settings. |

Followed by "Set the season or disc number in Info, or accept the suggestion."

**F. The review card.** The SHOW row's detail keeps "TV Series · years ·
Season n". When the job is TV, pre-rip, and has no season, the detail ends
with "Season not set" in the muted style, since an unset season is ordinary
(my call). The Episodes row's "Episodes need attention" text is unchanged.

**G. Standard components.** Chips, close buttons, glyphs and sort indicators
come from the shared components. No em dashes or unicode symbols in copy. No
new strings assume a season.

### 4.3 Tests and acceptance

- `uv run python devtools/tv-match-baseline.py --min-seconds 60` before and
  after. Add a scenario "nothing known, hint-ordered scan" that feeds the
  label's season when the corpus disc `Name` carries one. Add The Simpsons
  (1989) and Doctor Who (1963) to the corpus generator's `SERIES` for the
  deep-season case.
- Acceptance on the corpus: no scenario loses correct placements; in
  "nothing known", Supernatural seasons 11 to 15 and The Simpsons discs get
  the right season picked (`wrongS` for those discs drops to the level of the
  under-10 seasons).
- Backend unit tests for A to I in the existing suites, including: a re-run
  with one manually placed track never proposes its episode for another
  title, and fills around it in runs (`test_episode_stage`,
  `test_identity_thediscdb`, `test_thediscdb_snapshot`, `test_identity_router`),
  100% statement coverage kept.
- UI vitest for the Info form season field (seed, touched, null forgets,
  provenance line) on the card and the job page, the re-run defaults and the
  "Scan all seasons" entry, the season select and fallback, the alternatives
  buttons, the reasons mapping, the picker's runtime-sorted list with used
  episodes marked, "Fill the rest" previewing only unplaced tracks, and the
  card's "Season not set".
- Docs: `docs/developers/architecture/02-job-lifecycle.md` section "Episode
  matching" describes the new scan order, the stop rule, the reasons, and the
  seasons endpoint, replacing the ten-season text.

## 5. Constraints

- Stacked on #379; do not touch files only to reformat them; keep the diff
  to the surfaces above.
- OpenAPI drift gates CI: regenerate the snapshot and `api.gen.ts`.
- Backend 100% statement coverage; tests stay zero-infra.
- Setup and Settings reuse: no new setting is introduced.
- Humanizer over the PR body and user-facing strings.

## 6. Left to the builder

- Exact widening rule for "episode-shaped" in 4.1 B, as long as menus and
  trailers fall outside and the corpus baseline does not regress.
- Whether the seasons endpoint caches in process; `SourceHttp` caching may be
  enough.
- Layout of the alternatives buttons and the reasons list within the
  existing panel styles.
- How the fallback number input is offered when the season list fails.
- Test fixture shapes for `release_seasons`.

## 7. Definition of done

1. A TV disc with no label season: card shows "Season not set"; Info shows an
   empty Season; operator types 7, saves; card shows "Matching episodes…";
   panel refreshes with season 7's placement or a held result with reasons.
2. A disc from season 23 of a 38-season show with nothing known is scanned
   past season 10 and either applied or held with "Another season fits about
   as well"; never flagged truncated.
3. The re-run form never opens on season 1 unless the job's season is 1;
   "Scan all seasons" on a disc with a wrong label season lists the other
   seasons that fit.
6. Clearing the season in Info on a disc whose tracks were matched to season
   7 leaves the job showing season 7 from the match, not "Season not set".
7. The job page edits season, disc number and disc total with the same form
   as the card.
8. On a disc placed wrongly, the operator sets the season, picks the right
   episode for one track from a list sorted by runtime, presses "Fill the
   rest", and the preview places the remaining tracks around that pick. No
   track is renumbered in title order from the fixed one.
4. A TheDiscDB-mapped season disc shows its season in the card and Info.
5. Corpus baseline: no regression; deep-season discs pick the right season.
