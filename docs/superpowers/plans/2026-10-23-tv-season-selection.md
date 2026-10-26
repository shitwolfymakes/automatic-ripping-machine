# TV Season Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make season visible, editable and re-matchable everywhere a TV disc is reviewed, scan every season a provider lists, explain held results, and let the operator place episodes by hand with the matcher filling around their picks.

**Architecture:** Backend changes stay inside `identity/episode_stage.py` (scan order, stop rule, reasons, operator constraints), `identity/proposals.py` (clearing forgets), the TheDiscDB source and snapshot index (job-level claims), and two additions to the identity router (`scan_seasons` on match, a seasons list). The UI adds a season field to the Info form, mounts that form on the job page, removes every implicit season from the Match Episodes panel, and gives each track row its own season and a runtime-sorted episode picker. The TheDiscDB corpus and baseline harness guard against regression.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, SQLModel (backend); Svelte 5, SvelteKit, vitest (UI); the OpenAPI snapshot and generated TS types bind the two.

**Spec:** `docs/superpowers/specs/2026-10-23-tv-season-selection-design.md`

## Global Constraints

- Branch `feat/tv-season-selection`, stacked on `feat/home-episode-match` (wolfy #379). The PR targets that branch. Do not touch files only to reformat them.
- OpenAPI drift gates CI: after any change to `arm_common` schemas or a Backend router, run `bash devtools/regen-openapi-snapshot.sh` and `bash services/ui-neu/scripts/codegen.sh` and commit `services/ui-neu/openapi.snapshot.json` and `api.gen.ts`.
- Backend 100% statement coverage; tests stay zero-infra (FakeSession, FakeProvider; no Docker, no network).
- No new Settings field. No Postgres migration.
- UI copy is ASCII: no em or en dashes, middle dots, ellipsis characters or symbol glyphs. An empty value is "-", a trailing wait is "...", a separator in joined facts is ", ".
- Shared UI components (`Glyph`, `CloseButton`, chips) for recurring UI; never one-off inline markup.
- Lint before each commit: `uv run pre-commit run --files <files>`; UI: `cd services/ui-neu/frontend && npm run check && npm run lint && npx vitest run <file>`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; no session links.

## Review Focus

1. A provider that returns an empty season list for a show (new or mis-identified): the stage must record a miss with detail, never raise or loop. Pinned in Task 1.
2. A job whose show ids are all empty: sibling lookup must return nothing rather than treating every TV job as a sibling. Pinned in Task 3.
3. An operator-placed track whose season differs from the season being scanned: it must not remove episodes from the wrong season's pool and must still be excluded from alignment. Pinned in Task 4.
4. An old snapshot index without the `release_seasons` column: `lookup` must still return a match (with `release_seasons=None`) rather than 500 the identify call. Pinned in Task 7.
5. Clearing season on a job whose only season claim was the operator's own, with tracks already matched to a season: the job field empties and the tracks keep their per-track season. Pinned in Task 6.

---

### Task 1: Scan every season, in a useful order, and say why a result is held

**Files:**
- Modify: `services/backend/arm_backend/identity/episode_stage.py`
- Modify: `services/backend/arm_backend/identity/pipeline.py` (add `hint_season`)
- Modify: `services/backend/arm_backend/identity/sources/registry.py` (remove `MAX_SEASON_SCAN`)
- Modify: `devtools/tv-match-baseline.py` (drop the `MAX_SEASON_SCAN` import; scan all seasons)
- Modify: `docs/developers/architecture/02-job-lifecycle.md` ("Episode matching" paragraph)
- Test: `services/backend/tests/test_episode_stage.py`

**Interfaces:**
- Produces in `pipeline.py`: `def hint_season(job: Job, sources: Sequence[Source] = HINT_SOURCES) -> int | None` (the season of the first ok disc-hint entry that set one, in source order; same walk as `hint_is_tv`).
- Produces in `episode_stage.py`:
  - `def season_scan_order(seasons: Sequence[int], *, hint: int | None, sibling_seasons: Sequence[int]) -> list[tuple[int, bool]]`: `(season, from_hint)` pairs. Order: `hint` first if it is in `seasons`; then each of `sibling_seasons` that is in `seasons` (deduplicated, ascending by distance to `hint`, ties ascending by number; plain ascending when `hint` is None); then the rest ascending. `from_hint` is True for the first two groups.
  - `def sibling_seasons(rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds) -> list[int]`: seasons held by rows sharing an id with `ids` (`job.season` plus every `track.season`), most frequent first, ties ascending.
  - `def hold_reasons(fit: _SeasonFit, ranked: Sequence[tuple[int, MatchResult]], *, scanned: bool, auto_apply: bool) -> list[str]`: codes in this fixed order: `auto_apply_off`, `ambiguous`, `low_coverage`, `low_confidence`, `near_tie`, `thin_win`, `nominal_runtimes`, `sibling_conflict`. Thresholds are the existing `MIN_COVERAGE`, `MIN_MEAN_CONFIDENCE`, `_near_tie`, `_thin_win` (the last two only when `len(ranked) > 1`; `thin_win` only when `scanned`).
  - `_ok_claims` sets `suggestion = bool(reasons)`, `extra["hold_reasons"] = reasons`, `extra["scan_stopped_early"] = <bool>` when `scanned` (absent when the season was known). `scan_truncated` and `MAX_SEASON_SCAN` are gone.
  - `_pick_season(provider, req, order) -> tuple[int, _SeasonFit, list[tuple[int, MatchResult]], bool] | None`: walks `order`; after each fit, if `from_hint` and `hold_reasons(..., scanned=True, auto_apply=True)` is empty, stops and returns `stopped_early=True`.
  - `_match` computes `order = season_scan_order(await provider.seasons(show_id), hint=hint_season(job), sibling_seasons=sibling_seasons(rows, ids))` when `known_season is None`. An empty season list is `status="miss", detail="no seasons listed"`.

- [ ] **Step 1: Write the failing tests** in `test_episode_stage.py`

```python
def test_season_scan_order_puts_hint_then_siblings_then_the_rest() -> None:
    order = episode_stage.season_scan_order([1, 2, 3, 4, 5, 6], hint=4, sibling_seasons=[6, 2])
    assert order == [(4, True), (2, True), (6, True), (1, False), (3, False), (5, False)]
    assert episode_stage.season_scan_order([1, 2, 3], hint=None, sibling_seasons=[]) == [(1, False), (2, False), (3, False)]
    assert episode_stage.season_scan_order([1, 2], hint=9, sibling_seasons=[7]) == [(1, False), (2, False)]


async def test_nothing_known_scans_every_season_and_never_stops_early() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    seasons = {n: _season(n, [600 * n + i for i in range(10)]) for n in range(1, 16)}
    seasons[13] = _season(13, DISTINCT)
    provider = FakeProvider(seasons=seasons)
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    claims = outcomes[0].claims
    assert claims.job.season == 13
    assert sorted(n for name, n in provider.calls if name == "season") == list(range(1, 16))
    assert claims.extra["scan_stopped_early"] is False
    assert "scan_truncated" not in claims.extra


async def test_sibling_season_is_tried_first_and_stops_the_scan() -> None:
    # Disc 1 of season 7 (E1, E2) is already ripped; this is disc 2 holding E3-E6.
    job = _job(season=None, disc_number=2)
    sibling = _job("job_2", season=7, disc_number=1)
    sib_tracks = [_track("job_2", i, s, role=TrackRole.EPISODE, season=7, episode_number=i + 1) for i, s in enumerate(DISTINCT[:2])]
    db = _db(job, DISC, sibling, extra_tracks=sib_tracks)
    provider = FakeProvider(seasons={n: _season(n, DISTINCT) for n in range(1, 10)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    assert [n for name, n in provider.calls if name == "season"] == [7]
    assert outcomes[0].claims.extra["scan_stopped_early"] is True
    assert outcomes[0].claims.job.season == 7


async def test_hold_reasons_name_why_a_result_is_a_suggestion() -> None:
    job = _job()
    db = _db(job, [2700] * 4)
    provider = FakeProvider(seasons={1: _season(1, [2700] * 10)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    assert outcomes[0].claims.suggestion is True
    assert "ambiguous" in outcomes[0].claims.extra["hold_reasons"]
    off = Config(episode_auto_apply=False)
    outcomes = await compute_episode_claims(db, job, [provider], off, StageOptions())
    assert outcomes[0].claims.extra["hold_reasons"][0] == "auto_apply_off"


async def test_empty_season_list_is_a_miss() -> None:
    job = _job(season=None)
    db = _db(job, DISC)
    provider = FakeProvider(season_list=[])
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    assert outcomes[0].claims.status == "miss"
    assert outcomes[0].claims.detail == "no seasons listed"
```

Also rewrite the existing test at `test_episode_stage.py:1196` (more seasons than the cap): it now asserts every season was fetched and `scan_truncated` is absent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest services/backend/tests/test_episode_stage.py -q -k "scan_order or every_season or sibling_season_is_tried or hold_reasons or empty_season_list"`
Expected: FAIL (`season_scan_order` undefined; `scan_truncated` present).

- [ ] **Step 3: Implement** `hint_season` in `pipeline.py`; `season_scan_order`, `sibling_seasons`, `hold_reasons` and the new `_pick_season`/`_match` flow in `episode_stage.py`; delete `MAX_SEASON_SCAN` from `registry.py` and its import; in `devtools/tv-match-baseline.py` replace `series.season_numbers()[:MAX_SEASON_SCAN]` with `series.season_numbers()` and drop the import.

The stop check inside `_pick_season` evaluates `hold_reasons` against the fits ranked so far, with `auto_apply=True` (the stop is about confidence, and a disabled auto-apply still marks the stored claim a suggestion via `_ok_claims`).

- [ ] **Step 4: Run the suite**

Run: `uv run pytest services/backend/tests/test_episode_stage.py services/backend/tests/test_stage_runner.py services/backend/tests/test_identity_router.py -q`
Expected: PASS. Then `uv run pytest -q --cov=arm_backend --cov-report=term-missing services/backend/tests | tail -5` shows no missing lines in `episode_stage.py` or `pipeline.py`.

- [ ] **Step 5: Update the docs** in `02-job-lifecycle.md`, "Episode matching": replace "a thin or truncated season scan" with the scan order (hint, sibling seasons, the rest), the stop rule (only a hint- or sibling-proposed season can stop the scan), and the `hold_reasons` codes. Describe the current behaviour only.

- [ ] **Step 6: Lint and commit**

```bash
uv run pre-commit run --files services/backend/arm_backend/identity/episode_stage.py services/backend/arm_backend/identity/pipeline.py services/backend/arm_backend/identity/sources/registry.py devtools/tv-match-baseline.py services/backend/tests/test_episode_stage.py
git add -A services/backend/arm_backend/identity services/backend/tests/test_episode_stage.py devtools/tv-match-baseline.py docs/developers/architecture/02-job-lifecycle.md
git commit -m "feat(identity): scan every season in hint order and record why a match is held"
```

---

### Task 2: The anchor counts only episode-shaped titles

**Files:**
- Modify: `services/backend/arm_backend/identity/episode_stage.py` (`_fit_season`)
- Test: `services/backend/tests/test_episode_stage.py`

**Interfaces:**
- Produces: `def episode_shaped_count(titles: Sequence[TitleIn], episodes: Sequence[Episode], tolerance: int) -> int`: titles whose `seconds` lie within `[min_rt - tolerance, max_rt + tolerance]` over the episodes with a known runtime; `len(titles)` when no runtime is known. `_fit_season` passes this as `n_titles` to `start_anchor`.

- [ ] **Step 1: Write the failing test**

```python
async def test_anchor_ignores_extras_when_counting_titles() -> None:
    # Four 45-minute episodes and ten 2-minute extras on disc 2 of 3 of a ten-episode season.
    job = _job(disc_number=2, disc_total=3)
    db = _db(job, [2700] * 4 + [120] * 10)
    provider = FakeProvider(seasons={1: _season(1, [2700] * 10)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    placed = sorted(c.episode for c in outcomes[0].claims.tracks.values() if c.episode is not None)
    assert placed == [4, 5, 6, 7]
    assert episode_stage.episode_shaped_count([TitleIn("a", 2700), TitleIn("b", 120)], _season(1, [2700] * 3), 300) == 1
    assert episode_stage.episode_shaped_count([TitleIn("a", 2700), TitleIn("b", 120)], _season(1, [None] * 3), 300) == 2
```

(`TitleIn` is imported from `arm_backend.identity.episodes.model`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest services/backend/tests/test_episode_stage.py -q -k anchor_ignores_extras`
Expected: FAIL, placed starts at 1.

- [ ] **Step 3: Implement** `episode_shaped_count` and use it in `_fit_season`.

- [ ] **Step 4: Run**: same command, PASS; then `uv run pytest services/backend/tests/test_episode_stage.py -q`.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/episode_stage.py services/backend/tests/test_episode_stage.py
git commit -m "fix(identity): anchor the disc by its episode-shaped titles, not its extras"
```

---

### Task 3: Siblings by show id

**Files:**
- Modify: `services/backend/arm_backend/identity/episode_stage.py` (`_sibling_rows`)
- Test: `services/backend/tests/test_episode_stage.py`

**Interfaces:**
- `_sibling_rows(session, job)` selects `Job` rows with `media_type == MediaType.TV`, drops `job.id` and `_DEAD_STATUSES` in Python (as now), and returns `[]` when `current_ids(job).model_dump(exclude_none=True)` is empty. No title comparison. `_siblings` is unchanged (it already requires a shared id).

- [ ] **Step 1: Write the failing tests**

```python
async def test_siblings_match_by_show_id_not_title_string() -> None:
    job = _job(disc_number=2, title="The Office")
    sibling = _job("job_2", disc_number=1, title="The Office (US)")
    sib_tracks = [_track("job_2", i, s, role=TrackRole.EPISODE, season=1, episode_number=i + 1) for i, s in enumerate(DISTINCT[:2])]
    db = _db(job, DISC, sibling, extra_tracks=sib_tracks)
    rows = await episode_stage._sibling_rows(db, job)
    assert [j.id for j, _ in rows] == ["job_2"]
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    placed = {c.episode for c in outcomes[0].claims.tracks.values() if c.episode is not None}
    assert placed.isdisjoint({1, 2})


async def test_job_without_ids_has_no_siblings() -> None:
    job = _job(ids={}, disc_number=2)
    db = _db(job, DISC, _job("job_2", disc_number=1))
    assert await episode_stage._sibling_rows(db, job) == []
```

Replace the existing `test_job_without_title_has_no_siblings` with the second test.

- [ ] **Step 2: Run to verify failure**: `uv run pytest services/backend/tests/test_episode_stage.py -q -k "show_id_not_title or without_ids"`. Expected: FAIL.

- [ ] **Step 3: Implement** the `_sibling_rows` change.

- [ ] **Step 4: Run** `uv run pytest services/backend/tests/test_episode_stage.py services/backend/tests/test_stage_runner.py -q`. PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/episode_stage.py services/backend/tests/test_episode_stage.py
git commit -m "fix(identity): sibling discs are found by show id, not by title string"
```

---

### Task 4: Operator-placed tracks constrain the matcher

**Files:**
- Modify: `services/backend/arm_backend/identity/episode_stage.py` (`_eligible`, `_Request`, `_fit_season`, `compute_episode_claims`)
- Test: `services/backend/tests/test_episode_stage.py`

**Interfaces:**
- Produces: `def operator_placed(tracks: Sequence[Track]) -> dict[int, frozenset[int]]`: season -> episode numbers (ranges expanded via `episode_number_end`) for tracks with `identity_provenance.get("episode_number") == "manual"`, `role == TrackRole.EPISODE` and a season.
- `_eligible` also skips those tracks (they are not aligned).
- `_Request.placed: Mapping[int, frozenset[int]]`; `_fit_season` appends `SiblingDisc(None, req.placed.get(season, frozenset()))` to `siblings` when non-empty, so `start_anchor` removes them from `remaining` and `align_runs` splits runs around them. A placed track in another season removes nothing from this season.

- [ ] **Step 1: Write the failing tests**

```python
async def test_operator_placed_track_is_excluded_and_its_episode_reserved() -> None:
    job = _job()
    db = _db(job, DISC)
    hand = _tracks(db, job)["1"]
    hand.role, hand.season, hand.episode_number = TrackRole.EPISODE, 1, 4
    hand.identity_provenance = {"episode_number": "manual", "season": "manual", "role": "manual"}
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    claims = outcomes[0].claims
    assert "1" not in claims.tracks
    assert 4 not in {c.episode for c in claims.tracks.values()}
    assert episode_stage.operator_placed([hand]) == {1: frozenset({4})}


async def test_operator_placed_track_in_another_season_reserves_nothing_here() -> None:
    job = _job()
    hand = _track("job_1", 9, 999, role=TrackRole.EPISODE, season=2, episode_number=4,
                  identity_provenance={"episode_number": "manual", "season": "manual"})
    db = _db(job, DISC, extra_tracks=[hand])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions())
    claims = outcomes[0].claims
    assert "9" not in claims.tracks
    assert 4 in {c.episode for c in claims.tracks.values()}
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest services/backend/tests/test_episode_stage.py -q -k operator_placed`. Expected: FAIL.

- [ ] **Step 3: Implement** `operator_placed`, the `_eligible` skip, `_Request.placed`, and the `_fit_season` reservation.

- [ ] **Step 4: Run** `uv run pytest services/backend/tests/test_episode_stage.py -q`. PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/episode_stage.py services/backend/tests/test_episode_stage.py
git commit -m "feat(identity): a re-run fills around the operator's placed tracks"
```

---

### Task 5: `scan_seasons` on the match request and a seasons endpoint

**Files:**
- Modify: `packages/arm_common/arm_common/schemas/identity_api.py` (`MatchRequest.scan_seasons`, `SeasonListView`)
- Modify: `services/backend/arm_backend/identity/episode_stage.py` (`StageOptions.scan_seasons`, `_known_season`)
- Modify: `services/backend/arm_backend/routers/identity.py` (pass the flag; `GET /{job_id}/identity/seasons`)
- Modify: `docs/developers/architecture/02-job-lifecycle.md` (endpoint list)
- Regenerate: `services/ui-neu/openapi.snapshot.json`, `services/ui-neu/frontend/src/lib/types/api.gen.ts`
- Test: `services/backend/tests/test_identity_router.py`, `services/backend/tests/test_episode_stage.py`

**Interfaces:**
- `MatchRequest.scan_seasons: bool = False`; a `model_validator(mode="after")` raises `ValueError("season and scan_seasons are exclusive")` when both `season is not None` and `scan_seasons`.
- `class SeasonListView(BaseModel): source_id: str; show_id: str; seasons: list[int]`.
- `StageOptions.scan_seasons: bool = False`; `_known_season` returns `None` when it is set.
- Router: `_browse_show_id(provider, cfg, job, source) -> str` extracted from `_browse_season` (configured / backing off / id resolution / 404); `_browse_season` calls it. `browse_seasons` (`GET /{job_id}/identity/seasons`, `source: EpisodeSourceSetting`, `require_jwt`) returns `SeasonListView(source_id, show_id, seasons=await provider.seasons(show_id))`, mapping `SourceError` to 502 and any other exception to 502 as `browse_episodes` does.

- [ ] **Step 1: Write the failing tests**

In `test_identity_router.py` (same fixtures as the `/identity/episodes` tests):

```python
def test_seasons_browse_happy_path(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT), 2: _season(2, DISTINCT)})
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{JOB_ID}/identity/seasons", params={"source": "tmdb"}, headers=_auth(admin_token))
    assert r.status_code == 200
    assert r.json() == {"source_id": "episodes_tmdb", "show_id": "100", "seasons": [1, 2]}


def test_seasons_browse_without_show_id_404(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    runner = _FakeStageRunner([FakeProvider(show_id=None)])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{JOB_ID}/identity/seasons", params={"source": "tmdb"}, headers=_auth(admin_token))
    assert r.status_code == 404


def test_match_season_and_scan_seasons_together_422(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=_FakeStageRunner([FakeProvider()]))
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"season": 2, "scan_seasons": True}, headers=_auth(admin_token))
    assert r.status_code == 422
```

In `test_episode_stage.py`:

```python
async def test_scan_seasons_option_ignores_the_job_season() -> None:
    job = _job(season=1)
    db = _db(job, DISC)
    provider = FakeProvider(seasons={1: _season(1, [600 + i for i in range(10)]), 2: _season(2, DISTINCT)})
    outcomes = await compute_episode_claims(db, job, [provider], CFG, StageOptions(scan_seasons=True))
    assert outcomes[0].claims.job.season == 2
    assert outcomes[0].claims.inputs["season"] is None
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest services/backend/tests/test_identity_router.py services/backend/tests/test_episode_stage.py -q -k "seasons_browse or scan_seasons"`. Expected: FAIL (404 route, unknown field).

- [ ] **Step 3: Implement** the schema, option, router changes.

- [ ] **Step 4: Run** the two suites, PASS. Then regenerate the wire contract:

```bash
bash devtools/regen-openapi-snapshot.sh
bash services/ui-neu/scripts/codegen.sh
git status --short services/ui-neu   # snapshot + api.gen.ts changed
```

- [ ] **Step 5: Docs**: in `02-job-lifecycle.md` "Episode matching", add `GET /api/jobs/{id}/identity/seasons` to the endpoint list and say that `scan_seasons` on `/identity/match` scans every season regardless of the job's season.

- [ ] **Step 6: Lint and commit**

```bash
uv run pre-commit run --files packages/arm_common/arm_common/schemas/identity_api.py services/backend/arm_backend/routers/identity.py services/backend/arm_backend/identity/episode_stage.py services/backend/tests/test_identity_router.py services/backend/tests/test_episode_stage.py
git add -A packages/arm_common services/backend services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts docs/developers/architecture/02-job-lifecycle.md
git commit -m "feat(identity): scan_seasons on match and a seasons list endpoint"
```

---

### Task 6: Clearing a season or disc position forgets the operator's value

**Files:**
- Modify: `services/backend/arm_backend/identity/proposals.py` (`record_manual_job`)
- Test: `services/backend/tests/test_identity_proposals.py`

**Interfaces:**
- `record_manual_job(job, edits, *, keep_restated=False) -> bool`: an edit whose value is `None` removes that field from the manual job claim (and is never filtered as "restated"); returns True when the stored claim changed. The resolver then does the rest: with the manual owner gone, `_apply_one` resets the field to its default, or applies the next proposer.

- [ ] **Step 1: Write the failing tests** (use the module's existing job/claims helpers)

```python
# Uses this module's `_job()` / `_track()` / `NOW`; `resolve` and `apply_resolution` from
# arm_backend.identity.resolver; `JobClaim` from arm_common.schemas.identity.
TIERS = {"manual": 1, "label": 4}


def test_clearing_a_manual_field_removes_the_claim() -> None:
    job = _job()
    put_source(job, "label", SourceClaims(run_at=NOW, status="ok", job=JobClaim(season=3)))
    record_manual_job(job, {"season": 7})
    assert claims_of(job).sources["manual"].job.season == 7
    assert record_manual_job(job, {"season": None}) is True
    assert "season" not in claims_of(job).sources["manual"].job.model_fields_set
    res = resolve(claims_of(job), tiers=TIERS)
    assert res.job["season"].value == 3 and res.job["season"].source == "label"


def test_clearing_with_no_other_proposer_empties_the_field_and_keeps_track_seasons() -> None:
    job = _job()
    track = _track("t1")
    track.season = 7
    record_manual_job(job, {"season": 7})
    apply_resolution(job, [track], resolve(claims_of(job), tiers=TIERS))
    assert job.season == 7
    record_manual_job(job, {"season": None})
    apply_resolution(job, [track], resolve(claims_of(job), tiers=TIERS))
    assert job.season is None and "season" not in (job.identity_provenance or {})
    assert track.season == 7
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest services/backend/tests/test_identity_proposals.py -q -k clearing`. Expected: FAIL.

- [ ] **Step 3: Implement** in `record_manual_job`: split `edits` into `clears` (value None) and `sets`; apply the restated filter to `sets` only; pop each clear from `merged`; return True when `merged` differs from the stored claim.

- [ ] **Step 4: Run** `uv run pytest services/backend/tests/test_identity_proposals.py services/backend/tests/test_jobs*.py -q`. PASS. The `/resolve` route needs no change: it already passes explicit nulls to `record_manual_job`.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/proposals.py services/backend/tests/test_identity_proposals.py
git commit -m "fix(identity): clearing season or disc position forgets the operator's value"
```

---

### Task 7: TheDiscDB claims the job's season and disc position

**Files:**
- Modify: `services/backend/arm_backend/identity/sources/thediscdb_snapshot.py` (`_SCHEMA`, `_write_index`, `DiscMatch`, `SnapshotStore.lookup`)
- Modify: `services/backend/arm_backend/identity/sources/thediscdb.py` (`build_claims`)
- Test: `services/backend/tests/test_thediscdb_snapshot.py`, `services/backend/tests/test_identity_thediscdb.py`

**Interfaces:**
- `_SCHEMA` adds `release_seasons TEXT` (JSON list of ints, or NULL). `_write_index` computes, per `(kind, title_dir, release_dir)`, the sorted set of `int(Item.Season)` over every disc's `Titles` whose `Item.Type == "Episode"`, and stores it (NULL when empty).
- `DiscMatch.release_seasons: list[int] | None = None`.
- `SnapshotStore.lookup` selects the column; on `sqlite3.OperationalError` (old index) it re-runs the old SELECT and returns `release_seasons=None`.
- `build_claims` adds `job=JobClaim(season=s)` when exactly one season appears across the disc's Episode titles, and `disc_number=int(disc["Index"])` when `match.release_seasons` has exactly one element and `Index` is an int. Otherwise `job=JobClaim()` as today.

- [ ] **Step 1: Write the failing tests**

`test_thediscdb_snapshot.py`: extend `_mini_tarball` to accept a list of `(release_dir, disc_obj)` so one series release has two discs with `Item.Season` 1 and 2:

```python
def test_index_records_the_release_seasons(tmp_path: Path) -> None:
    tarball = _series_tarball(tmp_path, discs=[("season-1-2", DISC_S1), ("season-1-2", DISC_S2)])
    build_index(tarball, tmp_path / "index.sqlite")
    hit = SnapshotStore(tmp_path).lookup(DISC_S1["ContentHash"])
    assert hit is not None and hit.release_seasons == [1, 2]


def test_lookup_tolerates_an_index_without_release_seasons(tmp_path: Path) -> None:
    # Build with the current schema, then drop the column to imitate an old index.
    ...; conn.execute("ALTER TABLE discs DROP COLUMN release_seasons"); ...
    hit = SnapshotStore(tmp_path).lookup(DISC["ContentHash"])
    assert hit is not None and hit.release_seasons is None
```

`test_identity_thediscdb.py`:

```python
def test_build_claims_claims_the_season_and_disc_for_a_single_season_release() -> None:
    match = _match(_EPISODES_S3, kind="series"); match.disc["Index"] = 2; match.release_seasons = [3]
    claims = build_claims(match, _scan(_EPISODES_S3), now=NOW)
    assert claims.job.season == 3 and claims.job.disc_number == 2


def test_build_claims_skips_disc_number_for_a_multi_season_release() -> None:
    match = _match(_EPISODES_S3, kind="series"); match.disc["Index"] = 14; match.release_seasons = [1, 2, 3, 4]
    claims = build_claims(match, _scan(_EPISODES_S3), now=NOW)
    assert claims.job.season == 3 and claims.job.disc_number is None


def test_build_claims_claims_no_season_when_titles_span_seasons() -> None:
    ...  # Item.Season 3 and 4 on one disc -> claims.job.season is None
```

`_EPISODES_S3`: three titles with `Item: {"Type": "Episode", "Season": "3", "Episode": "1".."3"}` and a `_scan` helper that produces matching `ScanTitle`s by SourceFile.

- [ ] **Step 2: Run to verify failure**: `uv run pytest services/backend/tests/test_thediscdb_snapshot.py services/backend/tests/test_identity_thediscdb.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** schema, writer, `DiscMatch`, `lookup` fallback, `build_claims`.

- [ ] **Step 4: Run** the two suites and every suite that imports `build_claims` (`grep -l build_claims services/backend/tests/*.py`); PASS, coverage complete for both modules.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/sources/thediscdb_snapshot.py services/backend/arm_backend/identity/sources/thediscdb.py services/backend/tests/test_thediscdb_snapshot.py services/backend/tests/test_identity_thediscdb.py
git commit -m "feat(thediscdb): claim the job's season, and its disc number on single-season releases"
```

---

### Task 8: ASCII copy in the touched components, with a test that keeps it so

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/DiscReviewWidget.svelte`, `JobInfoForm.svelte`, `episodes/EpisodeMatchPanel.svelte`, `episodes/EpisodeRows.svelte`, `episodes/RerunPanel.svelte`
- Create: `services/ui-neu/frontend/src/lib/components/__tests__/ascii-copy.test.ts`

**Interfaces:** none. Replacements, character for character, no rewording:

| file | old | new |
|---|---|---|
| `EpisodeRows.svelte` | `'—'` (empty placeholder, four places) and `<span class="episode-rows-muted">—</span>` | `'-'` |
| `EpisodeRows.svelte` | `` `Auto · ${label}` ``, `` `Suggestion · ${label}` ``, `Proposed · {proposedLabel}` | `, ` separator |
| `EpisodeRows.svelte` | `Change…` | `Change...` |
| `EpisodeMatchPanel.svelte` | `Matching episodes…`, `Loading episodes…`, `Accepting…`, `Unpin…`, `Previewing…` (also in `RerunPanel.svelte`) | `...` |
| `EpisodeMatchPanel.svelte` | `` ` · ${Math.round(e.runtime_s / 60)}m` `` and `` ` · special` `` | `, ` |
| `DiscReviewWidget.svelte` | `.join(' · ')` (three places), `` `${displayJob.year}–${end}` `` | `.join(', ')`, `-` |
| `DiscReviewWidget.svelte` | `·` prefixes in the SHOW row markup (`· {matchDetail}`, `· {missLine ...}`) | `, ` |

Also update any existing tests whose expectations contain these characters.

- [ ] **Step 1: Write the failing test** `ascii-copy.test.ts`: reads the five component sources with `fs.readFileSync` and asserts none matches `/[—–·…→✓✗⚠]/` outside `<style>` blocks and `//` comments; also renders `EpisodeRows` with an unplaced row and asserts `screen.getAllByText('-').length > 0`.

- [ ] **Step 2: Run to verify failure**: `npx vitest run src/lib/components/__tests__/ascii-copy.test.ts`. Expected: FAIL, listing the files.

- [ ] **Step 3: Apply the replacements** above and fix expectations in the existing tests (`grep -rn "—\|…\|·" src/lib/components --include=*.test.ts`).

- [ ] **Step 4: Run** `npx vitest run src/lib/components`, PASS; `npm run lint && npm run format:check`.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components
git commit -m "style(ui): ASCII punctuation in the review card and episode panel copy"
```

---

### Task 9: Season in the Info form, with provenance, on the card and the job page

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/api/jobs.ts` (`resolveJob` body gains `season?: number | null`)
- Modify: `services/ui-neu/frontend/src/lib/api/identity.ts` (`fetchSeasons`)
- Create: `services/ui-neu/frontend/src/lib/utils/provenance.ts`
- Modify: `services/ui-neu/frontend/src/lib/components/JobInfoForm.svelte`
- Modify: `services/ui-neu/frontend/src/routes/jobs/[id]/+page.svelte` (Info tab)
- Test: `services/ui-neu/frontend/src/lib/components/JobInfoForm.test.ts`, `services/ui-neu/frontend/src/lib/utils/provenance.test.ts`, `services/ui-neu/frontend/src/routes/jobs/[id]/page.test.ts`

**Interfaces:**
- `fetchSeasons(jobId: string, source: EpisodeSource): Promise<SeasonListView>` -> `GET /api/jobs/${jobId}/identity/seasons?source=${source}`.
- `provenance.ts`: `export const PROVENANCE_LABEL: Record<string, string>` = `{ manual: 'set by you', label: 'from the disc label', bd_title: 'from the Blu-ray disc title', thediscdb: 'from TheDiscDB', episodes_tmdb: 'matched by TMDb', episodes_tvmaze: 'matched by TVmaze', episodes_tvdb: 'matched by TVDB' }`; `export function provenanceLine(field: 'season' | 'disc_number' | 'disc_total', prov: Record<string, string> | null | undefined): string | null` -> e.g. `"Season from the disc label"`, `"Disc number set by you"`, null when unset or unknown source.
- `JobInfoForm` props gain `onsaved?: (changed: { season: boolean; disc: boolean }) => void`, called after a successful save with which groups changed versus the job's values before the save. The Disc section renders Season, Disc number, Disc total (aria-labels "Season", "Disc number", "Disc total"), help text exactly: `For TV box sets, the season on this disc and the disc's position in it. Leave blank when unknown.`, and a muted `<p class="field-help">` per set field from `provenanceLine`. Save sends `season: num(season)` with the other fields; `season` is sent only when touched (omitted = keep, per the backend's rule).
- Job page: a fourth panel tab "Info" (`activePanel === 'info'`) renders `<JobInfoForm {job} onrefresh={() => loadJob()} onsaved={handleInfoSaved} />`; `handleInfoSaved` starts `matching` when `job.media_type === 'tv'` and `changed.season || changed.disc`.

- [ ] **Step 1: Write the failing tests**

`provenance.test.ts`:
```ts
it('names where a season came from', () => {
  expect(provenanceLine('season', { season: 'label' })).toBe('Season from the disc label');
  expect(provenanceLine('disc_number', { disc_number: 'manual' })).toBe('Disc number set by you');
  expect(provenanceLine('season', { season: 'episodes_tmdb' })).toBe('Season matched by TMDb');
  expect(provenanceLine('season', {})).toBeNull();
  expect(provenanceLine('season', { season: 'bogus' })).toBeNull();
});
```

`JobInfoForm.test.ts`:
```ts
it('shows the season empty when unknown and saves a typed season', async () => {
  mockResolve.mockResolvedValue({} as any);
  const onsaved = vi.fn();
  renderComponent(JobInfoForm, { job: job({ season: null }), onsaved });
  const season = screen.getByLabelText('Season') as HTMLInputElement;
  expect(season.value).toBe('');
  await fireEvent.input(season, { target: { value: '7' } });
  await fireEvent.click(screen.getByText('Save'));
  await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('job_1', expect.objectContaining({ season: 7 })));
  expect(onsaved).toHaveBeenCalledWith({ season: true, disc: false });
});
it('clears a season by sending null', ...);                 // typed '' on a job with season 7 -> season: null
it('does not send season when untouched', ...);              // title edit only -> body has no `season` key
it('shows the provenance line for a set season', ...);       // identity_provenance {season:'label'} -> "Season from the disc label"
```

`page.test.ts`: `it('has an Info tab that mounts the info form', ...)` asserting the "Season" input renders after clicking the "Info" tab.

- [ ] **Step 2: Run to verify failure**

Run: `cd services/ui-neu/frontend && npx vitest run src/lib/components/JobInfoForm.test.ts src/lib/utils/provenance.test.ts "src/routes/jobs/[id]/page.test.ts"`
Expected: FAIL.

- [ ] **Step 3: Implement** the API functions, `provenance.ts`, the form, the page tab.

- [ ] **Step 4: Run** the three test files, PASS; then `npm run check && npm run lint`.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/api services/ui-neu/frontend/src/lib/utils/provenance.ts services/ui-neu/frontend/src/lib/utils/provenance.test.ts services/ui-neu/frontend/src/lib/components/JobInfoForm.svelte services/ui-neu/frontend/src/lib/components/JobInfoForm.test.ts "services/ui-neu/frontend/src/routes/jobs/[id]"
git commit -m "feat(ui): season is shown and edited next to disc number, on the card and the job page"
```

---

### Task 10: The review card shows an unset season and re-matches after an Info save

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/DiscReviewWidget.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/DiscReviewWidget.episodes.test.ts`

**Interfaces:**
- Consumes `JobInfoForm.onsaved` from Task 9.
- `matchDetail` for `isTv && !isPostRip && jobMeta.season == null` ends with `Season not set` (joined with the same separator as the other parts). The `JobInfoForm` mount passes `onsaved={(c) => { if (isTv && (c.season || c.disc)) matching.start(); }}` in addition to the existing `onrefresh`.

- [ ] **Step 1: Write the failing tests**

```ts
it('says the season is not set for a pre-rip TV job without one', async () => { ... expect(await screen.findByText(/Season not set/)).toBeTruthy(); });
it('does not say it for a ripped job or when a season is known', ...);
it('starts matching when Info saves a season on a TV job', async () => { ... click Info, type 7 in Season, Save; expect(await screen.findByText('Matching episodes...')).toBeTruthy(); });
```

- [ ] **Step 2: Run to verify failure**: `npx vitest run src/lib/components/DiscReviewWidget.episodes.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** the card's three test files, PASS; `npm run check && npm run lint`.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components/DiscReviewWidget.svelte services/ui-neu/frontend/src/lib/components/DiscReviewWidget.episodes.test.ts
git commit -m "feat(ui): the review card shows an unset season and re-matches after an Info save"
```

---

### Task 11: The match panel assumes no season, lists candidate seasons, and explains a hold

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/episodeModel.ts`
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/EpisodeMatchPanel.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/RerunPanel.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/episodes/__tests__/episodeModel.test.ts`, `.../__tests__/EpisodeMatchPanel.test.ts`

**Interfaces:**
- `RerunForm.season: number | 'scan' | null`.
- `episodeModel.ts` adds:
  - `export const HOLD_REASON_TEXT: Record<string, string>` with exactly the spec's eight sentences (4.2 E), keyed by code.
  - `export function holdReasons(identity: IdentityView, source: string | null): string[]` -> sentences for `identity.sources[source].extra.hold_reasons`, unknown codes dropped.
  - `export function seasonAlternatives(identity: IdentityView, source: string | null): { season: number; matches: number; total: number }[]` from `sources[source].alternatives` (`season`, `matches`; `total` is the row count the panel passes in).
- `RerunPanel` props gain `seasons: number[] | null` (null = list unavailable: render the number input instead) and render the season as a `<select>` with options: `Scan all seasons` (value `scan`), `Specials` (0), then each listed season as `Season n`; preselects `form.season`.
- `EpisodeMatchPanel`:
  - `openRerun()` seeds `season: job.season ?? null`, `disc: job.disc_number ?? null`; the module-level default is `{ source: 'tmdb', season: null, disc: null, tolerance: null }`.
  - loads `fetchSeasons(job.id, rerun.source)` when the re-run opens or the source changes; on failure `seasons = null`.
  - `request(apply)` sends `scan_seasons: true` for `'scan'`, `season` for a number, nothing for null.
  - Under the status line, when `seasonAlternatives` is non-empty or the view is `suggestion`: a row of `btn btn-sm` buttons `Season 3 (6 of 6 titles)` running `run({ source: pickerSource, season, disc_number: job.disc_number ?? undefined, apply: false })`; the held result's own season appears first.
  - The suggestion alert lists `holdReasons(...)` as `<p class="alert-body">` lines and then `Set the season or disc number in Info, or accept the suggestion.`
  - The episode browser uses `job.season` with no fallback; with no season it fetches nothing (Task 12 gives rows their own season control).

- [ ] **Step 1: Write the failing tests**

`episodeModel.test.ts`:
```ts
it('maps hold reason codes to sentences and drops unknown ones', () => {
  const id = { sources: { episodes_tmdb: { status: 'ok', suggestion: true, extra: { hold_reasons: ['near_tie', 'bogus'] } } } } as any;
  expect(holdReasons(id, 'episodes_tmdb')).toEqual(['Another season fits about as well.']);
});
it('lists candidate seasons from alternatives', () => {
  const id = { sources: { episodes_tmdb: { status: 'ok', alternatives: [{ season: 3, coverage: 1, matches: 6 }] } } } as any;
  expect(seasonAlternatives(id, 'episodes_tmdb')).toEqual([{ season: 3, matches: 6, total: 0 }]);
});
```

`EpisodeMatchPanel.test.ts`:
```ts
it('opens the re-run form with no season when the job has none', ...);     // select value '' / option none selected, disc empty
it('offers Scan all seasons and sends scan_seasons', ...);                 // matchIdentity called with { scan_seasons: true } and no season
it('lists the seasons from the seasons endpoint', ...);                    // fetchSeasons mocked -> options Season 1..3
it('falls back to a number input when the season list fails', ...);
it('shows a candidate season button that previews that season', ...);     // alternatives -> button text 'Season 3 (6 of 6 titles)', click -> matchIdentity season 3 apply false
it('explains why a result is held', ...);                                   // hold_reasons ['ambiguous'] -> sentence present + closing line
```

Add `fetchSeasons: vi.fn(() => Promise.resolve({ source_id: 'episodes_tmdb', show_id: '5084', seasons: [1, 2, 3] }))` to the `$lib/api/identity` mock.

- [ ] **Step 2: Run to verify failure**: `npx vitest run src/lib/components/episodes`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** `npx vitest run src/lib/components/episodes src/lib/components/DiscReviewWidget.episodes.test.ts`, PASS; `npm run check && npm run lint`.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components/episodes
git commit -m "feat(ui): the match panel assumes no season, lists candidate seasons, and explains a hold"
```

---

### Task 12: Per-row season, a runtime-sorted picker, and Fill the rest

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/episodeModel.ts`
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/EpisodeRows.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/EpisodeMatchPanel.svelte`
- Test: `.../__tests__/episodeModel.test.ts`, `.../__tests__/EpisodeMatchPanel.test.ts`

**Interfaces:**
- `EpisodeRow` gains `season: number | null` and `seconds: number | null` (from `TrackView.season`/`TrackView.duration_seconds`; the identity view's track season when set).
- `episodeModel.ts` adds `export function pickerOptions(episodes: EpisodeSummary[], season: number, seconds: number | null, used: Set<number>): { value: string; label: string }[]`: one option per episode, `value` `s{season}e{n}` (`s0e{n}` for specials), label `E03 Name, 44m` (`S00E03 Name, 44m, special` for specials), sorted by `|runtime_s - seconds|` ascending (unknown runtime last, then by number) with `used` episodes labelled `... (used)` and sorted after the rest; the role options follow as today.
- `EpisodeRows` props: `seasons: number[] | null` and `onseason?: (trackId: string, season: number) => void`; `options` becomes `optionsFor?: (row: EpisodeRow) => { value: string; label: string }[] | null`. Each row's by-hand cell renders a season `<select>` (aria-label `Season for {row.ref}`, options `Specials`, `Season n`..., value `row.season ?? panelSeason ?? ''`) before the episode `<select>` (aria-label unchanged); the episode select is disabled until the row has a season.
- `EpisodeMatchPanel`:
  - `rowSeason: Record<string, number>` state for rows without a saved season; `onseason` saves `{ season }` for a row that already has an episode, else stores `rowSeason[trackId]` and loads that season's episodes into `episodesBySeason: Map<number, EpisodeSummary[]>` via `fetchEpisodes`.
  - `optionsFor(row)` -> `pickerOptions(episodesBySeason.get(season) ?? [], season, row.seconds, usedIn(season))` where `season = row.season ?? rowSeason[row.trackId] ?? job.season` and `usedIn` collects the episode numbers of the other rows in that season.
  - `setByHand` saves `{ role: 'episode', season, episode_number, episode_name }` from the picked value, as today.
  - A `Fill the rest` button (`btn btn-sm`) appears when `rows.some(r => r.handSet) && rows.some(r => r.code === 'Not placed')`; it runs `run({ source: pickerSource, season: job.season ?? undefined, disc_number: job.disc_number ?? undefined, apply: false })` and the existing preview UI shows the result with Apply.

- [ ] **Step 1: Write the failing tests**

`episodeModel.test.ts`:
```ts
it('sorts picker options by runtime fit and pushes used episodes last', () => {
  const eps = [{ number: 1, name: 'A', runtime_s: 2700 }, { number: 2, name: 'B', runtime_s: 1500 }, { number: 3, name: 'C', runtime_s: 1520 }] as any;
  const labels = pickerOptions(eps, 2, 1510, new Set([3])).map((o) => o.label);
  expect(labels.slice(0, 3)).toEqual(['E02 B, 25m', 'E01 A, 45m', 'E03 C, 25m (used)']);
  expect(pickerOptions(eps, 2, 1510, new Set())[0].value).toBe('s2e2');
});
```

`EpisodeMatchPanel.test.ts`:
```ts
it('gives each row a season control seeded from the job', ...);           // job season 4 -> every "Season for t0x" select shows 4
it('changing a row season reloads only that row episodes', ...);          // fetchEpisodes called with season 5 once; other rows unchanged
it('saves season and episode together from the picker', ...);            // updateTrack with { role: 'episode', season: 5, episode_number: 2, episode_name: ... }
it('offers Fill the rest after a hand pick and previews only', ...);     // one row handSet + unplaced -> button; click -> matchIdentity apply false, season = job season
```

- [ ] **Step 2: Run to verify failure**: `npx vitest run src/lib/components/episodes`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run** `npx vitest run src/lib/components/episodes src/lib/components/DiscReviewWidget.episodes.test.ts`, PASS; `npm run check && npm run lint`.

- [ ] **Step 5: Commit**

```bash
git add services/ui-neu/frontend/src/lib/components/episodes
git commit -m "feat(ui): per-track season, a runtime-sorted episode picker, and Fill the rest"
```

---

### Task 13: Corpus additions, baseline scenarios, and the regression test

**Files:**
- Modify: `devtools/thediscdb-fixture.py` (`SERIES` gains The Simpsons (1989) and Doctor Who (1963))
- Regenerate: `services/backend/tests/fixtures/thediscdb/*.json`, `manifest.json`
- Create: `services/backend/tests/tv_match_baseline.py` (the scenario engine, moved out of the devtools script)
- Modify: `devtools/tv-match-baseline.py` (thin CLI over the engine)
- Create: `services/backend/tests/test_tv_match_baseline.py`

**Interfaces:**
- `tests/tv_match_baseline.py`: `SCENARIOS`, `Tally`, `run(series, min_seconds) -> dict[str, Tally]`, `run_all(corpus, min_seconds) -> dict[str, Tally]`, plus two scenarios: `"nothing known, hint-ordered scan"` (the hint is the season parsed from the corpus disc `Name` with `re.search(r"Season (\d+)", name)`, fed through `season_scan_order` and the stop rule; mirrors Task 1) and `"season known, one track placed by hand"` (the oracle's first episode title is treated as operator-placed via `SiblingDisc(None, {episode})` and excluded from titles; mirrors Task 4).
- `Tally` gains `deep_wrong_season` and `deep_discs` (discs whose true season is 11 or more) so the deep-season rate can be compared with the rest.

- [ ] **Step 1: Regenerate the corpus**

```bash
uv run python -I devtools/thediscdb-fixture.py            # or --tarball <path> if the 1.5 GB tarball is already on disk
uv run pytest services/backend/tests/test_thediscdb_corpus.py -q
```
Expected: nine series in `manifest.json`; the smoke test passes.

- [ ] **Step 2: Write the failing regression test**

```python
BEFORE = {  # correct placements from the design doc's baseline table, --min-seconds 60
    "nothing known, scan": 134, "season known": 242, "season + disc known": 248,
    "season + disc, lower discs held": 467, "season + disc, higher discs held": 198, "season + disc, all others held": 381,
}
SEVEN = [...]  # the seven original slugs, so the floor compares like with like

def test_no_scenario_loses_correct_placements() -> None:
    corpus = {k: v for k, v in load_corpus().items() if k in SEVEN}
    tallies = run_all(corpus, 60)
    for name, floor in BEFORE.items():
        assert tallies[name].correct >= floor, name

def test_deep_seasons_pick_the_right_season_as_often_as_shallow_ones() -> None:
    t = run_all(load_corpus(), 60)["nothing known, scan"]
    deep_rate = t.deep_wrong_season / max(1, t.deep_discs)
    shallow_rate = (t.wrong_season - t.deep_wrong_season) / max(1, t.discs - t.deep_discs)
    assert deep_rate <= shallow_rate + 0.10

def test_a_hand_placed_track_is_never_duplicated() -> None:
    assert run_all(load_corpus(), 60)["season known, one track placed by hand"].duplicates == 0
```

(`Tally.duplicates`: matches proposing an episode the hand-placed track holds.)

- [ ] **Step 3: Run to verify failure**: `uv run pytest services/backend/tests/test_tv_match_baseline.py -q`. Expected: FAIL on import (engine module missing).

- [ ] **Step 4: Move the engine**, add the two scenarios and tally fields, make the CLI import it (`sys.path` insert of `services/backend` stays in the CLI only).

- [ ] **Step 5: Run** `uv run pytest services/backend/tests/test_tv_match_baseline.py services/backend/tests/test_thediscdb_corpus.py -q`, PASS; `uv run python devtools/tv-match-baseline.py --min-seconds 60` prints the table. Paste the "all series" block into the PR description next to the design doc's table.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run --files devtools/thediscdb-fixture.py devtools/tv-match-baseline.py services/backend/tests/tv_match_baseline.py services/backend/tests/test_tv_match_baseline.py
git add devtools services/backend/tests/fixtures/thediscdb services/backend/tests/tv_match_baseline.py services/backend/tests/test_tv_match_baseline.py
git commit -m "test(identity): deep-season series in the corpus and a baseline regression test"
```

---

### Task 14: Whole-branch check and PR

- [ ] **Step 1:** `uv run pytest -q` (all Python suites) and `cd services/ui-neu/frontend && npm run check && npm run lint && npm run format:check && npx vitest run`. All green.
- [ ] **Step 2:** `bash devtools/regen-openapi-snapshot.sh && git status --short` shows no change.
- [ ] **Step 3:** `uv run pre-commit run --all-files` clean.
- [ ] **Step 4:** Walk the design's Definition of done (section 7) against the running dev stack (`bash devtools/setup-dev.sh up`) with an ISO rip of a TV disc, or record which items could not be exercised without a disc.
- [ ] **Step 5:** Push to wolfy and open the PR against `feat/home-episode-match`, per `CLAUDE.local.md`'s workflow. The body links the design and the plan, carries the before/after baseline tables, and runs through the humanizer first.
