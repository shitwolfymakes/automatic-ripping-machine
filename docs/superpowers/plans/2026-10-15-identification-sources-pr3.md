# Identification Sources PR 3: Auto-Apply Hold Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three per-media-type "Apply confident matches" switches real: with a type's switch off, a confident online match is stored as a suggestion the operator confirms, and the disc waits in `awaiting_review` with no countdown; the Ripping › Review gate keeps precedence (spec D-10).

**Architecture:** Identify keeps its walk; only what it does with a hit changes. `auto_apply_for(cfg, kind)` maps a hit's kind to its switch (`movie_auto_apply`, `episode_auto_apply` for TV, `music_auto_apply`). When the switch is on, the hit is applied exactly as today (extracted into `apply_identity_result`). When it is off, the hit is stored as a typed `identity_suggestion` section in `metadata_json` (provider, title, year, kind, poster, ids, overview, raw payload), the job keeps the miss title and the `unidentified` flag, and it parks in `AWAITING_REVIEW` with `wait_start_time = None`, which the ripper already treats as "no countdown". The three places that already know a previously-ripped hold has no countdown (config un-pause, review-pause, the ripper's held-job probe) learn the suggestion hold the same way. A new `POST /api/jobs/{id}/identity/accept` applies the stored suggestion through the existing resolve path (extracted from the route into `resolve_identity`), so provenance, fan-out, the `identify.resolved` command and the episode stage all behave as for any resolve; accepting with the review gate off releases the rip, with it on starts the countdown. A resolve of a suggested job by any other means clears the suggestion. The two hidden toggles join the editable config surface (metadata, update request, PATCH validation, UI section, regenerated contract). No migration.

**Tech Stack:** Python 3.14, FastAPI, pydantic, pytest with the in-memory `FakeSession`, ruff via pre-commit, mypy; `bash devtools/regen-openapi-snapshot.sh` and `bash services/ui-neu/scripts/codegen.sh`; SvelteKit only for `settings-sections.ts` and its vitest.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (D-10, §5.4 "hidden until PR 3", §6 PR 3, §10) and issue #258's PR 3 bullet ("a hit is stored as a suggestion … the job parks in `awaiting_review` with `wait_start_time` null … `hold_for_review` + auto-apply on keeps today's countdown … No scoring of title hits: auto-apply is binary"). Branch: `feat/identification-sources-pr3` from `feat/identification-sources-pr2b` (PR #364).

## Global Constraints

- Switch per kind: `movie` → `movie_auto_apply`, `tv` → `episode_auto_apply` (the existing TV switch; spec D-8 lists exactly these three), `music` → `music_auto_apply`. Every identify result goes through the gate, including the TheDiscDB exact-id walk result and the release-metadata result (provider `thediscdb`): auto-apply is binary and source-blind.
- A hit that is not applied leaves `job.title` as the miss title (BDMT name → release title → raw label, exactly as a miss), `job.year`, `job.media_type`, `job.poster_url` unset, sets `flags.unidentified = True`, stores `metadata_json["identity_suggestion"]`, parks the job in `AWAITING_REVIEW` with `wait_start_time = None`, persists the review tracks (`_persist_review_tracks`), and emits `rip.awaiting_review` as any hold does. `block_on_miss` plays no part (it is a hit).
- `hold_for_review` on with the switch on keeps today's path unchanged (AWAITING_REVIEW with `wait_start_time = now`). With the switch off, the gate's countdown never starts while the suggestion is pending.
- A previously-ripped hold still wins over everything (unchanged code after the hit branch).
- `IdentitySuggestion` fields: `provider: str`, `title: str`, `year: int | None`, `kind: Literal["movie", "tv", "music"]`, `poster_url: str | None`, `external_ids: ExternalIds`, `overview: str | None`, `payload: dict[str, Any]`, `suggested_at: datetime`. Readers are lenient like `previously_ripped_job_id`: a malformed section reads as `None`.
- Accept (`POST /api/jobs/{job_id}/identity/accept`, writer auth, response `ResolveResponse`): 404 unknown job; 409 `job {id} has no identity suggestion to accept` when the section is absent; 409 with resolve's own message when the status is not resolvable. On success the suggestion is applied with `apply_identity_result`, the section is removed, and the status is set before delegating to `resolve_identity`: `AWAITING_REVIEW` + `hold_for_review` on → stays, `wait_start_time = now` (or `None` while `ripping_paused`); `AWAITING_REVIEW` + gate off → `IDENTIFIED` unless `ripping_paused`, in which case it stays held with `wait_start_time = None`; any other resolvable status is left to `resolve_identity`'s promote/preserve rule. The request passed on is `ResolveRequest(title, year, media_type=MediaType(kind), external_ids=external_ids_of(result))`.
- `resolve_identity(session, job, req, *, hub, stage_runner, before_identity=None)` is the body of today's `resolve` route from the `_identity_snapshot` line to the return; the route keeps the fetch and status check. It additionally drops `identity_suggestion` from the metadata it writes. The existing resolve tests must pass unchanged.
- No-countdown sites: `config.py` un-pause skips jobs with a suggestion (as it skips previously-ripped holds); `review-pause` answers 409 `this disc is waiting for you to confirm its identity; it has no countdown to pause`; `get_held_job` reports `paused=True` for a suggestion hold.
- Config surface: `movie_auto_apply` and `music_auto_apply` get `ConfigFieldMeta` entries (group `Metadata`, tier `operator`, `setup_step="metadata"` like `movie_sources`, type `bool`, editable), `ConfigUpdateRequest` fields, and the PATCH "must be true or false" rule shared with `episode_auto_apply`. Labels and help: `movie_auto_apply` label `Apply confident movie matches`, help `When off, a movie match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.`; `music_auto_apply` label `Apply confident music matches`, help `When off, an audio CD match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.`; `episode_auto_apply` keeps its label and its help becomes `When off, a TV show match and every episode match are kept as suggestions to confirm on the job page; the disc is held with no countdown. Ripping › Review first still holds every disc.`
- UI: `settings-sections.ts` "Movies and music" section gains the two toggles (`keys` and one per column under its list); no other UI change in this PR (the review card's suggestion display and Accept button are the UI redesign PR's). OpenAPI snapshot and `api.gen.ts` regenerated and committed.
- Tests zero-infra (`FakeSession`, fake dispatcher). Commits carry no attribution trailers.

## Review Focus

1. A music hit with `music_auto_apply` off must not set `disc_number` at hold time and must set it on accept (Task 2 hold test asserts `disc_number is None`; Task 4 accept test asserts it lands).
2. Un-pausing ripping must not stamp a countdown on a suggestion hold, or the disc auto-rips as an unidentified placeholder (Task 3 test).
3. A ripper restart must re-park a suggestion hold, not abandon it: `get_held_job` reports `paused=True` (Task 3 test).
4. Resolving a suggested job through the search dialog must clear the suggestion and the `unidentified` flag together, so a later accept is a 409 and the rip no longer parks for identity (Task 4 test).
5. Accept while `ripping_paused` with the gate off must not release the rip; the job stays held with no countdown until un-pause stamps one (Task 4 test).

---

### Task 1: Suggestion schema, readers, and the kind-to-switch map

**Files:**
- Modify: `packages/arm_common/arm_common/schemas/job_metadata.py`
- Modify: `packages/arm_common/arm_common/schemas/__init__.py` (export `IdentitySuggestion`, `identity_suggestion_of`, `without_identity_suggestion` next to `JobMetadata`/`previously_ripped_job_id`; follow the existing export style)
- Modify: `services/backend/arm_backend/identity/sources/registry.py`
- Test: `packages/arm_common/tests/test_job_metadata_suggestion.py` (new)
- Test: `services/backend/tests/test_identity_registry_online.py`

**Interfaces:**
- Produces: `IdentitySuggestion` (pydantic model, fields per Global Constraints), `JobMetadata.identity_suggestion: IdentitySuggestion | None`, `identity_suggestion_of(metadata_json) -> IdentitySuggestion | None`, `without_identity_suggestion(metadata_json) -> dict[str, Any]`, `auto_apply_for(cfg, kind: str) -> bool`.

- [ ] **Step 1: Write the failing schema tests**

```python
# packages/arm_common/tests/test_job_metadata_suggestion.py
from datetime import datetime, timezone

from arm_common.schemas.job_metadata import (
    ExternalIds,
    IdentitySuggestion,
    JobMetadata,
    identity_suggestion_of,
    without_identity_suggestion,
)


def _suggestion() -> dict:
    return {
        "provider": "tmdb",
        "title": "Iron Man",
        "year": 2008,
        "kind": "movie",
        "poster_url": "https://image.tmdb.org/t/p/w500/abc.jpg",
        "external_ids": {"imdb": "tt0371746", "tmdb": "1726", "tmdb_kind": "movie"},
        "overview": "Tony Stark.",
        "payload": {"id": 1726, "poster_path": "/abc.jpg"},
        "suggested_at": "2026-10-15T10:00:00Z",
    }


def test_job_metadata_parses_the_suggestion_section():
    md = JobMetadata.model_validate({"identity_suggestion": _suggestion()})
    assert md.identity_suggestion is not None
    assert md.identity_suggestion.title == "Iron Man"
    assert md.identity_suggestion.external_ids.imdb == "tt0371746"
    assert md.identity_suggestion.suggested_at == datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def test_identity_suggestion_of_reads_a_valid_section():
    s = identity_suggestion_of({"identity_suggestion": _suggestion(), "flags": {"unidentified": True}})
    assert isinstance(s, IdentitySuggestion)
    assert (s.provider, s.kind, s.year) == ("tmdb", "movie", 2008)


def test_identity_suggestion_of_is_none_when_absent_or_malformed():
    assert identity_suggestion_of(None) is None
    assert identity_suggestion_of({}) is None
    assert identity_suggestion_of({"identity_suggestion": "nope"}) is None
    assert identity_suggestion_of({"identity_suggestion": {"title": "no provider"}}) is None


def test_without_identity_suggestion_drops_only_that_section():
    md = {"identity_suggestion": _suggestion(), "flags": {"unidentified": True}, "scan_result": None}
    out = without_identity_suggestion(md)
    assert "identity_suggestion" not in out
    assert out["flags"] == {"unidentified": True}
    assert md["identity_suggestion"] is not None  # input untouched
    assert without_identity_suggestion(None) == {}


def test_identity_suggestion_external_ids_default_empty():
    s = IdentitySuggestion(provider="tvmaze", title="Lost", kind="tv", payload={}, suggested_at=datetime.now(timezone.utc))
    assert s.external_ids == ExternalIds()
    assert s.year is None and s.poster_url is None and s.overview is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/arm_common/tests/test_job_metadata_suggestion.py -q`
Expected: ImportError on `IdentitySuggestion`.

- [ ] **Step 3: Add the model, the field, and the readers**

In `job_metadata.py`, after `PreviouslyRipped`:

```python
class IdentitySuggestion(BaseModel):
    """A confident online match identify did not apply because the media
    type's "Apply confident matches" switch is off (identification-sources
    spec D-10). The job keeps its miss title and the `unidentified` flag and
    waits in AWAITING_REVIEW with no countdown until the operator accepts
    it (POST /api/jobs/{id}/identity/accept) or identifies the disc another
    way (any resolve clears this section)."""

    model_config = ConfigDict(extra="allow")

    provider: str
    title: str
    year: int | None = None
    kind: Literal["movie", "tv", "music"]
    poster_url: str | None = None
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    overview: str | None = None
    # The provider's raw hit, so accepting re-applies exactly what identify
    # would have applied (provider_raw, music section, disc number).
    payload: dict[str, Any] = Field(default_factory=dict)
    suggested_at: datetime
```

In `JobMetadata`, after `previously_ripped`:

```python
    # Set when a media type's auto-apply switch held a confident match for
    # the operator to confirm; no countdown runs while it is set.
    identity_suggestion: IdentitySuggestion | None = None
```

After `previously_ripped_job_id`:

```python
def identity_suggestion_of(metadata_json: dict[str, Any] | None) -> IdentitySuggestion | None:
    """The confident match a held job is waiting for the operator to
    confirm (see IdentitySuggestion), or None when absent or malformed."""
    section = (metadata_json or {}).get("identity_suggestion")
    if not isinstance(section, dict):
        return None
    try:
        return IdentitySuggestion.model_validate(section)
    except ValidationError:
        return None


def without_identity_suggestion(metadata_json: dict[str, Any] | None) -> dict[str, Any]:
    """A copy of the bag with the suggestion section removed."""
    md = dict(metadata_json or {})
    md.pop("identity_suggestion", None)
    return md
```

Add `ValidationError` to the pydantic import. Update the module docstring's list with one line: ``- `identity_suggestion` — a confident match held for the operator to confirm (auto-apply off; no countdown runs while it is set).``

- [ ] **Step 4: Run the schema tests**

Run: `uv run pytest packages/arm_common/tests/test_job_metadata_suggestion.py -q`
Expected: 5 passed.

- [ ] **Step 5: Write the failing registry test**

Append to `services/backend/tests/test_identity_registry_online.py`:

```python
def test_auto_apply_for_maps_each_kind_to_its_switch() -> None:
    from arm_backend.identity.sources.registry import auto_apply_for

    cfg = Config(id=1, movie_auto_apply=False, episode_auto_apply=True, music_auto_apply=False)
    assert auto_apply_for(cfg, "movie") is False
    assert auto_apply_for(cfg, "tv") is True
    assert auto_apply_for(cfg, "music") is False
    cfg.episode_auto_apply = False
    assert auto_apply_for(cfg, "tv") is False
    # Unknown kinds and a missing row apply (identify never holds what it cannot name).
    assert auto_apply_for(cfg, "weird") is True
    assert auto_apply_for(None, "movie") is True
```

(`Config` is already imported in that file; if the existing tests build it differently, match them.)

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest services/backend/tests/test_identity_registry_online.py -q -k auto_apply_for`
Expected: ImportError.

- [ ] **Step 7: Add `auto_apply_for`**

In `registry.py`, after `music_auto_apply`:

```python
def auto_apply_for(cfg: Config | None, kind: str) -> bool:
    """Whether a confident match of this kind is applied by identify (spec
    D-10: one switch per media type; TV shares the episode switch). An
    unknown kind applies: identify never holds a hit it cannot classify."""
    if kind == "movie":
        return movie_auto_apply(cfg)
    if kind == "tv":
        return episode_auto_apply(cfg)
    if kind == "music":
        return music_auto_apply(cfg)
    return True
```

- [ ] **Step 8: Run both test files**

Run: `uv run pytest packages/arm_common/tests/test_job_metadata_suggestion.py services/backend/tests/test_identity_registry_online.py -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add packages/arm_common/arm_common/schemas/job_metadata.py packages/arm_common/arm_common/schemas/__init__.py packages/arm_common/tests/test_job_metadata_suggestion.py services/backend/arm_backend/identity/sources/registry.py services/backend/tests/test_identity_registry_online.py
git commit -m "feat(identity): typed identity_suggestion section and auto_apply_for"
```

---

### Task 2: Identify holds a hit when its switch is off

**Files:**
- Create: `services/backend/arm_backend/identity/apply.py`
- Modify: `services/backend/arm_backend/routers/ripper.py` (identify hit branch, lines ~776-806 on the base)
- Test: `services/backend/tests/test_identity_apply.py` (new)
- Test: `services/backend/tests/test_ripper_router.py`

**Interfaces:**
- Consumes: `auto_apply_for`, `IdentitySuggestion`, `without_identity_suggestion` (Task 1); `metadata_with_identity`, `extract_poster_url`, `external_ids_of` from `arm_backend.metadata`.
- Produces: `apply_identity_result(job, result, *, now) -> None` (the exact block identify runs today: title, year, media_type, poster, `metadata_with_identity`, music disc number); `suggest_identity(metadata_json, result, *, now) -> dict` (returns the bag with `identity_suggestion` set and `flags.unidentified = True`); `suggestion_to_result(s: IdentitySuggestion) -> MetadataResult`.

- [ ] **Step 1: Write the failing helper tests**

```python
# services/backend/tests/test_identity_apply.py
from datetime import datetime, timezone

from arm_backend.identity.apply import apply_identity_result, suggest_identity, suggestion_to_result
from arm_backend.metadata.base import MetadataResult
from arm_common import Job
from arm_common.enums import DiscType, JobStatus, MediaType
from arm_common.schemas.job_metadata import flag_is_set, identity_suggestion_of

_NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def _job() -> Job:
    return Job(id="job_1", drive_id="drv_x", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={"flags": {}})


def test_apply_identity_result_sets_the_job_fields_and_identity_section() -> None:
    job = _job()
    result = MetadataResult(
        title="Iron Man", year=2008, kind="movie", payload={"id": 1726, "poster_path": "/abc.jpg", "overview": "Tony."},
        provider="tmdb",
    )
    apply_identity_result(job, result, now=_NOW)
    assert (job.title, job.year, job.media_type) == ("Iron Man", 2008, MediaType.MOVIE)
    assert job.poster_url == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert job.metadata_json["identity"]["provider"] == "tmdb"
    assert job.metadata_json["identity"]["external_ids"]["tmdb"] == "1726"
    assert job.metadata_json["provider_raw"]["tmdb"]["id"] == 1726


def test_apply_identity_result_music_disc_number() -> None:
    job = _job()
    result = MetadataResult(title="Album", year=1999, kind="music", payload={"disc": 2}, provider="musicbrainz")
    apply_identity_result(job, result, now=_NOW)
    assert job.disc_number == 2
    job2 = _job()
    job2.disc_number = 1
    apply_identity_result(job2, result, now=_NOW)
    assert job2.disc_number == 1  # an existing disc number is kept
    job3 = _job()
    apply_identity_result(job3, MetadataResult(title="A", year=None, kind="music", payload={"disc": True}), now=_NOW)
    assert job3.disc_number is None  # a bool is not a disc number


def test_suggest_identity_stores_the_hit_and_flags_unidentified() -> None:
    result = MetadataResult(
        title="Iron Man", year=2008, kind="movie", payload={"id": 1726, "poster_path": "/abc.jpg", "overview": "Tony."},
        provider="tmdb",
    )
    md = suggest_identity({"scan_result": {"x": 1}}, result, now=_NOW)
    s = identity_suggestion_of(md)
    assert s is not None
    assert (s.provider, s.title, s.year, s.kind) == ("tmdb", "Iron Man", 2008, "movie")
    assert s.poster_url == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert s.external_ids.tmdb == "1726" and s.external_ids.tmdb_kind == "movie"
    assert s.overview == "Tony." and s.payload["id"] == 1726 and s.suggested_at == _NOW
    assert flag_is_set(md, "unidentified")
    assert md["scan_result"] == {"x": 1}
    assert "identity" not in md  # nothing applied


def test_suggestion_round_trips_to_a_result() -> None:
    result = MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 123, "name": "Lost"}, provider="tvmaze")
    s = identity_suggestion_of(suggest_identity(None, result, now=_NOW))
    assert s is not None
    back = suggestion_to_result(s)
    assert (back.title, back.year, back.kind, back.provider) == ("Lost", 2004, "tv", "tvmaze")
    assert back.payload == {"id": 123, "name": "Lost"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_identity_apply.py -q`
Expected: ModuleNotFoundError `arm_backend.identity.apply`.

- [ ] **Step 3: Create `identity/apply.py`**

```python
"""Applying, holding and re-applying a confident identify hit.

`apply_identity_result` is the one place a `MetadataResult` becomes the
job's identity (title, year, kind, poster, the typed `identity` section,
the music disc number). Identify calls it when the kind's auto-apply switch
is on; `POST /jobs/{id}/identity/accept` calls it when the operator confirms
a hit identify held (`suggest_identity`). Spec: identification-sources D-10.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from arm_backend.metadata import extract_poster_url, metadata_with_identity
from arm_backend.metadata.base import MetadataResult, _first_str, external_ids_of
from arm_common import Job
from arm_common.enums import MediaType
from arm_common.schemas.job_metadata import IdentitySuggestion, with_flags


def apply_identity_result(job: Job, result: MetadataResult, *, now: datetime) -> None:
    """Make `result` the job's identity (what identify did inline before PR 3)."""
    job.title = result.title
    job.year = result.year
    # G-03: keep the identified kind — it is the routing input.
    # result.kind is a subset of MediaType's values by construction.
    job.media_type = MediaType(result.kind)
    job.poster_url = extract_poster_url(result)
    # §3.4: identity + provider_raw, never a top-level payload merge.
    job.metadata_json = metadata_with_identity(job.metadata_json, result, identified_at=now)
    # A MusicBrainz medium position is this disc's number; the {disc}
    # naming token reads the column (G-14).
    if result.kind == "music" and job.disc_number is None:
        raw_disc = (result.payload or {}).get("disc")
        if isinstance(raw_disc, int) and not isinstance(raw_disc, bool):
            job.disc_number = raw_disc


def suggest_identity(metadata_json: dict[str, Any] | None, result: MetadataResult, *, now: datetime) -> dict[str, Any]:
    """Store `result` for the operator to confirm instead of applying it.

    The job stays unidentified (flag set: a rip started without confirming
    parks after the rip like any placeholder) and nothing from the hit
    reaches the job row or the `identity` section."""
    payload = result.payload or {}
    suggestion = IdentitySuggestion(
        provider=result.provider or "unknown",
        title=result.title,
        year=result.year,
        kind=result.kind,
        poster_url=extract_poster_url(result),
        external_ids=external_ids_of(result),
        overview=_first_str(payload.get("overview"), payload.get("Plot")),
        payload=dict(payload),
        suggested_at=now,
    )
    md = with_flags(metadata_json, unidentified=True)
    md["identity_suggestion"] = suggestion.model_dump(mode="json", exclude_none=True)
    return md


def suggestion_to_result(suggestion: IdentitySuggestion) -> MetadataResult:
    """The held hit as identify saw it, for `apply_identity_result`."""
    return MetadataResult(
        title=suggestion.title,
        year=suggestion.year,
        kind=suggestion.kind,
        payload=dict(suggestion.payload),
        provider=suggestion.provider,
    )
```

Check how `ripper.py` imports `extract_poster_url` and `metadata_with_identity` today (`from arm_backend.metadata import …` or `from arm_backend.metadata.base import …`) and use the same module so there is one definition. If `_first_str` being private bothers ruff/mypy, rename it `first_str` in `metadata/base.py` and update its two call sites.

- [ ] **Step 4: Run the helper tests**

Run: `uv run pytest services/backend/tests/test_identity_apply.py -q`
Expected: 4 passed.

- [ ] **Step 5: Write the failing identify tests**

Append to `services/backend/tests/test_ripper_router.py`. First extend `_config(...)` with `movie_auto_apply: bool = True, episode_auto_apply: bool = True, music_auto_apply: bool = True` and pass them to the `Config(...)` it builds (add the kwargs only; every existing call keeps its defaults).

```python
def test_identify_movie_hit_with_auto_apply_off_is_held_as_a_suggestion() -> None:
    """movie_auto_apply off + a confident movie hit -> the hit is stored, not
    applied; the disc parks in AWAITING_REVIEW with no countdown, keeps the
    miss title and the unidentified flag, persists its review tracks and
    emits rip.awaiting_review."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(movie_auto_apply=False)]
    db.rows["rip_presets"] = [_movie_preset()]
    result = MetadataResult(
        title="Iron Man", year=2008, kind="movie", payload={"id": 1726, "poster_path": "/abc.jpg"}, provider="tmdb"
    )
    hub = _Hub()
    app = _make_app(db, dispatcher=_Dispatcher(result), hub=hub)
    scan = _scan_dict()
    scan["titles"] = [{"index": 1, "duration_seconds": 4200}]
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": scan}, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "awaiting_review"
    assert out["wait_start_time"] is None
    assert out["title"] == "MY_DISC"  # the miss title, not the hit
    assert out["year"] is None and out["media_type"] is None and out["poster_url"] is None
    assert "identity" not in out["metadata_json"] or out["metadata_json"]["identity"] is None
    assert out["metadata_json"]["flags"]["unidentified"] is True
    s = out["metadata_json"]["identity_suggestion"]
    assert (s["provider"], s["title"], s["year"], s["kind"]) == ("tmdb", "Iron Man", 2008, "movie")
    assert s["poster_url"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert any(e["event_type"] == "rip.awaiting_review" for e in hub.events)
    tracks = [row for row in db.added if type(row).__name__ == "Track"]
    assert {t.source_ref for t in tracks} == {"1"}


def test_identify_hold_for_review_with_auto_apply_off_has_no_countdown() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True, movie_auto_apply=False)]
    db.rows["rip_presets"] = [_movie_preset()]
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={}, provider="tmdb")
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict()}, headers=_SERVICE_AUTH
        )
    out = r.json()
    assert out["status"] == "awaiting_review"
    assert out["wait_start_time"] is None
    assert out["metadata_json"]["identity_suggestion"]["title"] == "Iron Man"
    tracks = [row for row in db.added if type(row).__name__ == "Track"]
    assert len(tracks) == len(_scan_dict()["titles"])  # persisted once, not twice


def test_identify_tv_hit_follows_the_episode_switch() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(episode_auto_apply=False, movie_auto_apply=True)]
    db.rows["rip_presets"] = [_movie_preset()]
    result = MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 123}, provider="tvmaze")
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict()}, headers=_SERVICE_AUTH
        )
    out = r.json()
    assert out["status"] == "awaiting_review" and out["wait_start_time"] is None
    assert out["media_type"] is None
    assert out["metadata_json"]["identity_suggestion"]["kind"] == "tv"


def test_identify_music_hit_with_auto_apply_off_keeps_disc_number_unset() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(music_auto_apply=False)]
    db.rows["rip_presets"] = [_movie_preset()]
    result = MetadataResult(title="Album", year=1999, kind="music", payload={"disc": 2}, provider="musicbrainz")
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict("cd")}, headers=_SERVICE_AUTH
        )
    out = r.json()
    assert out["status"] == "awaiting_review"
    assert out["disc_number"] is None
    assert out["metadata_json"]["identity_suggestion"]["payload"]["disc"] == 2


def test_identify_switch_off_for_another_kind_still_applies_this_one() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(music_auto_apply=False, episode_auto_apply=False)]
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={}, provider="tmdb")
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict()}, headers=_SERVICE_AUTH
        )
    out = r.json()
    assert out["status"] == "identified" and out["title"] == "Iron Man"
    assert "identity_suggestion" not in out["metadata_json"] or out["metadata_json"]["identity_suggestion"] is None


def test_identify_previously_ripped_hold_still_wins_over_a_suggestion() -> None:
    """on_previously_ripped=hold + auto-apply off: one AWAITING_REVIEW hold
    carrying both the previously_ripped reason and the suggestion."""
    # Reuse the previously-ripped fixture shape from test_previously_ripped.py:
    # seed an earlier RIPPED job sharing the crc64 fingerprint, config with
    # on_previously_ripped=hold and movie_auto_apply=False, a movie hit.
    ...
```

For the last test, read `services/backend/tests/test_previously_ripped.py::test_hold_overrides_the_timed_review_and_a_missed_identify` and write the equivalent assertion: status `awaiting_review`, `wait_start_time is None`, `metadata_json["previously_ripped"]["job_id"]` set, and `metadata_json["identity_suggestion"]["title"]` set. Put it in `test_previously_ripped.py` next to that test if its fixtures live there.

Also check `_scan_dict("cd")` yields a CD scan (`disc_type="cd"`); if the CD path needs fingerprints or `cd_toc`, copy the shape from `test_identify_music_fills_music_section_and_disc_number`.

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_ripper_router.py -q -k "auto_apply or episode_switch or suggestion"`
Expected: the new tests fail on `status == "identified"` / missing section.

- [ ] **Step 7: Rewrite the identify hit branch**

In `routers/ripper.py`, compute the miss title before the `if result is not None:` branch (it is needed by both arms now), then replace the hit arm:

```python
        release_title = release_identity(thediscdb_match)[0] if thediscdb_match is not None else None
        # The cleaned hint titles are search inputs only: a miss (or a held
        # hit) is named by the disc's own BDMT name as written, else the
        # release, else the label.
        bdmt_name = (
            scan.bd_meta.name.strip() if scan.bd_meta is not None and any(h.id == "bd_title" for h in hints) else ""
        )
        miss_title = bdmt_name or release_title or scan.volume_label

        if result is not None and auto_apply_for(cfg, result.kind):
            apply_identity_result(job, result, now=datetime.now(timezone.utc))
            # Timed review gate: … (keep the existing comment)
            if cfg.hold_for_review:
                job.status = JobStatus.AWAITING_REVIEW
                job.wait_start_time = datetime.now(timezone.utc)
                await _persist_review_tracks(session, job, scan)
            else:
                job.status = JobStatus.IDENTIFIED
        elif result is not None:
            # D-10: this kind's "Apply confident matches" switch is off. Keep
            # the hit for the operator to confirm; the disc waits with no
            # countdown (the ripper treats a null wait_start_time as "no
            # countdown") and stays unidentified until they accept or
            # resolve it. The review gate's own countdown never starts here.
            job.title = miss_title
            job.metadata_json = suggest_identity(job.metadata_json, result, now=datetime.now(timezone.utc))
            job.status = JobStatus.AWAITING_REVIEW
            job.wait_start_time = None
            await _persist_review_tracks(session, job, scan)
            logger.info(
                "identify job_id=%s: %s hit %r held for confirmation (auto-apply off)", job.id, result.kind, result.title
            )
        else:
            diagnostic: dict[str, bool] = {}
            if timed_out:
                diagnostic["dispatch_timeout"] = True
            if cfg.block_on_miss:
                … (unchanged miss arm, minus the lines that moved up)
```

Import `auto_apply_for` from the registry module (next to the other registry imports) and `apply_identity_result, suggest_identity` from `arm_backend.identity.apply`. Remove the now-duplicated inline apply block. The `previous is not None` block after the branch is unchanged: it already skips `_persist_review_tracks` when the status is already `AWAITING_REVIEW` and sets `wait_start_time = None`.

- [ ] **Step 8: Run the ripper router suite**

Run: `uv run pytest services/backend/tests/test_ripper_router.py services/backend/tests/test_previously_ripped.py services/backend/tests/test_identity_apply.py -q`
Expected: all pass, including every pre-existing identify test (they run with the switches at their default `True`).

- [ ] **Step 9: Commit**

```bash
git add services/backend/arm_backend/identity/apply.py services/backend/arm_backend/routers/ripper.py services/backend/tests/test_identity_apply.py services/backend/tests/test_ripper_router.py services/backend/tests/test_previously_ripped.py
git commit -m "feat(identify): hold a confident hit as a suggestion when its auto-apply switch is off"
```

---

### Task 3: A suggestion hold has no countdown anywhere

**Files:**
- Modify: `services/backend/arm_backend/routers/config.py` (un-pause loop, ~line 286)
- Modify: `services/backend/arm_backend/routers/jobs.py` (`review_pause`, ~line 649)
- Modify: `services/backend/arm_backend/routers/ripper.py` (`get_held_job`, ~line 1192)
- Test: `services/backend/tests/test_config_router.py`, `services/backend/tests/test_jobs_router.py`, `services/backend/tests/test_ripper_router.py`

**Interfaces:**
- Consumes: `identity_suggestion_of` (Task 1).

- [ ] **Step 1: Write the three failing tests**

In `test_config_router.py`, find the existing un-pause test that asserts previously-ripped holds keep `wait_start_time = None` (search `unpaus` / `previously_ripped` in that file; if none exists, model the new test on the test that asserts un-pausing stamps `wait_start_time` on held jobs) and add:

```python
def test_unpausing_does_not_start_a_countdown_on_a_suggestion_hold(signing_key: bytes) -> None:
    # Config row with ripping_paused=True; one AWAITING_REVIEW job whose
    # metadata_json = {"identity_suggestion": {... valid section ...}, "flags": {"unidentified": True}}
    # and wait_start_time=None; one plain AWAITING_REVIEW job with wait_start_time=None.
    # PATCH /api/config {"ripping_paused": false}
    # assert the suggestion job's wait_start_time is still None
    # assert the plain job's wait_start_time is now set
```

Fill in with the file's own `_make_app` / seeding helpers; the valid section can be the dict from Task 1's `_suggestion()` (copy it; tests do not import from other test modules).

In `test_jobs_router.py`, next to `test_review_pause_sets_manual_pause`:

```python
def test_review_pause_409_on_a_suggestion_hold(signing_key: bytes) -> None:
    db = FakeSession()
    job = _job(status=JobStatus.AWAITING_REVIEW)
    job.metadata_json = {"identity_suggestion": _SUGGESTION, "flags": {"unidentified": True}}
    db.rows["jobs"] = [job]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/review-pause?paused=true", headers=_auth(token))
    assert r.status_code == 409
    assert "confirm its identity" in r.json()["detail"]
    assert job.manual_pause is False
```

(Define `_SUGGESTION` as a module-level dict in `test_jobs_router.py`; Task 4 reuses it. Match `_job(...)`'s real signature.)

In `test_ripper_router.py`, next to `test_held_job_paused_flag_from_per_job_manual_pause`:

```python
def test_held_job_paused_flag_from_a_suggestion_hold() -> None:
    # Same shape as the per-job manual_pause test, but manual_pause=False,
    # ripping_paused=False and metadata_json carrying a valid identity_suggestion.
    # assert body["paused"] is True
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_config_router.py services/backend/tests/test_jobs_router.py services/backend/tests/test_ripper_router.py -q -k suggestion`
Expected: 3 failures (countdown stamped; 200 instead of 409; `paused` False).

- [ ] **Step 3: Teach the three sites**

`config.py` un-pause loop:

```python
        for job in held:
            # A previously-ripped hold and a held suggestion have no countdown to restart.
            if previously_ripped_job_id(job.metadata_json) is not None or identity_suggestion_of(job.metadata_json) is not None:
                continue
```

`jobs.py` `review_pause`, after the previously-ripped 409:

```python
    if identity_suggestion_of(job.metadata_json) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this disc is waiting for you to confirm its identity; it has no countdown to pause",
        )
```

`ripper.py` `get_held_job`:

```python
    # A previously-ripped hold or a held suggestion waits for the operator however it got there.
    paused = (
        global_paused
        or bool(rows[0].manual_pause)
        or previously_ripped_job_id(rows[0].metadata_json) is not None
        or identity_suggestion_of(rows[0].metadata_json) is not None
    )
```

Import `identity_suggestion_of` from `arm_common.schemas.job_metadata` in each file.

- [ ] **Step 4: Run the three suites**

Run: `uv run pytest services/backend/tests/test_config_router.py services/backend/tests/test_jobs_router.py services/backend/tests/test_ripper_router.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/routers/config.py services/backend/arm_backend/routers/jobs.py services/backend/arm_backend/routers/ripper.py services/backend/tests/test_config_router.py services/backend/tests/test_jobs_router.py services/backend/tests/test_ripper_router.py
git commit -m "feat(review): a held identity suggestion has no countdown to start, pause or lose on restart"
```

---

### Task 4: Accept endpoint; resolve clears the suggestion

**Files:**
- Modify: `services/backend/arm_backend/routers/jobs.py` (extract `resolve_identity`; add `accept_identity_suggestion`)
- Modify: `packages/arm_common/arm_common/enums.py` only if a comment needs it (no new statuses)
- Test: `services/backend/tests/test_jobs_router.py`

**Interfaces:**
- Consumes: `apply_identity_result`, `suggestion_to_result` (Task 2); `identity_suggestion_of`, `without_identity_suggestion` (Task 1); `external_ids_of`.
- Produces: `resolve_identity(session, job, req, *, hub, stage_runner, before_identity=None) -> ResolveResponse`; route `POST /api/jobs/{job_id}/identity/accept`.

- [ ] **Step 1: Extract `resolve_identity` (no behaviour change)**

In `routers/jobs.py`, move the body of `resolve` from `before_identity = _identity_snapshot(job)` through the `return ResolveResponse(...)` into:

```python
async def resolve_identity(
    session: AsyncSession,
    job: Job,
    req: ResolveRequest,
    *,
    hub: WSHub,
    stage_runner: EpisodeStageRunner | None,
    before_identity: tuple[int | None, int | None, MediaType | None, str | None, dict[str, Any]] | None = None,
) -> ResolveResponse:
    """The resolve route's body, shared with the suggestion accept route.

    `before_identity` lets a caller that already changed the job's identity
    (accept) still get the episode stage scheduled: the snapshot is taken
    here only when the caller passes none."""
    if before_identity is None:
        before_identity = _identity_snapshot(job)
    … (the moved body, verbatim, with `job_id` references replaced by `job.id`)
```

and have the route do its fetch, 404, status 409, then `return await resolve_identity(session, job, req, hub=hub, stage_runner=stage_runner)`. Where the moved body builds `new_metadata` (the dict it assigns to `job.metadata_json`), add `new_metadata.pop("identity_suggestion", None)` beside the existing `new_metadata.pop("unidentified", None)` with the comment `# A resolve by any route is the operator identifying the disc: a held suggestion is moot.`

Run: `uv run pytest services/backend/tests/test_jobs_router.py services/backend/tests/test_resolve_fanout.py -q`
Expected: all pass (pure extraction).

- [ ] **Step 2: Write the failing accept tests**

Append to `test_jobs_router.py` (using `_SUGGESTION` from Task 3 and the file's helpers; the `_make_app` there takes a hub, and a `_StageRunner` fake exists at line ~72):

```python
def _suggested_job(status: JobStatus = JobStatus.AWAITING_REVIEW) -> Job:
    job = _job(status=status)
    job.title = "MY_DISC"
    job.year = None
    job.media_type = None
    job.wait_start_time = None
    job.metadata_json = {"identity_suggestion": dict(_SUGGESTION), "flags": {"unidentified": True}}
    return job


def test_accept_applies_the_suggestion_and_releases_the_rip_when_the_gate_is_off(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job()
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1, hold_for_review=False, ripping_paused=False)]
    hub = _Hub()
    app, token = _make_app(signing_key, db, hub=hub)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()["job"]
    assert body["status"] == "identified"
    assert (body["title"], body["year"], body["media_type"]) == ("Iron Man", 2008, "movie")
    assert body["poster_url"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert body["metadata_json"]["identity"]["provider"] == "tmdb"
    assert body["metadata_json"]["identity"]["external_ids"]["imdb"] == "tt0371746"
    assert body["metadata_json"]["provider_raw"]["tmdb"]["id"] == 1726
    assert body["metadata_json"].get("identity_suggestion") is None
    assert body["metadata_json"]["flags"].get("unidentified", False) is False
    assert any(e["event_type"] == "identify.resolved" for e in hub.events)


def test_accept_with_the_review_gate_on_keeps_the_hold_and_starts_the_countdown(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job()
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1, hold_for_review=True, ripping_paused=False)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    body = r.json()["job"]
    assert body["status"] == "awaiting_review"
    assert body["wait_start_time"] is not None
    assert body["title"] == "Iron Man"


def test_accept_while_ripping_is_paused_stays_held_with_no_countdown(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job()
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1, hold_for_review=False, ripping_paused=True)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    body = r.json()["job"]
    assert body["status"] == "awaiting_review"
    assert body["wait_start_time"] is None
    assert body["metadata_json"].get("identity_suggestion") is None


def test_accept_on_a_ripped_placeholder_promotes_to_ripped(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job(JobStatus.RIPPED_AWAITING_IDENTIFY)
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["job"]["status"] == "ripped"
    assert r.json()["job"]["title"] == "Iron Man"


def test_accept_music_suggestion_sets_the_disc_number(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job()
    job.metadata_json["identity_suggestion"].update(
        {"provider": "musicbrainz", "kind": "music", "title": "Album", "year": 1999, "payload": {"disc": 2}}
    )
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert r.json()["job"]["disc_number"] == 2


def test_accept_409_without_a_suggestion(signing_key: bytes) -> None:
    db = FakeSession()
    job = _job(status=JobStatus.AWAITING_REVIEW)
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert r.status_code == 409
    assert "no identity suggestion" in r.json()["detail"]


def test_accept_409_in_a_non_resolvable_status(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job(JobStatus.RIPPING)
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert r.status_code == 409
    assert job.title == "MY_DISC"


def test_accept_404(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_missing/identity/accept", headers=_auth(token))
    assert r.status_code == 404


def test_accept_requires_a_writer(signing_key: bytes) -> None:
    # Mirror the file's existing viewer-403 pattern for a writer-only route.
    ...


def test_accept_schedules_the_episode_stage_for_a_tv_suggestion(signing_key: bytes) -> None:
    # TV suggestion (kind "tv", provider "tvmaze"); app built with the file's
    # _StageRunner fake; assert the runner was asked to schedule job.id.
    ...


def test_resolve_clears_a_held_suggestion(signing_key: bytes) -> None:
    db = FakeSession()
    job = _suggested_job()
    db.rows["jobs"] = [job]
    db.rows["config"] = [Config(id=1)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/resolve", json={"title": "Something Else", "year": 2001}, headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["job"]["metadata_json"].get("identity_suggestion") is None
        assert r.json()["job"]["metadata_json"]["flags"].get("unidentified", False) is False
        again = client.post(f"/api/jobs/{job.id}/identity/accept", headers=_auth(token))
    assert again.status_code == 409
```

If the `Config` row in this file is seeded through a helper, use it. Check what `JobView.metadata_json` serialises for an absent `identity_suggestion` (pydantic will emit `null`); the assertions above accept both.

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_jobs_router.py -q -k "accept or resolve_clears"`
Expected: 404s on the accept route; the resolve test fails on the lingering section.

- [ ] **Step 4: Add the route**

In `routers/jobs.py`, after `resolve`:

```python
@router.post("/{job_id}/identity/accept", response_model=ResolveResponse)
async def accept_identity_suggestion(
    job_id: JobIdParam,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(_get_stage_runner),
) -> ResolveResponse:
    """Confirm the confident match identify held because the media type's
    auto-apply switch was off (identification-sources spec D-10).

    Applies the stored hit exactly as identify would have, then hands the
    job to the resolve path (provenance, fan-out, `identify.resolved`, the
    episode stage). The status is settled first: a held disc is released to
    rip when the review gate is off, or gets the gate's countdown when it is
    on; a pause keeps it held with no countdown until un-pause stamps one;
    a ripped placeholder follows resolve's promote rule.
    """
    job = (await session.execute(select(Job).where(col(Job.id) == job_id).with_for_update())).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    suggestion = identity_suggestion_of(job.metadata_json)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"job {job_id} has no identity suggestion to accept")
    if job.status not in RESOLVABLE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is in status {job.status.value}, not in an identify-resolvable status",
        )
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    before_identity = _identity_snapshot(job)
    now = datetime.now(timezone.utc)
    result = suggestion_to_result(suggestion)
    job.metadata_json = without_identity_suggestion(job.metadata_json)
    apply_identity_result(job, result, now=now)
    if job.status == JobStatus.AWAITING_REVIEW:
        paused = cfg is not None and bool(cfg.ripping_paused)
        if cfg is not None and cfg.hold_for_review:
            job.wait_start_time = None if paused else now
        elif paused:
            job.wait_start_time = None
        else:
            job.status = JobStatus.IDENTIFIED
    req = ResolveRequest(
        title=result.title, year=result.year, media_type=MediaType(result.kind), external_ids=external_ids_of(result)
    )
    logger.info("accept job_id=%s: %s suggestion %r applied -> %s", job.id, result.kind, result.title, job.status.value)
    return await resolve_identity(session, job, req, hub=hub, stage_runner=stage_runner, before_identity=before_identity)
```

Imports: `apply_identity_result`, `suggestion_to_result` from `arm_backend.identity.apply`; `identity_suggestion_of`, `without_identity_suggestion` from `arm_common.schemas.job_metadata`; `external_ids_of` from `arm_backend.metadata.base`; `Config`, `CONFIG_SINGLETON_ID` as the other routers import them. Check how `jobs.py` already reads the config singleton and reuse that helper if one exists.

- [ ] **Step 5: Run the jobs suites**

Run: `uv run pytest services/backend/tests/test_jobs_router.py services/backend/tests/test_resolve_fanout.py -q`
Expected: all pass.

- [ ] **Step 6: Regenerate the wire contract**

```bash
bash devtools/regen-openapi-snapshot.sh
bash services/ui-neu/scripts/codegen.sh
git status --short services/ui-neu
```

Expected: the snapshot and `api.gen.ts` change (new route, `identity_suggestion` on `JobMetadata`). `cd services/ui-neu/frontend && npm run check` passes.

- [ ] **Step 7: Commit**

```bash
git add services/backend/arm_backend/routers/jobs.py services/backend/tests/test_jobs_router.py services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts
git commit -m "feat(jobs): POST /identity/accept applies a held suggestion; resolve clears it"
```

---

### Task 5: The two toggles join the config surface

**Files:**
- Modify: `packages/arm_common/arm_common/config_metadata.py`
- Modify: `packages/arm_common/arm_common/schemas/auth.py` (`ConfigUpdateRequest`)
- Modify: `services/backend/arm_backend/routers/config.py` (PATCH bool rule)
- Modify: `services/ui-neu/frontend/src/lib/utils/settings-sections.ts`
- Test: `packages/arm_common/tests/test_config_hidden_fields.py`, `packages/arm_common/tests/test_config_metadata.py`, `services/backend/tests/test_config_identification_settings.py`, `services/ui-neu/frontend/src/lib/utils/__tests__/settings-sections.test.ts`
- Regenerate: `services/ui-neu/openapi.snapshot.json`, `services/ui-neu/frontend/src/lib/types/api.gen.ts`

- [ ] **Step 1: Flip the tests**

`test_config_hidden_fields.py`: `_HIDDEN = {"default_retention_policy", "notification_apprise_urls"}`.

`test_config_metadata.py`: replace the two `not in by_key` lines with

```python
    for key, label in (("movie_auto_apply", "Apply confident movie matches"), ("music_auto_apply", "Apply confident music matches")):
        meta = by_key[key]
        assert (meta.type, meta.group, meta.editable, meta.setup_step) == ("bool", "Metadata", True, "metadata")
        assert meta.label == label
        assert "Review first" in meta.help
    assert "Review first" in by_key["episode_auto_apply"].help
```

`test_config_identification_settings.py`: in `test_patch_ranked_lists_and_toggles` (or a new test beside it) PATCH `{"movie_auto_apply": false, "music_auto_apply": false}` and assert both read back `False`; add a test that PATCH `{"movie_auto_apply": null}` is 400 with detail `movie_auto_apply must be true or false`, and the same for `music_auto_apply`.

`settings-sections.test.ts`: add a case that, given metas for `movie_sources`, `music_sources`, `movie_auto_apply`, `music_auto_apply`, the "Movies and music" section's columns are `[['movie_sources', 'movie_auto_apply'], ['music_sources', 'music_auto_apply']]` and `fields` is empty.

Run: `uv run pytest packages/arm_common/tests/test_config_hidden_fields.py packages/arm_common/tests/test_config_metadata.py services/backend/tests/test_config_identification_settings.py -q` and `cd services/ui-neu/frontend && npx vitest run src/lib/utils/__tests__/settings-sections.test.ts`
Expected: failures on the missing entries / fields / layout.

- [ ] **Step 2: Add the entries, fields and validation**

`config_metadata.py`: insert after the `movie_sources` entry

```python
    ConfigFieldMeta(
        key="movie_auto_apply",
        group="Metadata",
        tier="operator",
        setup_step="metadata",
        label="Apply confident movie matches",
        help=(
            "When off, a movie match waits on the job page for you to confirm it and the disc is held with no "
            "countdown. Ripping › Review first still holds every disc."
        ),
        type="bool",
        editable=True,
    ),
```

and after `music_sources` the `music_auto_apply` twin (label `Apply confident music matches`, help `When off, an audio CD match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.`). Copy `setup_step` from whatever `movie_sources` carries (if it carries none, carry none). Update `episode_auto_apply`'s help to the Global Constraints text.

`auth.py` `ConfigUpdateRequest`: add `movie_auto_apply: bool | None = None` and `music_auto_apply: bool | None = None` after `search_provider_music`.

`config.py` PATCH: replace the single `episode_auto_apply` None check with

```python
    for key in ("episode_auto_apply", "movie_auto_apply", "music_auto_apply"):
        if key in fields and fields[key] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be true or false")
```

`settings-sections.ts` "Movies and music":

```ts
			keys: ['movie_sources', 'music_sources', 'movie_auto_apply', 'music_auto_apply'],
			columns: [
				['movie_sources', 'movie_auto_apply'],
				['music_sources', 'music_auto_apply']
			]
```

- [ ] **Step 3: Regenerate and run everything touched**

```bash
bash devtools/regen-openapi-snapshot.sh
bash services/ui-neu/scripts/codegen.sh
uv run pytest packages/arm_common services/backend/tests/test_config_identification_settings.py services/backend/tests/test_config_router.py -q
cd services/ui-neu/frontend && npm run check && npx vitest run
```

Expected: all green; `api.gen.ts` now types the two update fields.

- [ ] **Step 4: Commit**

```bash
git add packages/arm_common/arm_common/config_metadata.py packages/arm_common/arm_common/schemas/auth.py services/backend/arm_backend/routers/config.py services/ui-neu/frontend/src/lib/utils/settings-sections.ts packages/arm_common/tests services/backend/tests/test_config_identification_settings.py services/ui-neu/frontend/src/lib/utils/__tests__/settings-sections.test.ts services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts
git commit -m "feat(config): movie_auto_apply and music_auto_apply are editable"
```

---

### Task 6: Spec and docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.4 note, §6 item 4, §10)
- Modify: `docs/developers/architecture/02-job-lifecycle.md`

- [ ] **Step 1: Spec**

§5.4: change the "hidden from the editable surface until PR 3 reads them" sentence to say PR 3 reads them and exposes them. §6 item 4 becomes: `4. **PR 3 · Auto-apply hold path.** `auto_apply_for(cfg, kind)` (movie / episode / music switch); a hit whose switch is off is stored as `metadata_json.identity_suggestion`, the job keeps the miss title and the `unidentified` flag and parks in `awaiting_review` with no countdown; `POST /jobs/{id}/identity/accept` applies it through the resolve path (gate off → rip released; gate on → countdown); any resolve clears it. The two toggles become editable.` §10: add `- Resolved in PR 3: TV title hits follow `episode_auto_apply` (one switch per media type, D-8); the TheDiscDB release-metadata identity goes through the same gate; accept while ripping is paused keeps the disc held until un-pause stamps a countdown. The review card's suggestion display and Accept button are the UI redesign PR's.`

- [ ] **Step 2: Lifecycle doc**

Next to the previously-ripped `hold` paragraph (line ~53), add a bullet describing the suggestion hold: when it happens, what the job row looks like (miss title, `flags.unidentified`, `identity_suggestion`, `awaiting_review`, no `wait_start_time`), the three ways out (accept → identity applied, rip released or countdown per the review gate; resolve → suggestion cleared, held disc waits for Start; Start without either → placeholder rip that parks at `ripped_awaiting_identify` where accept still works), and that un-pause, review-pause and the ripper's held-job probe treat it like the previously-ripped hold.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-identification-sources-design.md docs/developers/architecture/02-job-lifecycle.md
git commit -m "docs(identity): auto-apply hold path in the spec and the job lifecycle"
```

---

## Self-review notes

- **Spec coverage.** D-10 precedence: Task 2 (gate on + switch on unchanged; switch off never starts the countdown) and Task 4 (accept honours the gate). #258 PR 3 bullet: suggestion stored (Task 2), `awaiting_review` with null `wait_start_time` (Task 2), ripper untouched (null already means no countdown), binary (no scoring anywhere). §5.4 un-hide: Task 5. D-8's three switches: Task 1.
- **Why a typed section rather than a `SourceClaims` entry.** `JobClaim.title` is a search hint the resolver never applies, and online sources are not resolver `Source`s (no tier), so a claim could carry neither the identity nor a path to apply it. The typed section carries the full hit and `accept` re-applies it through the one function identify uses.
- **Why accept goes through `resolve_identity`.** Provenance, `identify.resolved` for the parked ripper, fan-out, the stage trigger and the placeholder promote rule all live there; duplicating them is how the first resolve bugs (Fix 75-x) happened.
- **Type consistency.** `apply_identity_result(job, result, *, now)` (Tasks 2, 4); `suggest_identity(metadata_json, result, *, now) -> dict` (Task 2); `suggestion_to_result(s)` (Tasks 2, 4); `identity_suggestion_of` / `without_identity_suggestion` (Tasks 1, 3, 4); `auto_apply_for(cfg, kind)` (Tasks 1, 2); `resolve_identity(session, job, req, *, hub, stage_runner, before_identity=None)` (Task 4).
- **Review Focus.** 1 → Task 2 music hold test + Task 4 music accept test. 2 → Task 3 config test. 3 → Task 3 held-job test. 4 → Task 4 `test_resolve_clears_a_held_suggestion`. 5 → Task 4 paused test.
- **Known interplay left for the UI PR.** Until the review card shows the suggestion, a held disc looks like an unidentified hold with a Start button; the stack merges together, so no release sees that state.
