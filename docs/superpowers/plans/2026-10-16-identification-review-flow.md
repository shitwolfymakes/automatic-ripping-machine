# Identification Review Flow: Unmatched-Disc Experience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an unmatched disc fixable from the job without visiting Settings: pick the search source per search, identify through a search that carries ids, see why the automatic match missed, and be led into episode matching once a show is chosen.

**Architecture:** Three UI tasks and one small backend task. (1) `TitleSearch` gains a source switch (TMDb · OMDb · TVmaze · TVDB for TV; TMDb · OMDb for movies), defaulting to the Settings choice and greying out sources whose key is not saved; key presence comes from the existing `GET /api/config` (secrets come back as `<hidden>` when set). (2) The job page's "Identify disc" dialog for video discs embeds `TitleSearch` so a chosen result carries ids; manual entry stays, and a bare title on a TV disc warns that episodes cannot be matched. (3) The dispatcher records each source it tried and the outcome; identify stores the list on a miss as `metadata_json.identify_attempts`, and the review card summarises it in one line. (4) After a TV show is chosen, the review card shows the episode-matching state from the job's identity claims with a link to Match Episodes.

**Tech Stack:** FastAPI/pydantic (Task 3), SvelteKit/Svelte 5, vitest, pytest.

**Context:** owner walkthrough 2026-10-16 ("you put in a disc and it doesn't auto match"). Branch `feat/identification-review-flow` from `feat/identification-sources-ui-polish` (PR #370).

## Global Constraints

- **Source switch:** a segmented control or compact select labelled `Search with` inside `TitleSearch`, options in this order: TV `TMDb`, `OMDb`, `TVmaze`, `TVDB`; Movie `TMDb`, `OMDb`. Default is the Settings choice for the type (`$searchProviders`); switching Movie/TV resets to that type's default. A source whose key is not saved is shown disabled with the title `Needs <name> API key` (TVmaze never needs one). The chosen source is passed as `searchMetadata(query, type, provider)`. The existing provider badge is replaced by the switch.
- **Key presence:** a new readable store `keyedSources` in `lib/stores/config.ts` with `{ tmdb: boolean; omdb: boolean; tvdb: boolean }`, set in `hydrateConfig` from the config view (`value === '<hidden>'` means saved); `fetchConfig`'s `AppConfig` gains those three booleans. On a config fetch failure all three are `true` (fail open: the backend still refuses an unkeyed provider with a 400 the search shows).
- **Identify dialog (video discs):** above the manual Title/Year fields, the dialog shows `TitleSearch` for the job; selecting a result and applying it resolves the job exactly as the card's search does (ids, media type, poster). The manual fields stay under a `Or enter the title yourself` caption. When the job looks episodic (`job.looks_episodic` or `job.media_type === 'tv'`) and the operator submits the manual form, show above the submit button: `Without a search result ARM has no show id, so episodes can't be matched automatically.` and require a second click labelled `Save without a match`. CD dialog unchanged.
- **Miss reasons (backend):** `MetadataDispatcher` keeps a per-call list of attempts `{source: str, step: "fingerprint" | "disc_id" | "title" | "imdb", kind: "movie" | "tv" | "music" | None, outcome: "hit" | "miss" | "timeout" | "error" | "not_configured", detail: str | None}`, appended in `_call` (hit/miss/timeout/error) and for sources skipped because they are not configured (if the walk knows; at minimum, when a kind's walk is empty record one `{source: None, step: "title", kind, outcome: "no_sources"}` entry — add `"no_sources"` to the outcome literal). `identify()` returns the result as today; the attempts are readable as `dispatcher.last_attempts` for the call just made (reset at the start of `identify` and `identify_from_imdb`). The identify route stores `metadata_json["identify_attempts"] = [...]` (JSON-serialisable dicts, at most 20) when the final result is a miss (including a timeout of the whole dispatch: add `{source: None, step: "title", kind: None, outcome: "timeout", detail: "lookup took longer than 25 s"}`), and removes the key on a hit. `JobMetadata` gains `identify_attempts: list[dict[str, Any]] | None = None`; regenerate the OpenAPI snapshot and `api.gen.ts`.
- **Miss line on the card:** for a job with `flags.unidentified` or status `awaiting_user_id`, the review card shows one line under the title, `data-testid="identify-miss-reason"`, chosen by the first rule that applies: any attempt `no_sources` → `No online source is switched on for this kind of disc.`; all attempts `not_configured` → `No API keys are saved for the sources in your lists.`; any `timeout` and no `miss` → `The lookup timed out. Try the search below.`; otherwise → `No source found a close match for "<searched title or volume label>". Try another source in the search below.` (searched title: the `detail` of the last `title` attempt if it carries one, else the job title). No line when there are no attempts (older jobs).
- **Episode lead-in on the card:** for a TV job (`media_type === 'tv'`) not in a post-rip status, a line `data-testid="episode-status"`: no series known (`has_series` false) → `Pick the show to match episodes.`; series known and an episode source claim with status `ok` → `Episodes matched from <source label>.` (label TMDb/TVmaze/TVDB from the claim id `episodes_<id>`); claims present but none ok → `No source could place the episodes.`; none yet → `Matching episodes…`. The line links to `/jobs/<id>#episodes` when a series is known; the job page opens the Match Episodes panel when the hash is `#episodes`.
- Copy follows the docs' voice: plain sentences, no exclamation, no "not X but Y". Tests zero-infra. Commits carry no attribution trailers.

## Review Focus

1. Switching the source to TVmaze with no TMDb key saved must search TVmaze (provider param sent) and never send `tmdb` (Task 1).
2. A manual TV identify must require the second click and must not resolve on the first (Task 2).
3. A dispatch timeout must still store an attempts list with the timeout entry, and a later hit (resolve or re-identify) must remove `identify_attempts` (Task 3).
4. A job with no attempts (older rows) shows no miss line (Task 3 UI test).
5. The episode line must not appear for movies or post-rip jobs, and its link must open Match Episodes (Task 4).

---

### Task 1: Source switch in the title search

**Files:** `services/ui-neu/frontend/src/lib/stores/config.ts`, `lib/api/config.ts`, `lib/components/TitleSearch.svelte`; tests `lib/components/__tests__/TitleSearch.test.ts` (create or extend), `lib/stores/__tests__/config.test.ts` (if present; else cover via TitleSearch).

- [ ] Tests first: default source = Settings choice per type; switching Movie/TV resets it; an unkeyed source is disabled with the title text; choosing TVmaze calls `searchMetadata(query, 'tv', 'tvmaze')`; the provider badge is gone.
- [ ] Implement per Global Constraints; reuse the `InterfaceSettings`-style segmented control or a `select` with `aria-label="Search with"`.
- [ ] `npm run check && npx vitest run && npm run lint`; commit `feat(ui): pick the search source per search`.

### Task 2: Identify dialog searches first

**Files:** `lib/components/IdentifyDialog.svelte`; test `lib/components/__tests__/IdentifyDialog.test.ts`.

- [ ] Tests first: a video job shows `TitleSearch` and the manual fields under the caption; an episodic job's manual submit shows the warning and does not call `resolveJob` until `Save without a match`; a movie job's manual submit resolves on the first click; CD dialog unchanged.
- [ ] Implement; on a `TitleSearch` apply, call the dialog's `onidentified` with the response the same way the manual path does (check how `TitleSearch` reports completion and wire it).
- [ ] Gate and commit `feat(ui): identify a disc from a search result so it carries show ids`.

### Task 3: Why the automatic match missed

**Files:** `services/backend/arm_backend/metadata/dispatcher.py`, `services/backend/arm_backend/routers/ripper.py` (identify miss/hit arms), `routers/jobs.py` (`resolve_identity` drops `identify_attempts` like it drops `identity_suggestion`), `packages/arm_common/arm_common/schemas/job_metadata.py`; UI `lib/components/DiscReviewWidget.svelte` + a helper `missReason(job)` in `lib/utils/job-status.ts`; tests in `services/backend/tests/test_dispatcher.py`, `test_ripper_router.py`, `test_jobs_router.py`, `lib/utils/__tests__/job-status.test.ts`, `DiscReviewWidget.test.ts`; regen snapshot + `api.gen.ts`.

- [ ] Backend tests first: attempts recorded for hit/miss/timeout/error; an empty TV walk records `no_sources`; identify stores the list on a miss and removes it on a hit; whole-dispatch timeout stores the timeout entry; resolve removes it.
- [ ] Implement backend; `uv run pytest services/backend packages/arm_common -q`; pre-commit ruff/ruff-format/mypy; regen.
- [ ] UI tests first for `missReason` (each rule, no attempts → null) and the card line; implement; UI gate.
- [ ] Commit `feat(identify): record why the automatic match missed and say so on the card` (one or two commits).

### Task 4: Episode lead-in

**Files:** `lib/components/DiscReviewWidget.svelte`, helper `episodeStatus(job)` in `lib/utils/job-status.ts`, `routes/jobs/[id]/+page.svelte` (`#episodes` opens the panel); tests in `job-status.test.ts`, `DiscReviewWidget.test.ts`, the job page test.

- [ ] Tests first for each state, movie/post-rip absence, and the hash opening the panel; implement; gate; commit `feat(ui): lead from a chosen show into episode matching`.

## Self-review notes

- Items 1–4 from the walkthrough map to Tasks 1–4. Only Task 3 touches the backend and the wire contract, so hifi needs a backend rebuild for it; the rest is UI-only.
