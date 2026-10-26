# Episode match without an accept step: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (owner chose native execution in session) with a fresh whole-branch review at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** every episode match is applied to the tracks; a held one is marked and shown as a guess; the countdown holds for it; the UI's only match verbs are Fix match and Clear episodes.

**Architecture:** the resolver stops skipping held episode sources and reports the winner and whether it was held; the pipeline stores `unsure` on the claims; `JobView.episodes_unsure` carries it to the ripper (countdown hold) and the UI (amber). A new DELETE endpoint forgets a job's episode match. The panel loses Accept, Re-run, Pin and Unpin.

**Tech stack:** FastAPI + Pydantic (`arm_common`), SvelteKit/Svelte 5, vitest, pytest with FakeSession, OpenAPI snapshot + codegen.

**Spec:** `docs/superpowers/specs/2026-10-25-episode-match-no-accept-design.md`

## Global constraints

- UI copy ASCII only (`__tests__/ascii-copy.test.ts`).
- After any `arm_common` schema or router change: `bash devtools/regen-openapi-snapshot.sh` and `bash services/ui-neu/scripts/codegen.sh`, commit both artifacts.
- Tests zero-infra; backend changes fully covered.
- No migrations: `unsure` lives in the claims JSON; `episodes_unsure` is computed.

## Review focus

1. A job whose winning episode source is clean must have `unsure` false even if another source held.
2. Clearing a match keeps manual track claims and the show ids.
3. The ripper never auto-starts while `episodes_unsure`; Start rip by hand still works.
4. A card with no series or a movie never shows the guess state or the held countdown.
5. The pin endpoint still works and the UI never calls it.

---

### Task 1: resolver applies held sources and reports unsure

**Files:** modify `packages/arm_common/arm_common/schemas/identity.py` (`IdentityClaims.unsure: bool = False`), `packages/arm_common/arm_common/schemas/jobs.py` (`JobView.episodes_unsure` computed from `metadata_json.identity_claims.unsure`), `services/backend/arm_backend/identity/resolver.py` (`Resolution.episode_source: str | None`, `Resolution.episode_unsure: bool`; usable sort key `(tier, 0 if pinned else 1, 1 if suggestion else 0, rank...)`; the `suggestion` skip is removed), `services/backend/arm_backend/identity/pipeline.py` (`resolve_job` writes `claims.unsure = resolution.episode_unsure` through `proposals`), tests `test_identity_resolver.py`, `test_identity_pipeline.py`, `test_identity_schemas.py`, a JobView test.

- [ ] Rewrite `test_suggestion_sources_are_not_applied` as `test_held_source_is_applied_and_reported_unsure`; `test_pinned_ok_suggestion_is_applied` keeps passing; add `test_clean_source_beats_held_one_regardless_of_rank`; add a pipeline test that `resolve_job` sets and clears `claims.unsure`; add a JobView test for `episodes_unsure`.
- [ ] Implement; `uv run pytest services/backend -q`; regen OpenAPI + codegen; commit.

### Task 2: clear-match endpoint

**Files:** `services/backend/arm_backend/identity/proposals.py` (`forget_episode_sources(job) -> bool`: drop `episodes_*` sources, clear the episode pin, `unsure = False`), `services/backend/arm_backend/routers/identity.py` (`DELETE /{job_id}/identity/match` → `IdentityView`, writer role, lock job then tracks, resolve, `emit_identity_resolved`), `services/ui-neu/frontend/src/lib/api/identity.ts` (`clearEpisodeMatch(jobId)`), tests `test_identity_proposals.py`, `test_identity_router.py`.

- [ ] Tests: forgets the sources and the pin, keeps manual claims and show ids, emits `job.identity_updated` and `track.updated` for each unplaced track, 404 unknown job, 403 reader.
- [ ] Implement; regen OpenAPI + codegen; commit.

### Task 3: ripper holds the countdown for a guess

**Files:** `services/ripper/arm_ripper/job_controller.py` (`_review_countdown_expired`: `if view.episodes_unsure: return False`, log once per job id), `services/ripper/tests/test_job_controller.py`.

- [ ] Test mirroring `test_review_gate_per_job_pause_does_not_auto_start` with `episodes_unsure=True`; a second test that a later view with `episodes_unsure=False` auto-starts.
- [ ] Implement; `uv run pytest services/ripper -q`; commit.

### Task 4: panel model and markup

**Files:** `services/ui-neu/frontend/src/lib/components/episodes/episodeModel.ts` (`PanelState` = noseries | matching | unavailable | nomatch | unsure | applied; `panelState` uses `job.episodes_unsure` for `unsure`; `Origin.kind` gains `guess`; `buildRows` marks an applied placement from a held winning source as `guess`; drop the suggestion-drawing branch; `placedCount` counts auto, guess, you), `EpisodeMatchPanel.svelte` (header chips and actions per spec 4.4; Fix match = `openRerun` seeded with the held season; Clear episodes calls `clearEpisodeMatch` then `reload` and `onchanged`; remove accept, unpin, pinned alert, Re-run button, `unpinIdentity` import), `RerunPanel.svelte` ("Apply & pin X" → "Apply"), `EpisodeRows.svelte` (origin label "Guess, {source}" with chip-warning), tests `episodeModel.test.ts`, `EpisodeMatchPanel.test.ts`, `ascii-copy.test.ts`.

- [ ] Update tests first: no Accept, no Unpin, no "Pinned by you", no "Suggestion, not applied"; `unsure` view shows the amber line, the fit facts, the Guess chips, Fix match and Clear episodes; Clear episodes calls the API and `onchanged`; Fix match opens the form on the held season; "Apply" applies.
- [ ] Implement; `npx vitest run src/lib/components/episodes`; commit.

### Task 5: card, countdown, settings label

**Files:** `services/ui-neu/frontend/src/lib/utils/job-status.ts` (`episodeStatus` returns `guess` when `job.episodes_unsure` and every title placed; `attention` otherwise as today), `DiscReviewWidget.svelte` (Episodes row `guess` state copy "Episodes placed, a guess" + Review; Episodes button visible for `guess`; countdown `paused` when `episodes_unsure` with note "Held: episodes are a guess", pause toggle hidden), `CountdownTimer.svelte` (optional `note` prop replacing the "Paused" word), `routes/jobs/[id]/+page.svelte` (any Episodes status copy it shares), `settings/IdentityCard.svelte` (label + help for `episode_auto_apply`), tests `job-status.test.ts`, `DiscReviewWidget.episodes.test.ts`, `CountdownTimer` test if present.

- [ ] Tests first; implement; `npx vitest run`; `npm run check`; `npm run lint`; `npm run lint:styles`; commit.

### Task 6: docs, memory, gates, deploy

**Files:** `docs/developers/architecture/02-job-lifecycle.md` (episode matching paragraph: applied with unsure, countdown hold, Clear episodes), `.claude/memory/project_tv_season_selection.md`.

- [ ] Full gates: `uv run pytest`, UI suite + checks, OpenAPI drift check, `uv run pre-commit run --all-files`.
- [ ] Fresh whole-branch reviewer on the most capable model; fix round; push to #402; PR comment; merge into hifi's deploy branch and roll out; verify on a TV ISO.
