# ARM v3 — Master Implementation Plan

This plan sequences the work required to turn the walking skeleton into a v3.0 release that can pass the [cutover readiness criteria](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover). It is a living document: phases may reorder if dependencies surface, and PR-sized milestones will be broken out into separate planning docs as they're picked up.

Architecture it implements: [v3/docs/arch/](../arch/). Every line below is a "how do we build what those docs describe" — not a re-specification.

## How to read this document

- **Phases** are serial on the critical path. Phase N+1 depends on state shipped in Phase N.
- **Tracks** run in parallel to the critical path once their entry condition is met (usually "phase X has shipped").
- Each phase lists: **goal**, **exit criteria** (what's demonstrably working), **deliverables** (roughly PR-sized chunks), and **depends on**.
- Subsystems are listed in the order they come online. The first concrete end-to-end win is a disc → `/raw/` rip (Phase 3). The first user-visible UI win is Phase 5. The first full rip→transcode→`/media` flow is Phase 7.

## Guiding principles

Pulled straight from [00-vision.md](../arch/00-vision.md) — repeated here because they drive ordering:

1. **Bits first, metadata second, transcode third.** Get raw files on disk before worrying about Apprise, GPU probing, or UI polish.
2. **Every phase ships a demoable slice.** No "foundation-only" phases — if a phase can't be demonstrated end-to-end, it's split.
3. **v2 stays untouched.** Every deliverable is strictly additive under `v3/`. See [08-v2-isolation-and-cutover.md](../arch/08-v2-isolation-and-cutover.md).
4. **Schemas before endpoints.** Every wire contract lands first in [packages/arm_common/](../../packages/arm_common/) Pydantic; producers and consumers import the same types.

---

## Phase 0 — Walking skeleton (shipped)

Captured here so later phases can reference what's already running.

**Delivered** (commits `f697df22` → `8beb8bfa`):
- Postgres 18 with TLS, internal CA, service token, PUID/PGID entrypoint ([services/_common/docker-entrypoint.sh](../../services/_common/docker-entrypoint.sh) — to verify on disk).
- Backend boots, runs Alembic `0001_initial` + `0002_disc_fingerprint`, serves `/api/health`, `/api/ripper/register`, `/api/ripper/identify`.
- One ripper container polls `ioctl(CDROM_DRIVE_STATUS)` on `/dev/sr0`, registers with Backend, posts `identify` on disc insert → creates a `Job` row in `status='created'`.
- [packages/arm_common/](../../packages/arm_common/) has enums (`DriveStatus`, `JobStatus`, `DiscType`), ULID helper, and the two ripper request schemas (`RegisterRequest`, `IdentifyRequest`). Phase 0 also shipped skinny `RegisterResponse`/`IdentifyResponse` stubs; Phase 1 replaces them with the full `Drive`/`Job` row models.

**Not delivered:** every other table, real disc identification, MakeMKV invocation, WebSocket hub, UI, transcode, auth, notifications, installer, supply-chain hygiene. Roughly **5%** of the target architecture.

---

## Phase 1 — Data model completion (shipped)

**Delivered** (commits `aa531dee` → `fd2c539a`):

1. SQLModel adoption — `Drive`/`Job` (and every other entity) are SQLModel classes, doubling as wire schemas. The `/api/ripper/register` and `/api/ripper/identify` routes return the row models directly; the skinny `RegisterResponse`/`IdentifyResponse` stubs from Phase 0 are gone.
2. `users`, `config`, `events` tables present.
3. `tracks`, `rip_presets`, `transcode_presets`, `sessions`, `session_applications`, `transcode_tasks`, `gpus` tables present.
4. Status/mode columns are `VARCHAR`. No native Postgres enum types, no CHECK constraints. A `_StrEnumString` SQLAlchemy `TypeDecorator` ([packages/arm_common/arm_common/models/_columns.py](../../packages/arm_common/arm_common/models/_columns.py)) round-trips `str ↔ StrEnum` at the SQL boundary so loaded rows present typed enums to Pydantic.
5. Partial unique index `uq_transcode_tasks_output_path_live` on `transcode_tasks(output_path) WHERE status IN ('queued','in_progress','done')`.
6. First-boot seeders ([services/backend/arm_backend/seeders.py](../../services/backend/arm_backend/seeders.py)): admin user with a random `secrets.token_urlsafe(18)` password (argon2id, logged once with a banner), `config` singleton with HS256 signing key, 7 built-in rip presets, 8 built-in transcode presets, 8 built-in sessions. Idempotent — re-running on a populated DB is a no-op.

Realignment landed alongside the data model:

- SQLModel classes live in [packages/arm_common/arm_common/models/](../../packages/arm_common/arm_common/models/) per [04-data-model.md § Schema definition and migrations](../arch/04-data-model.md#schema-definition-and-migrations) — moved out of `arm_backend` so future ripper/transcode services can reuse them without depending on the backend package.
- All 0001/0002/0003 migrations from the Phase 0 walking skeleton were collapsed into a single consolidated [0001_initial](../../services/backend/migrations/versions/0001_initial.py); no production DB to migrate.

**Verified end-to-end on a fresh DB.** Alembic upgrade clean, banner logged, `\dt` shows 13 tables, seed counts match (users=1, config=1, rip_presets=7, transcode_presets=8, sessions=8), backend restart is idempotent.

---

## Phase 2 — Real disc identification (shipped)

**Delivered** on `wolfy/v3-improvments`:

1. Typed `ScanResult` / `ScanTitle` in [packages/arm_common/arm_common/schemas/ripper.py](../../packages/arm_common/arm_common/schemas/ripper.py); `IdentifyRequest.scan_result` is no longer an opaque dict.
2. New `arm_backend/metadata/` package with `TMDBClient` (v4 bearer auth so the key never leaks via query string), `OMDBClient` (movie fallback), `MusicBrainzClient` (1 req/s rate limit + required user-agent), and a `MetadataDispatcher` that owns one shared `httpx.AsyncClient` with the merged trust store. Routing: DVD/BD → TMDB movie → TMDB TV → OMDB movie; CD → MusicBrainz only; DATA/UNKNOWN → short-circuit miss.
3. Backend `/api/ripper/identify` handler runs the lookup, persists `title`/`year`/`metadata_json`, and lands the job at `identified` (hit) or `awaiting_user_id` (miss with `config.block_on_miss=true`) or `identified` with `metadata_json={"unidentified": true}` (miss with `block_on_miss=false`, placeholder mode for Phase 10). Per-provider 8s + overall 25s `asyncio.wait_for` budget; provider 5xx logs and falls through, never failing the request.
4. Ripper-side `JobController` ([services/ripper/arm_ripper/job_controller.py](../../services/ripper/arm_ripper/job_controller.py)) holds per-job state. On `AWAITING_USER_ID` it polls `GET /api/ripper/jobs/{job_id}` (5s → 30s exponential backoff) until the UI/curl resolves it. Backend retries with backoff on transport errors. Replaced by WS in Phase 4.
5. UI-side `POST /api/jobs/{job_id}/resolve` ungated (dev-only; carries a `# Phase 5: gate behind require_jwt` marker pending JWT in Phase 5).
6. Ripper Dockerfile multistage build that ports v2's signed-tarball MakeMKV install and runtime `update_key.sh` (env `MAKEMKV_PERMA_KEY` or scraped monthly beta) wired into the shared entrypoint. `libdvd-pkg` reconfigured non-interactively at image build time; `abcde`/`flac`/`cdparanoia` for CDs; `python-discid` for MusicBrainz disc-id computation.
7. Tests: 16 backend tests (metadata clients via `respx`, dispatcher routing rules) + 7 ripper tests (`makemkvcon` parser fixtures, JobController behaviour with a fake backend) — all passing under `uv run pytest`.

`disc_fingerprint` / `aacs_disc_id` columns remain null per [04-data-model.md](../arch/04-data-model.md). Live DB integration tests for `/identify` and `/resolve` deferred to a future phase that brings up testcontainers; manual verification via real DVD documented in [v3/docs/ops/makemkv.md](../ops/makemkv.md).

**Depends on:** Phase 1.

---

## Phase 3 — Rip pipeline (MVP end-to-end, shipped)

**Delivered** on `wolfy/v3-improvments`:

1. Typed `TrackUpdateRequest` / `JobCompleteRequest` / `RipStartResponse` / `TrackView` in [packages/arm_common/arm_common/schemas/](../../packages/arm_common/arm_common/schemas/).
2. New `arm_backend/track_selection.py` applies `rip_presets.track_selection` rules — `main_feature` (longest title ≥ 45 min, fallback to longest), `all_tracks` (≥ 60 s), `archive` (every title), `custom` raises `NotImplementedError` (Phase 6). DVD/BD → `VIDEO_TITLE` rows with `source_ref = title.index`; CD → `AUDIO_TRACK` rows from libdiscid track list; DATA → single `DATA_DUMP`.
3. Three new backend endpoints under `/api/ripper/`:
   - `POST /jobs/{job_id}/rip-start` — hardcoded preset by `disc_type` (DVD/BD → `rpr_builtin_movie_archive`, CD → `rpr_builtin_music_standard`, DATA → `rpr_builtin_data_copy`); reads `metadata_json["scan_result"]`; selects tracks; transitions `IDENTIFIED → RIPPING`. Idempotent.
   - `PATCH /tracks/{track_id}` — validates legal `queued → in_progress → done|failed` transitions; writes `output_path`/`size_bytes`/`sha256`/`duration_seconds`/`last_error`.
   - `POST /jobs/{job_id}/rip-complete` — aggregates track outcomes into `RIPPED` / `RIPPED_PARTIAL` / `FAILED`.
4. Drive-scoping via `X-ARM-Hostname` header. New `require_drive_owner_by_job` / `require_drive_owner_by_track` deps load the row's drive and 403 on mismatch ([05-cross-cutting.md § Authorization rules](../arch/05-cross-cutting.md#authorization-rules)). `register` and `identify` stay bearer-only (no `drive_id` available at call time). Per-drive defaults in `Drive.default_session_id` arrive in Phase 8.
5. Identify handler now persists `scan_result` into `metadata_json["scan_result"]` so rip-start can re-derive the title list without requiring the ripper to re-send it.
6. Ripper rip stack at [services/ripper/arm_ripper/rip/](../../services/ripper/arm_ripper/rip/):
   - `makemkv_rip.rip_disc` shells `makemkvcon mkv ... all <outdir> --minlength=N` exactly once per disc (Phase 15.5 reverted from per-title invocations — see § Phase 15.5 below), streams PRGV/PRGT/MSG records, attributes per-title outcomes from `MSG:5018`/`MSG:5003` + post-exit output-dir walk, captures `title_tNN.mkv` size + SHA-256 per surviving title.
   - `abcde_rip.rip_cd` rips a whole audio CD via `abcde -o wav -a read,move -n -N` with a generated config that pins `OUTPUTFORMAT=track_${TRACKNUM}` (no encoding, no CDDB); maps output WAVs back to per-track `RipResult`s.
   - `data_rip.rip_data` `dd`s a raw image to `/raw/<job>/dump.iso`.
   - `dispatcher.rip_all` routes per `disc_type`, invoking on_track_start / on_track_done / on_track_progress callbacks the orchestrator uses to drive the wire-side state machine.
7. `JobController._run_rip` orchestrates: rip-start (with retry-on-503), per-track PATCH-with-retry on transitions, rip-complete (with retry), `eject`, then a 3 s grace before returning so the poll loop's `DRIVE_NOT_READY` flicker doesn't re-trigger.
8. CD scan path now populates `ScanResult.titles` from libdiscid (track number + seconds), so the same `select_tracks` rule fans out per-song Track rows for CDs.
9. Tests: 8 backend track-selection tests + 5 makemkvcon mkv parser tests + extended JobController tests (rip-start/rip-complete/eject), all passing under `uv run pytest` (38 tests total). Live-disc integration testing deferred to manual verification per Phase 2's precedent — JSONB columns on `rip_presets` block in-memory SQLite, and testcontainers is a Phase 14 deliverable.

`/raw/<job_id>/` retention is no-op until Phase 7's transcode landing; document loudly so dev disks don't fill silently.

**Crash recovery is NOT in Phase 3.** `rip-start` is idempotent (returns existing tracks on re-call), but a power cut mid-rip leaves the job in `ripping` until the Phase 9 Backend-startup sweep wipes `/raw/<job>/` and resets every track to `queued`. Documented as a known gap.

**Depends on:** Phase 1 (`tracks`, `rip_presets`), Phase 2 (`metadata_json["scan_result"]` is now load-bearing — Phase 2's identify handler was extended to persist it before commit).

---

## Phase 4 — WebSocket hub (shipped)

**Delivered** on `wolfy/v3-improvments`:

1. New `arm_common.schemas.ws` — discriminated-union message types for `auth`, `subscribe`, `unsubscribe`, `publish`, plus the outbound `WSEnvelope` / `WSAck` / `WSError` frames. The `publish` op extends what 03-protocol.md documents — the hub builds the envelope server-side (`event_id`, `emitted_at`), clients never set those themselves; documented in the new "Implementation notes" section of [03-protocol.md](../arch/03-protocol.md).
2. New `services/backend/arm_backend/ws/` package: `principal.py` (`ServicePrincipal`/`UIPrincipal` with `resolve_principal(token, hostname)` lifting the token-compare out of the FastAPI dep so the same check runs in REST and WS paths), `authz.py` (`can_subscribe`/`can_publish` enforcing the per-principal topic matrix from [05-cross-cutting.md § WebSocket security](../arch/05-cross-cutting.md#websocket-security)), `hub.py` (in-memory `WSHub` with 1 Hz/track progress throttle and 2s per-recipient send timeout that evicts slow subscribers), `router.py` (`/ws` endpoint with origin allowlist, service-token-subprotocol skip, 5s unauth timeout, message dispatch loop).
3. Backend lifespan attaches `app.state.ws_hub`; `/ws` route registered. New `ARM_ALLOWED_ORIGINS` setting (comma-separated, empty-by-default per Phase 4 — service-token only until the UI ships in Phase 5).
4. Typed events emitted from REST handlers: `rip.needs_user_input` (identify lands `awaiting_user_id`), `rip.started` (rip-start), `track.completed` / `track.failed` (PATCH track), `rip.completed` / `rip.partial` / `rip.failed` (rip-complete), `identify.resolved` (resolve, fanned out on both `ripper.events` and the per-drive `ripper.commands.{drive_id}` command topic). Every typed event also writes an `events` row in the same transaction; `ripper.progress.*` bypasses persistence.
5. Resolve handler now preserves `metadata_json["scan_result"]` when overwriting metadata, so post-resolve rip-start can still find the scan list.
6. New `services/ripper/arm_ripper/ws_client.py` — long-lived `WSClient` with reconnect-with-backoff (1s → 2s → 4s → 8s → 30s cap), auth-then-replay-subscriptions on every connect, fire-and-forget `publish` (drops silently when disconnected), per-topic dispatch to async handlers. Uses stdlib `websockets>=12` over the merged trust store.
7. `JobController` rewired: `_await_resolution` is now event-driven on an `asyncio.Event` keyed by `job_id`, set by the WS handler when `identify.resolved` arrives. 5s boot-race fallback to REST `get_job` covers the window before the WS handshake completes; periodic REST sanity polls handle a torn WS connection. `on_track_progress` callback now publishes `ripper.progress.{job_id}` over WS (no `eta_seconds` — the protocol doc lists it but PRGV doesn't carry remaining time; deferred).
8. Tests: 28 new backend tests (principal, origin, hub fan-out + persist + throttle + eviction, full authz matrix) + 4 new ripper tests (WS client handshake / subscribe replay on reconnect / publish-while-disconnected, JobController WS-event-unblocks-resolution). Existing 38 tests still green; full suite at 70 tests.

`eta_seconds` on `ripper.progress.*` is the only protocol field deferred (PRGV doesn't expose it — derive from elapsed-vs-fraction is its own ticket). The `identify.resolved` payload is ad-hoc; Phase 11 (notifications) will tighten it once Apprise consumers care.

**Depends on:** Phase 3 (there's something to stream progress *about*).

---

## Phase 5 — User auth + UI walking skeleton (shipped)

**Delivered** on `wolfy/v3-improvments`:

1. **JWT plumbing** — new [arm_backend/jwt_utils.py](../../services/backend/arm_backend/jwt_utils.py) issues / verifies HS256 access tokens (7-day TTL, no refresh per [05-cross-cutting.md § Authentication model](../arch/05-cross-cutting.md#authentication-model)) signed with `config.session_signing_key`. The signing key is cached on `app.state.signing_key` during the lifespan startup; rotation requires a backend restart (the documented "log out everywhere" lever).
2. **Two-direction auth split** — [arm_backend/auth.py](../../services/backend/arm_backend/auth.py) gains `require_jwt` (loads the User row from a verified JWT, 403s a `password_must_change=true` user on every UI route except `/api/auth/password` + `/api/auth/logout`) and tightens `require_service_token` to reject JWT-shaped tokens. UI routes use `Depends(require_jwt)`; ripper routes use `Depends(require_service_token)`. The "UI endpoints reject service token, ripper endpoints reject UI JWT" rule from [05-cross-cutting.md § Authorization rules](../arch/05-cross-cutting.md#authorization-rules) is now enforced at dependency choice, not runtime branching.
3. **Auth router** — `POST /api/auth/login` (verifies argon2id, transparently rehashes if the cost factor is stale, surfaces `password_must_change` on the response), `POST /api/auth/logout` (no-op; client drops the token), `POST /api/auth/password` (verifies current password, rotates the hash, clears `password_must_change` — does NOT issue a new JWT, since no claims changed).
4. **UI-only REST routers** — `GET /api/jobs` (paginated + status/drive filters), `GET /api/jobs/{id}` (returns `JobDetailView` = job + tracks in one round-trip), `GET /api/drives`, `GET /api/sessions` (read-only; CRUD lands in Phase 6), `GET/PATCH /api/config` (server-side strips `session_signing_key` from every response — secret never wire-exposed), `GET /api/diagnostics` (Phase 5 ships backend's `ARM_LOG_LEVEL` only; per-service introspection is Phase 12). The existing `POST /api/jobs/{job_id}/resolve` is now gated behind `require_jwt`, dropping the Phase-2 `# Phase 5:` marker.
5. **WS UI JWT principal** — [arm_backend/ws/principal.py](../../services/backend/arm_backend/ws/principal.py) `resolve_principal` extends to verify UI JWTs against the cached signing key, returning `UIPrincipal(user_id, username)`. The Phase 4 `AuthError("UI JWT auth not yet supported")` stub is gone. UI doesn't open a WS in Phase 5, but the wire is hot — verified live from the ripper container.
6. **Vue 3 SPA** — new [services/ui/](../../services/ui/) scaffold: Vue 3 + `<script setup>` + TypeScript, Pinia for the auth + jobs stores, vue-router with nav guards (anonymous → /login, must-change → /change-password, authenticated /login → /jobs), hand-rolled `fetch` wrapper that puts the JWT in localStorage and resets on 401. Pages: Login, ChangePassword, Jobs (5s REST polling), JobDetail, Drives, Sessions, Config (full edit form for TMDB/OMDB keys, Apprise URLs, retention policy, etc.), Diagnostics. `openapi-typescript` generates types off a committed `openapi.snapshot.json`; hand-written `src/api/types.ts` is the projection the views actually import.
7. **arm-ui container** — [services/ui/Dockerfile](../../services/ui/Dockerfile) is a multi-stage `node:22-alpine` → `nginx:1.27-alpine` build. nginx serves the static SPA, reverse-proxies `/api/*` and `/ws/*` to `https://arm-backend:8443` over the merged trust store, and ships a strict CSP + `X-Content-Type-Options nosniff` + no-referrer policy. UI-specific entrypoint does the CA merge but skips the gosu-arm drop (nginx manages its own privilege drop after binding 443). New compose service exposes `8081:443`, threads `ARM_ALLOWED_ORIGINS` through to backend, mounts `arm-ui.{crt,key}` issued by [v3/install.sh](../../install.sh) with SANs `arm-ui` + `localhost` + `hostname -f`.
8. **`ARM_ALLOWED_ORIGINS` parsing fix** — `pydantic-settings` JSON-parses `list[str]` env vars by default; `ARM_ALLOWED_ORIGINS=https://localhost:8081` blew up at backend startup. Wrapped the field in `Annotated[..., NoDecode]` so the existing `_split_origins` validator sees the raw string. Compose now threads `ARM_ALLOWED_ORIGINS` from `.env` into `arm-backend`; `.env.example` documents the default.
9. **Tests** — 26 new backend tests (`test_jwt_utils.py`, `test_jwt_split.py`, `test_auth_router.py`, `test_ws_principal_jwt.py`) covering issue/verify round-trip, signature/expiry/`sub`-missing rejection, the eight-way require_jwt × require_service_token × wrong-token-shape × must-change-flag matrix, and full TestClient round-trips on login/password/logout. 8 new frontend Vitest tests covering auth-store hydrate/login/logout/401-reset and four router-guard cases. Backend total: 80 → 80+18 ripper = 98 tests, all green; mypy strict and ruff clean. Frontend `npm test` + `npm run build` both clean.
10. **Live verification** — `docker compose up -d`; browser-equivalent curl flow exercised: login (200 + `must_change=true`) → `GET /api/jobs` (403, "password change required") → `POST /api/auth/password` (200) → same JWT now unblocks `/api/jobs` (200 + 6 jobs). UI endpoint with service token → 401 ("UI endpoint requires user JWT, not service token"); ripper endpoint with UI JWT → 401 ("service endpoint requires service token, not UI JWT"). WS connection from inside the ripper container with the UI JWT: auth ack → subscribe `ripper.events` ack → subscribe `ripper.commands.drv_xxx` rejected with code 4403.

Visual UI verification deferred to manual click-through; per [05-cross-cutting.md § Testing strategy](../arch/05-cross-cutting.md#testing-strategy) we do not ship Playwright. Phase 13 (installer) auto-detects host SANs; today the bootstrap script hardcodes `localhost` + `hostname -f`. Snapshot-drift CI lands in Phase 14.

**Depends on:** Phase 1 (`users`, `config`), Phase 3 (jobs exist), Phase 4 (WS hub stub for UIPrincipal already in place).

---

## Phase 6 — Sessions & session applications (shipped)

**Goal.** The CRUD layer for user-authored sessions. Creating a session application against a ripped job produces `transcode_tasks` rows in `queued` state — but nothing transcodes them yet (Phase 7).

**Exit criteria — met.** A user can clone a built-in session, tweak it, apply it to a ripped job via `POST /api/jobs/{job_id}/transcode`, and see the resulting `session_applications` + `transcode_tasks` rows. Path-template validation rejects templates that produce empty required tokens. Cross-session and cross-job collisions surface the dialog described in [02-job-lifecycle.md § Concurrent write safety](../arch/02-job-lifecycle.md#concurrent-write-safety).

**Deliverables:**
1. **REST CRUD** for sessions, rip presets, and transcode presets. `POST /api/sessions/{id}/clone` is a first-class endpoint that copies a built-in into a user-owned non-builtin row. `is_builtin=true` rows are name-only-editable; `DELETE` is refused with a useful message. `DELETE /api/rip-presets/{id}` and `DELETE /api/transcode-presets/{id}` 409 with the names of any sessions still referencing the preset.
2. **`POST /api/jobs/{job_id}/transcode`** is the apply endpoint — body `{session_id, overwrite: bool=false}`. Idempotent on `(session_id, job_id)`. Returns `ApplySessionResponse {session_application, tasks, collisions, idempotent}`. On `AWAITING_USER_ID` the application is parked in `WAITING_IDENTIFY` with no tasks (real fan-out-on-resolve is Phase 10's job).
3. **Path-template expansion + validation** in [arm_backend/path_template.py](../../services/backend/arm_backend/path_template.py): per-`MediaType` token whitelist mirrors arch §02, synthetic-context expansion at save-time, real-data expansion at apply-time. `{transcode_slug}` requires a transcode preset; `{ext}` requires one (except `media_type=ISO`). Empty real-data tokens raise 422 — better than writing `Iron Man () - .mkv`.
4. **Apply-time collision check** in [arm_backend/transcode_apply.py](../../services/backend/arm_backend/transcode_apply.py): single `SELECT … WHERE output_path IN (...) AND status IN live_states` against `transcode_tasks`, plus an `os.stat` against `MEDIA_ROOT/<path>` for filesystem-only hits (pre-v3 user content). 409 with `{collisions: [...]}` unless `overwrite=true`. The partial unique index on `transcode_tasks(output_path)` is the DB-level safety net for TOCTOU races; `IntegrityError` maps to a generic 409 too.
5. **`GET /api/transcodes`** with `?status=` and `?session_application_id=` filters; **`DELETE /api/transcodes/{id}`** soft-cancels `QUEUED` tasks (`status=FAILED, last_error="cancelled by user"`) and 409s on `IN_PROGRESS` (running cancel lands in Phase 7).
6. **`POST /api/sessions/preview`** drives the wizard's live template preview — debounced 300 ms client-side, returns the synthetic expansion or a 422 with the validation message.
7. **UI:** new `SessionForm.vue` (used at `/sessions/new` and `/sessions/:id/edit`), full CRUD for `RipPresets.vue` / `RipPresetForm.vue` and `TranscodePresets.vue` / `TranscodePresetForm.vue`, a `TrackFiltersEditor.vue` component that renders only when `track_selection==custom`, and an `ApplySessionDialog.vue` on `JobDetail.vue` that surfaces the collision flow. Pinia stores: `sessions.ts`, `ripPresets.ts`, `transcodePresets.ts`, `transcodes.ts`. Built-in protection is also enforced UI-side (Edit on a built-in only exposes the name field).
8. **`custom` rip-preset support.** Declarative `TrackFilters` schema (`min_duration_seconds`, `max_duration_seconds`, `title_indices`, `title_indices_exclude`) — all conditions ANDed. Required iff `track_selection==CUSTOM`; rejected at save otherwise. [arm_backend/track_selection.py](../../services/backend/arm_backend/track_selection.py) is no longer raising `NotImplementedError` for CUSTOM; the rip pipeline now consumes the filters end-to-end.
9. **Tests:** 36 new backend tests (path-template, slugify, custom-track-selection, compute_outputs, sessions/rip-presets routers, apply-session matrix), 4 new Vitest specs (sessions store CRUD + apply + collision retry). 156 backend / 12 UI total — all green.

**Depends on:** Phase 1 (every session-related table), Phase 3 (applying against real ripped jobs), Phase 5 (UI to drive it).

---

## Phase 7 — Transcode container (ephemeral, per-task, shipped)

**Goal.** Backend dequeues `transcode_tasks` and spawns `arm-transcode-<uuid>` containers via the Docker socket. Each container transcodes one raw into one output under `/media/`. Full rip→transcode flow completes end-to-end. CPU-only — GPU is Phase 7b.

**Exit criteria — met.** Applying a "Plex 1080p H.265" session to a ripped movie produces a real file at `/media/Movies/{Title} ({Year})/{Title} ({Year}) - plex-1080p-h-265.mkv`. The transcode task transitions `queued → in_progress → done`; the parent session application aggregates to `done`; `transcode.events` fires the typed events; the UI shows live progress over `transcode.progress.{task_id}`. Killing a transcoder mid-run leaves a `.arm-inprogress` file that the next Backend boot sweeps; the stale-claim sweep recovers heartbeat-lapsed tasks within ~90 s.

**Delivered** on `wolfy/v3-improvments`:

1. **`services/transcode/` image + `arm_transcode` package.** Single-stage `python:3.14-slim-bookworm` + `tini gosu handbrake-cli ffmpeg flac` (+ ca-certificates). The shared `services/_common/docker-entrypoint.sh` no-ops past its MakeMKV gate, so the same CA-merge + PUID-drop pattern carries unchanged. New compose service `arm-transcode-builder` (profile `build-transcode`) for `docker compose build`; the dispatcher refers to the image by name and spawns containers on demand. `arm_transcode/` contains: `main.py` (single-task lifecycle), `api_client.py` (httpx wrapper), `ws_client.py` (long-lived WS w/ `X-ARM-Task-Id`), `handbrake.py` (`HandBrakeCLI --json` progress parser), `ffmpeg_audio.py` (FLAC/MP3 from WAV), `passthrough.py` (TranscodeTool.NONE rename-or-copy), `atomic.py` (`*.arm-inprogress` context manager), `heartbeat.py` (REST every 30 s + WS publish every ~1 s), `config.py` (env binding).
2. **Backend `TranscodeDispatcher`** ([transcode_dispatcher.py](../../services/backend/arm_backend/transcode_dispatcher.py)) — single asyncio task started in `main.py` lifespan. Each tick runs the stale-claim sweep (`UPDATE … WHERE status='in_progress' AND claim_heartbeat_at < now() - threshold`; resets to `queued`, hard-fails after `MAX_ATTEMPTS=3`) and dequeues queued tasks via `SELECT … FOR UPDATE SKIP LOCKED LIMIT N`. Spawns one container per row via docker-py, with host-side mount paths from `ARM_HOST_*_PATH` env (set by compose to `${PWD}/{raw,media,logs,certs}`). `.arm-inprogress` orphan sweep runs once at lifespan startup (Backend, not transcoder, since transcoders are single-task ephemeral).
3. **Transcoder REST surface** at `/api/transcoder/`: `register`, `tasks/{id}/claim`, `tasks/{id}/heartbeat`, `tasks/{id}/complete`, `tasks/{id}/fail` ([routers/transcoder.py](../../services/backend/arm_backend/routers/transcoder.py)). Service-token gated. `claim` is the `queued → in_progress` transition; on first claim per session_application the application also flips `queued → running` and emits `session.started`. `complete`/`fail` emit `task.completed`/`task.failed` and re-aggregate via `aggregate_session_application` (in [transcode_apply.py](../../services/backend/arm_backend/transcode_apply.py)) → `session.completed` / `session.partial` / `session.failed`.
4. **Atomic rename** in the transcoder ([atomic.py](../../services/transcode/arm_transcode/atomic.py)). HandBrake/ffmpeg write to `<final>.arm-inprogress`; on success the context manager fsyncs the parent dir and `os.replace`s to `<final>`. On exception the partial stays for the Backend startup sweep.
5. **WS principal extension.** `resolve_principal` now takes a `task_id_hint` (sourced from the `X-ARM-Task-Id` header at the WS handshake) and produces `ServicePrincipal(kind="transcoder", hostname=..., task_id=...)`. Authz: transcoders may subscribe `transcoder.commands.{task_id}` (cancel) and publish `transcode.progress.{task_id}` iff the task is `claimed_by` the same hostname AND `IN_PROGRESS`. The hub now throttles `transcode.progress.*` at 1 Hz alongside `ripper.progress.*`.
6. **Cancel on IN_PROGRESS** — `DELETE /api/transcodes/{id}` for a running task no longer 409s. The router fires `dispatcher.cancel_running(task_id)` non-blocking; the dispatcher emits `task.cancel` over `transcoder.commands.{task_id}`, waits 10 s for a graceful `/fail`, then falls back to `client.containers.list(filters={"label": "arm.task_id=..."}).stop(timeout=5)` and force-marks the task `failed`. Queued cancels are unchanged from Phase 6 (sync soft-cancel).
7. **UI** — [stores/transcodes.ts](../../services/ui/src/stores/transcodes.ts) gains a singleton WS client ([api/ws.ts](../../services/ui/src/api/ws.ts)) with subscribe-on-demand + reconnect-with-backoff. The store tracks per-task live progress in a `liveProgress` shadow map (so a list re-fetch doesn't clobber an in-flight tick) and reconciles `transcode.progress.{task_id}` subscriptions whenever the task set's IN_PROGRESS subset changes. JobDetail.vue grew a "Transcode tasks" panel with live progress bars and a Cancel button.
8. **Tests:** 41 new backend tests (`test_transcoder_router.py` × 12, `test_transcode_aggregate.py` × 6, `test_transcode_dispatcher.py` × 11, `test_ws_transcoder_principal.py` × 12), 14 new transcode-service tests (`test_atomic.py`, `test_handbrake.py`, `test_passthrough.py`, `test_config.py`), 5 new Vitest specs (`transcodes.spec.ts`). 211 backend+ripper+transcode / 17 UI total — all green; mypy strict + ruff lint clean.

`docker-compose.yml` got the Backend's `/var/run/docker.sock` mount (acceptable per `06-deployment.md:254`) and the `./media:/media` mount; `.env.example` documents the host-path knobs. Snapshot regen of `services/ui/openapi.snapshot.json` covers the new schema surface.

**Depends on:** Phase 6 (queued tasks exist), Phase 4 (progress WS).

### Phase 7b — GPU transcoding

**Goal.** Light up VAAPI / NVENC / QSV hardware encoders behind the same dispatcher loop, so applying a "Plex 1080p H.265" session on a host with a GPU produces a real `.mkv` encoded by the GPU (visibly faster + measurable in `nvidia-smi`/`intel_gpu_top`). Hosts without a GPU regress to nothing — the CPU path from Phase 7 stays the silent fallback.

**Exit criteria — met.** On a GPU host (Intel iGPU / AMD GPU / NVIDIA), Backend's lifespan probe populates the `gpus` table, the dispatcher claims a row before spawning, and `arm-transcode-<id>` runs `HandBrakeCLI ... --encoder vaapi_h265` (or `nvenc_h265` / `qsv_h265`). On task complete/fail, the row flips back to `available`. On a CPU-only host, the table stays empty, `transcode.hw_unavailable` fires once at startup, and every task spawns CPU exactly as before.

**Delivered** on `wolfy/v3-improvments`:

1. **`codec` column on `transcode_presets`** ([0002 migration](../../services/backend/migrations/versions/0002_transcode_preset_codec.py)) — explicit predicate for the GPU↔preset match. Backfills seeded rows by ILIKE on `preset_ref`. `VideoCodec(H264|H265|AV1)` enum on the SQLModel + view/request schemas + UI types. Built-in H.265 / TV / 2160p presets backfilled to `H265`.
2. **`gpu_probe.py`** at Backend startup ([gpu_probe.py](../../services/backend/arm_backend/gpu_probe.py)) — `_probe_dri()` enumerates `/dev/dri/renderD*` and reads `/sys/class/drm/<n>/device/vendor` (Intel `0x8086` → QSV, AMD `0x1002` → VAAPI; NVIDIA Mesa nodes skipped). `_probe_nvidia()` shells `nvidia-smi -L`; `FileNotFoundError` and non-zero exit both cleanly degrade to `[]`. Both paths advertise `["h264", "h265"]` for now. Lifespan truncates `gpus`, refills, and emits `transcode.hw_unavailable` on empty.
3. **Dispatcher GPU dispatch** ([transcode_dispatcher.py](../../services/backend/arm_backend/transcode_dispatcher.py)) — `_claim_gpu_for_task` implements the four-branch matrix from `04-data-model.md:126`: `cpu_only` → CPU; `any` → GPU if free else CPU; `NULL` → GPU if free, queue if busy, CPU only when no GPU advertises this codec. `_inject_gpu_run_kwargs` adds `devices=` for VAAPI/QSV (`/dev/dri/renderD*:rwm`) and `runtime="nvidia"` + `device_requests=[DeviceRequest(driver="nvidia", count=1, device_ids=[idx], capabilities=[["gpu","video"]])]` for NVENC. Spawn-failure branch rolls the claim back so the next tick can retry. The stale-claim sweep also releases the claimed `gpus` row.
4. **Transcoder release on terminal** — `release_gpu_for_task` is a module-level helper called from `complete` and `fail` in [routers/transcoder.py](../../services/backend/arm_backend/routers/transcoder.py); idempotent.
5. **`--encoder` injection** in [arm_transcode/handbrake.py](../../services/transcode/arm_transcode/handbrake.py) — `_hw_encoder_args()` reads `ARM_GPU_VENDOR` + `ARM_GPU_CODEC` from env and returns `["--encoder", "<vendor>_<codec>"]` from a 6-entry table (vaapi/qsv/nvenc × h264/h265). Inserted after `--preset` so HandBrake's preset CPU encoder is overridden; `extra_args` from the user-defined preset still wins via append-last. AV1 deferred (encoder-name space varies by silicon generation).
6. **Compose overlay + Backend image** — [docker-compose.gpu.yml](../../../docker-compose.gpu.yml) adds `/dev/dri:/dev/dri:ro` + `runtime: nvidia` + `deploy.resources.reservations.devices` to the Backend service. Users opt in via `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up`. The Backend image apt-installs `nvidia-utils-535` from Debian `non-free` / `bookworm-backports` (override the version with `--build-arg NVIDIA_UTILS_VERSION=...` if your host driver is on a different major branch); the probe degrades cleanly when `nvidia-smi`'s version disagrees with the host driver. CPU-only hosts use the base compose unchanged. .env.example documents the overlay knob; [services/transcode/README.md](../../services/transcode/README.md) gains a "GPU transcoding" section with the full hw_preference matrix.
7. **Tests:** 19 new (`test_gpu_probe.py` × 5: empty host, VAAPI-only, QSV+NVENC mix, nvidia-smi missing, nvidia-smi rc≠0; `test_transcode_dispatcher_gpu.py` × 12 spanning the full hw_preference × availability × vendor matrix; `test_transcoder_router_gpu.py` × 2 for complete/fail release; `test_handbrake_hw.py` × 11 covering all 6 vendor/codec pairs + edge cases). 241 backend+ripper+transcode / 17 UI total; mypy strict + ruff lint clean; OpenAPI snapshot regenerated.

**Depends on:** Phase 7 (CPU dispatch surface).

---

## Phase 8 — Auto-session / default_session_id

**Goal.** `drives.default_session_id` + `config.auto_transcode_on_idle=true` causes each successful rip to auto-queue its default session.

**Exit criteria — met.** A drive with a `default_session_id` set + `Config.auto_transcode_on_idle=true` produces a `session_application` automatically when `rip-complete` flips the job to `RIPPED` or `RIPPED_PARTIAL`. CPU/GPU paths route as before via the Phase 7/7b dispatcher; on success the user sees a transcode appear in the UI without ever clicking "Apply session".

**Delivered** on `wolfy/v3-improvments`:

1. **Apply-session core extracted to `arm_backend/auto_session.py`.** `apply_session_internal` is the single engine behind both code paths — manual `POST /api/jobs/{id}/transcode` and the new auto hook. Returns `ApplySessionOutcome(application, tasks, collisions, idempotent, skipped_reason)` so callers map outcomes to the right surface (HTTP 4xx for the route, log+swallow for the hook). `routers/jobs.py:apply_session` shrinks to a ~30-line shim that maps `SessionNotFoundError` → 400, `skipped_reason="collisions"` → 409, `IntegrityError` → 409.
2. **`maybe_auto_apply_session` hook** in [auto_session.py](../../services/backend/arm_backend/auto_session.py), called from [routers/ripper.py:rip_complete](../../services/backend/arm_backend/routers/ripper.py) when `job.status in (RIPPED, RIPPED_PARTIAL)`. Loads the `Drive`, returns early if `default_session_id is None`; loads `Config(id=1)`, returns early if `auto_transcode_on_idle is False`. Wraps the helper call in `try/except`; `SessionNotFoundError`, `TemplateValidationError`, `IntegrityError`, and the catch-all `Exception` all log at WARN and never re-raise — `rip-complete`'s 200 response is preserved on every failure mode.
3. **`session.queued` WS event** emitted by `apply_session_internal` exactly once on successful fan-out, on topic `session.events`, with payload `{session_application_id, session_id, job_id, source: "manual"|"auto", task_count}`. Idempotent re-applies skip the emit because they exit the helper before the spawn branch. The manual route picks up the emit for free; previously it emitted nothing.
4. **`PATCH /api/drives/{drive_id}`** in [routers/drives.py](../../services/backend/arm_backend/routers/drives.py) accepts a `DriveUpdateRequest` ([schemas/drives.py](../../packages/arm_common/arm_common/schemas/drives.py)) with optional `display_name` and `default_session_id` (both nullable; explicit `null` clears, omit to leave untouched, `extra="forbid"` rejects typos at 422). Validates that a non-null `default_session_id` references a real session row (400 if not).
5. **UI Drives page** ([Drives.vue](../../services/ui/src/views/Drives.vue)) gains a "Default session" `<select>` column. `Promise.all` fetches drives + sessions on mount; `@change` PATCHes `/api/drives/{id}` and updates the local ref. `DriveUpdateRequest` added to [api/types.ts](../../services/ui/src/api/types.ts); `api.patch` was already in place.
6. **Tests:** 19 new (`test_auto_session.py` × 6 covering manual vs auto emit, idempotent reuse, collision skip, missing-session raise, awaiting_user_id parking; `test_ripper_router_auto.py` × 6 for the hook gates and graceful no-ops; `test_drives_router.py` × 6 for the PATCH happy/error paths; `test_apply_session.py` extended × 1 to assert `session.queued` fires with `source: "manual"`). 1 new Vitest spec (`drives.spec.ts`) verifying the dropdown renders one option per session plus a "— none —" entry. 260 backend+ripper+transcode / 18 UI total; ruff lint clean; OpenAPI snapshot regenerated to cover `DriveUpdateRequest` + the PATCH endpoint.

No DB migration was required — [drive.py:31-33](../../packages/arm_common/arm_common/models/drive.py) and [config.py:18](../../packages/arm_common/arm_common/models/config.py) already had `default_session_id` (FK with `ON DELETE SET NULL`) and `auto_transcode_on_idle` since Phase 1. Known limitation: the dropdown is unfiltered — picking a TV session for a movie drive is allowed; auto-apply will then fail at template-resolve time and skip cleanly. UX polish (filter dropdown by media type, surface a notice on auto-skip) is deferred.

**Depends on:** Phase 7.

---

## Phase 9 — Crash recovery

**Goal.** The top-2 pain point that motivated v3 ([00-vision.md](../arch/00-vision.md)). Five queued rips + simulated power cut mid-batch resumes cleanly.

**Exit criteria — met.** A backend restart while one rip is in flight resets the job's tracks to `queued`, increments their `attempts`, and stamps `resumed_from_crash=true`; the UI shows a "resumed from crash" badge alongside the status. A ripper-only restart with the disc still in the tray detects the in-flight job, wipes `/raw/<job_id>/` locally, calls `POST /resume`, and re-rips. The UI badge clears automatically when the job reaches a terminal status.

**Delivered** on `wolfy/v3-improvments`:

1. **Reset helper extracted to [arm_backend/crash_recovery.py](../../services/backend/arm_backend/crash_recovery.py).** `reset_job_for_recovery(db, job)` is the single engine: it sets `Job.resumed_from_crash=True` and, for every non-`QUEUED` track on the job, flips status to `QUEUED` and increments `attempts`. Idempotent — already-queued tracks are skipped, so re-runs neither inflate counters nor double-stamp the flag. `sweep_in_flight_jobs(SessionLocal)` wraps it for batch use against all `JobStatus.RIPPING` rows in one transaction.
2. **Backend-startup sweep** wired into the FastAPI `lifespan` in [main.py](../../services/backend/arm_backend/main.py) between the GPU inventory refresh and the `TranscodeDispatcher` construction. Same try/except + log shape as the existing `sweep_arm_inprogress` hook. Failures log at exception level but never block boot.
3. **`POST /api/ripper/jobs/{job_id}/resume`** in [routers/ripper.py](../../services/backend/arm_backend/routers/ripper.py) is the per-job recovery endpoint for the "only ripper crashed, backend stayed up" case. Validates `job.status == RIPPING` (409 otherwise), runs `reset_job_for_recovery`, emits `rip.resumed` on `ripper.events` with payload `{job_id, drive_id, track_count, resumed_from_crash: True}`, and returns the same `RipStartResponse` shape as `rip-start` so the ripper's existing rip-loop continues unchanged. Reuses `require_drive_owner_by_job` so a misrouted call from the wrong host returns 403 before any state mutation.
4. **`GET /api/ripper/drives/{drive_id}/in-flight-job`** is the boot-probe lookup. Returns a `JobView` (200) for the single `RIPPING` job assigned to that drive, 404 if none. Uses `require_service_token` plus an explicit drive-existence check; multiple matches (a data-model violation) log + return the first row.
5. **Ripper recovery module** at [services/ripper/arm_ripper/recovery.py](../../services/ripper/arm_ripper/recovery.py) wires it together. `wipe_raw_dir(job_id)` is `shutil.rmtree(/raw/<job_id>, ignore_errors=True)`. `boot_probe(client, drive_id, device_path, controller)` queries the in-flight endpoint, probes `ioctl` for disc presence, wipes `/raw/<job_id>/`, and hands off to a new `JobController.resume_inflight_job(job, device_path)`. All exceptions log + swallow so a misbehaving probe never blocks the ripper's normal `poll_loop`. `BackendClient.get_in_flight_job` and `BackendClient.resume` are the two new HTTP wrappers.
6. **JobController refactor** ([job_controller.py](../../services/ripper/arm_ripper/job_controller.py)) extracts the post-rip-start body of `_run_rip` into `_execute_rip(*, job_id, disc_type, device_path, rip_start)`. Both the normal disc-inserted path (via `_run_rip` after `rip_start`) and the boot-probe path (via `resume_inflight_job` after `client.resume`) reuse it. No behaviour change to the normal path.
7. **`JobView.resumed_from_crash: bool`** added to [arm_common/schemas/jobs.py](../../packages/arm_common/arm_common/schemas/jobs.py); SQLModel's `from_attributes=True` picks it up automatically. `Track.attempts` was already on `TrackView`. UI side: [api/types.ts](../../services/ui/src/api/types.ts) adds the field; [Jobs.vue](../../services/ui/src/views/Jobs.vue) and [JobDetail.vue](../../services/ui/src/views/JobDetail.vue) render a `resumed from crash` badge alongside the status badge, gated by the new [utils/jobStatus.ts](../../services/ui/src/utils/jobStatus.ts) `isTerminalJobStatus()` helper. The DB flag itself is never cleared (permanent audit trail); the UI hides the badge once `status` becomes terminal.
8. **Transcode stale-claim sweep** (deliverable 4) was already in place via [TranscodeDispatcher.sweep_stale_claims](../../services/backend/arm_backend/transcode_dispatcher.py) — runs on every dispatcher tick. No code change.
9. **Tests:** 14 new backend (`test_crash_recovery.py` × 5 for `reset_job_for_recovery` + `_sweep`; `test_ripper_resume.py` × 9 covering `/resume` happy/idempotent/409/404/401/403 and `/in-flight-job` 200/404/404/401), 6 new ripper (`test_boot_probe.py` covering no-inflight, disc-absent, disc-present wipe + resume, resume failure, HTTP error swallow, idempotent wipe), 2 new Vitest (`jobs.spec.ts` for badge shown when non-terminal + hidden when terminal). 246 backend / 30 ripper / 20 UI total; ruff format + ruff lint + mypy strict clean; OpenAPI snapshot regenerated to cover `JobView.resumed_from_crash`, `POST /api/ripper/jobs/{id}/resume`, and `GET /api/ripper/drives/{id}/in-flight-job`.

No DB migration was required — `Job.resumed_from_crash` ([job.py:34](../../packages/arm_common/arm_common/models/job.py)) and `Track.attempts` ([track.py:31](../../packages/arm_common/arm_common/models/track.py)) shipped with Phase 1. Known limitations: a disc ejected during the crash leaves the `RIPPING` row visible with the badge but no auto-cleanup — the user manually intervenes (insert disc to start a fresh job, or abandon). The "two RIPPING jobs on one drive" data-model violation is logged and the first row returned; no automatic resolution. The ripper-still-mid-rip-when-backend-crashes race causes one extra `attempts++` per affected track when the ripper's next PATCH lands; cosmetic only.

**Depends on:** Phase 3 (rip pipeline), Phase 7 (transcode side).

---

## Phase 10 — Placeholder rips (deferred identity)

**Goal.** Opt-in flow where an identify miss rips immediately to `/raw/<job_id>/`; session applications park in `waiting_identify`; resolving identity later fans out transcode against the resolved title. **No files are ever renamed or moved.**

**Exit criteria.** With `config.block_on_miss=false` or a `deferred_placeholder` rip preset, an unknown disc rips without blocking; a queued session sits in `waiting_identify`; user resolves identity via `POST /api/jobs/{job_id}/resolve`; transcode fans out against the now-resolved title.

**Deliverables:**
1. **Rip-preset handling** for `identification_mode = required | skip | deferred_placeholder`.
2. **`session_applications.status = waiting_identify`** state + transitions (`waiting_identify → queued` on resolve).
3. **UI** — prompt + resolve modal, "queued — waiting for you to identify this disc" badge, `skip` mode (home movies) generic-title form.

**Depends on:** Phase 7 (transcode fan-out), Phase 6 (session applications), Phase 3 (rip pipeline).

---

## Phase 11 — Notifications (shipped)

**Goal.** Apprise dispatcher consumes typed events and fires outbound webhooks.

**Exit criteria.** With `notifications_enabled=true` and at least one Apprise URL configured, `rip.{completed,failed,partial}` and `session.{completed,failed,partial}` events trigger outbound notifications end-to-end. Disabled (the default) → no traffic.

**What shipped:**

1. **Polling dispatcher** at [services/backend/arm_backend/notification_dispatcher.py](../../services/backend/arm_backend/notification_dispatcher.py) — single asyncio task started in lifespan, mirrors `TranscodeDispatcher`. Each tick reads unsent notifiable events from `events`, loads the `Config` singleton, and either fires Apprise (when enabled + URLs present) or marks `notified_at` without dispatching (the "off out of the box" path). `AppriseNotifier` is a `Protocol` with `_RealAppriseNotifier` wrapping `apprise.Apprise().async_notify`; tests inject a fake.
2. **`Config.notifications_enabled: bool` master toggle** ([config.py:31-34](../../packages/arm_common/arm_common/models/config.py)) defaults False. The URL list alone is not consent — the user must actively check "Enable notifications" in the UI before any traffic is generated. Surfaced in `ConfigView` / `ConfigUpdateRequest` and edited via a checkbox in [Config.vue](../../services/ui/src/views/Config.vue) above the existing Apprise textarea.
3. **`Event.notified_at: datetime | None` watermark** ([event.py:34](../../packages/arm_common/arm_common/models/event.py)). Migration [0003_notifications.py](../../services/backend/migrations/versions/0003_notifications.py) adds the column + index, backfills `notified_at = emitted_at` on existing rows (avoids dumping the historical event log on first deploy), and adds `notifications_enabled` to `config` with `server_default=false`.
4. **Server-side URL validation** in [routers/config.py](../../services/backend/arm_backend/routers/config.py) — `_first_invalid_apprise_url` runs each pasted URL through a fresh `apprise.Apprise().add(url)`. Failure returns 400 with a redacted detail (`"invalid apprise URL: <scheme>://****"`) so a 400 response is safe to paste into a bug report. Validation runs whether `notifications_enabled` is True or False.
5. **Scheme-only redaction** via `redact_apprise_url(url) → "<scheme>://****"`. Apprise stashes credentials in netloc/path/query depending on the provider, so surgical masking is fragile. The dispatcher logs only redacted URLs; the config router logs nothing about config bodies. Asserted by a `caplog`-based test that ensures no raw credential token (`"AAA"` / `"BBB"`) ever appears in a log line.
6. **Notifiable event types** are a frozen set: `rip.{completed,failed,partial}` + `session.{completed,failed,partial}`. Existing emit sites are untouched; payload shapes are frozen per [03-protocol.md § Versioning](../arch/03-protocol.md#versioning).
7. **Best-effort semantics.** `notified_at` is set whether or not Apprise succeeded — a permanently-broken URL drops one notification rather than logspamming forever. Empty URL list and disabled state both still mark `notified_at` so events do not pile up while notifications are off.
8. **Tests:** 20 new (`test_notification_dispatcher.py` × 9 covering disabled/enabled/empty/non-notifiable/already-notified/raises/multi-event/redaction; `test_notification_format.py` × 5 for title and body shapes; `test_config_apprise_validation.py` × 6 for round-trip and 400 redaction). 252 backend / 30 ripper / 23 UI; ruff format + ruff lint clean; mypy clean on the touched files (pre-existing test-file errors are unchanged); OpenAPI snapshot regenerated.

**Depends on:** Phase 4 (events persist), Phase 5 (UI config form).

**Depends on:** Phase 4 (events persist).

---

## Phase 12 — Logs persistence + per-job log view (shipped)

**Goal.** Every service's JSONL log is queryable by `job_id`; UI per-job view shows correlated lines; bug-report zip endpoint works.

**Exit criteria.** `GET /api/logs/{job_id}.zip` returns a zip containing the per-job slice of every service log. UI log viewer live-tails via `logs.{job_id}` WS topic.

**What shipped:**

1. **Shared structured-logging helper** at [packages/arm_common/arm_common/logging.py](../../packages/arm_common/arm_common/logging.py) — `configure_service_logging(service_name)` installs a `JsonFormatter` on stdout *and* a `RotatingFileHandler(/logs/<service>.log, 10 MB × 5)`. Each line carries `{ts, level, service, job_id, track_id, session_application_id, msg, extra}` per [05-cross-cutting.md § Logging](../arch/05-cross-cutting.md#logging). Backend / ripper / transcode all replaced their `logging.basicConfig` blocks with one call. The file handler is best-effort — outside a container `/logs` may be unwritable, in which case stdout still carries every line so the openapi-snapshot regen and tests don't blow up.
2. **`with_log_context(job_id=..., track_id=..., session_application_id=...)`** uses `contextvars` so async work inside the block stamps the correlation IDs without ceremony at every `logger.*` call site. Wrapped at the operation entry points: ripper `JobController.handle_disc_inserted` + per-track callbacks + `resume_inflight_job`; transcoder `amain` after register; `auto_session.apply_session_internal`; `transcode_dispatcher.spawn_pending` and `sweep_stale_claims` per-task; `notification_dispatcher._tick` per-event. Documented gotcha: `loop.run_in_executor` does NOT copy contextvars — wrap with `contextvars.copy_context().run(...)` at the executor boundary.
3. **Per-task transcode log filename** — dispatcher injects `ARM_SERVICE_NAME=arm-transcode-{task_id_short}` at spawn so parallel transcoders don't clobber a shared `/logs/arm-transcode.log` rotation. Same convention as the existing container hostname.
4. **Singleton `LogTailer`** at [services/backend/arm_backend/log_tailer.py](../../services/backend/arm_backend/log_tailer.py) — one asyncio task started in lifespan. Per drain it scandirs `/logs`, follows every `*.log` in append mode (seek-to-end on open so historical lines aren't replayed), parses each appended line as JSON, gates on `hub.subscriber_count(f"logs.{job_id}")`, and emits `log.line` envelopes via `hub.emit(persist=False, ...)`. Detects rotation via `st_ino` mismatch, drains the freshly-opened file in the same tick. Loop guard skips records whose `extra.logger` starts with `arm_backend.ws.hub` so the hub's own emit-failure logs don't feed back.
5. **Backend logs router** at [services/backend/arm_backend/routers/logs.py](../../services/backend/arm_backend/routers/logs.py): `GET /api/logs/{job_id}` streams `application/x-ndjson` (per-file `?limit=` default 1000 / hard cap 10000, files alphabetical, no cross-file resort) and `GET /api/logs/{job_id}.zip` returns an in-memory `ZIP_DEFLATED` archive with one entry per service that contributed lines (per-entry caps: 5000 lines / 5 MB). Both gated on `require_jwt`; service tokens are rejected. The `.zip` route is declared first because FastAPI would otherwise let `/{job_id}` swallow `job_x.zip`.
6. **`bug_report_zip_url` removed from `DiagnosticsResponse`** ([schemas/auth.py:69](../../packages/arm_common/arm_common/schemas/auth.py)) — it was a Phase-1 placeholder. The diagnostics endpoint is global; the zip URL is per-job. UI now hardcodes `/api/logs/{jobId}.zip` against the dedicated logs router instead of threading `?job_id=` through diagnostics.
7. **UI log pane** at [services/ui/src/components/JobLogsCard.vue](../../services/ui/src/components/JobLogsCard.vue) — mounted on `JobDetail.vue` below the tracks card. On mount: GET `/api/logs/{jobId}?limit=200` to seed, then `wsClient.subscribe(\`logs.${jobId}\`, ...)` for live tail. "Download zip" button uses a fetch+blob+anchor pattern in [api/logs.ts](../../services/ui/src/api/logs.ts) so the JWT can ride on the request (a plain anchor `href` can't carry an `Authorization` header). 2000-line cap on the in-memory pane bounds memory; earlier lines remain in the zip.
8. **Tests:** 23 new backend (`test_logging.py` × 7 covering JSONL shape + contextvar propagation + nesting + extra-override + asyncio.create_task inheritance + run_in_executor gotcha + extra.logger stamp; `test_log_tailer.py` × 7 covering subscriber gating + null/missing/bad-JSON / loop guard / rotation / new-file pickup; `test_logs_router.py` × 9 covering ndjson + per-file limit + hard cap + bad-JSON skip + zip per-entry cap + JWT enforcement + filename stamp). 3 new UI (`JobLogsCard.spec.ts` covering seed + live-tail append + zip-download). 324 backend/ripper/transcode + 26 UI; ruff format / lint / mypy clean on touched files; UI eslint + prettier clean; vue-tsc + vite build green; OpenAPI snapshot regenerated (added `/api/logs/{job_id}` and `/api/logs/{job_id}.zip`, dropped `bug_report_zip_url` from `DiagnosticsResponse`).

**Depends on:** Phase 4 (WS hub), Phase 5 (UI).

---

## Phase 13 — Installer (install.sh) (shipped)

**Goal.** The one-command bootstrap in [06-deployment.md § Install](../arch/06-deployment.md#install). Replaces the `v3/devtools/bootstrap-certs.sh` + manual `.env` + manual compose-up sequence that the walking skeleton used.

**Exit criteria.** Fresh host with Docker ≥ 24 runs the `curl | bash` one-liner and lands at `https://host:8081/` login screen in under 5 minutes.

**What shipped:**

1. **`v3/install.sh`** ([v3/install.sh](../../install.sh)) — single self-contained ~660-line bash script. All templates (compose, `.env`, GPU overlay, udev rule) are inline heredocs, so `curl -fsSL .../v3/install.sh | bash` works on a host with no v3 checkout. Prereq check (`docker ≥ 24`, `compose v2`, `openssl ≥ 1.1.1`, `bash ≥ 4`, docker daemon reachable, optical-group warning), prefix creation (mode 0700 on `certs/`, 2775 setgid on `raw/media/logs/`), CA + per-service leaf generation, `.env` seed with random secrets, full compose rewrite per run, GPU overlay generation, host udev rule.
2. **Per-drive SCSI-generic auto-detect** — `ls /sys/class/block/sr<N>/device/scsi_generic/` per detected `/dev/sr*`. Drives without an sg node are skipped with a loud warning (silent-data-disc-fallback failure mode is worse than a missing service block). Threaded through `emit_ripper_block` so `devices: [/dev/srN, /dev/sgM]` is always paired correctly.
3. **Per-drive `UDISKS_AUTO=0` udev rule** — same `ID_PATH`-scoped logic that `setup-dev.sh:67-122` uses, lifted into `install.sh`. Full rewrite each run; gated on sudo (the cert/compose/env steps don't need root). If sudo isn't available the script prints the rule for manual install rather than silently skipping.
4. **Flags** — `--prefix <path>` (default `~/arm`), `--rotate-ca` (with confirmation prompt), `--start` (run `docker compose pull && docker compose up -d` after install). Plus `--certs-only / --no-env / --no-compose / --no-udev` for `setup-dev.sh` and unattended-install integration.
5. **Idempotent rerun** — `.env` preserved (only `PUID`/`PGID`/`CDROM_GID` re-derived); CA preserved unless `--rotate-ca`; leaves regenerated every run (cheap, self-heals stale/corrupted leaves, picks up new SANs); compose **fully rewritten** each run (clobbering hand-edits — call-out via `# Generated by install.sh — do not edit` header) from the union of (currently-detected drives) ∪ (drive names already in the existing compose). Previously-removed drives keep their service-block name in the file (stamped `sg-missing-sr<N>` so a `docker compose config` flags it).
6. **Generated compose: image-based, not build-based.** End users pull `${ARM_IMAGE_PREFIX}/arm-<svc>:${ARM_IMAGE_TAG}` (defaults `docker.io/automaticrippingmachine` and `v3.0.0-alpha-1`). Dev compose at [v3/docker-compose.yml](../../docker-compose.yml) keeps its `build:` blocks for developers. Two compose files describing the same stack — converging on the doc-spec at [06-deployment.md:80-153](../arch/06-deployment.md). Phase 14 (CI + image release) is the registry-availability dependency; the installer prints a "alpha tag — `docker compose pull` may 404" warning so this isn't surprising.
7. **GPU overlay** — `~/arm/docker-compose.gpu.yml` is generated alongside the base file; users with GPUs run `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` per the next-steps message. Same content as [v3/docker-compose.gpu.yml](../../docker-compose.gpu.yml) verbatim.
8. **`bootstrap-certs.sh` retired** — deleted from `v3/devtools/`. `setup-dev.sh:36-44` now invokes `install.sh --prefix "$V3_DIR" --certs-only --no-env --no-compose --no-udev` so cert-gen has one source of truth. `v3/devtools/README.md` and the Phase 5 compose-mount reference at [MASTER_IMPLEMENTATION_PLAN.md:135] updated to point at `install.sh`.
9. **shellcheck pre-commit hook** — `koalaman/shellcheck-precommit@v0.10.0` against `^v3/.+\.sh$`. Catches obvious bash bugs in `install.sh` and `setup-dev.sh` without running them. Both clean (one `SC2012` info-level suppression for a sysfs `ls` where `find` would be overkill).
10. **Verification:** five-row idempotency matrix (fresh install, rerun-preserves-env-and-CA, --rotate-ca, --certs-only mode, `docker compose config` validates) all green; `setup-dev.sh` regression smoke clean; shellcheck clean.

**Depends on:** Phase 7 (installer needs the full compose topology it's generating to be correct).

---

## Phase 14 — Supply chain + CI (shipped)

**Goal.** Every published image is pinned-by-digest, has a signed SBOM, and is rebuilt weekly for security updates.

**Exit criteria.** `cosign verify docker.io/<namespace>/arm-<service>:<tag>` succeeds with OIDC identity `https://token.actions.githubusercontent.com/<owner>/<repo>/.github/workflows/v3-release.yml@refs/tags/<tag>`. `syft` SBOM is attached to each image as a cosign attestation. Weekly scheduled rebuild runs and ships green. (`cosign verify` user-facing docs land at cutover per § Phase 16 — until the upstream namespace exists, the README points at the fork's namespace.)

**What shipped:**

1. **`.github/workflows/v3-ci.yml`** ([../../../.github/workflows/v3-ci.yml](../../../.github/workflows/v3-ci.yml)) — `paths: v3/**` scope so v2 PRs stay green via the existing v2 workflows. Seven parallel jobs: `lint-python` (ruff format-check, ruff lint, mypy on all 4 packages), `lint-ui` (eslint, prettier --check, vue-tsc), `lint-shell` (shellcheck on every `*.sh` under `v3/`), `test-python` (pytest covering all 3 service test dirs via the workspace `[tool.pytest.ini_options].testpaths`), `test-ui` (vitest), `openapi-drift` (live-import `arm_backend.main:app`, `app.openapi()`, `jq -S` diff against `services/ui/openapi.snapshot.json`), and `build-images` (matrix over backend/ripper/transcode/ui — Dockerfile sanity, no push, GHA cache scoped per service). Concurrency group cancels superseded runs per ref.
2. **`.github/workflows/v3-release.yml`** ([../../../.github/workflows/v3-release.yml](../../../.github/workflows/v3-release.yml)) — fires on `v3.*` tag push. Matrix over the 4 services. Each service: `docker/login-action` → `docker/metadata-action` (computes only `:<tag>`; `:latest` is no longer set here — it is owned by `publish-main.yml`, see item 8) → `docker/build-push-action` (push by digest, `provenance: true`) → `sigstore/cosign-installer@v3` → `anchore/sbom-action` (SPDX JSON) → `cosign sign --yes` (keyless, OIDC token from `id-token: write` permission) → `cosign attest --type spdxjson` (SBOM as in-toto attestation). Concurrency group does **not** cancel mid-publish. Workflow no-ops with a clear error if `vars.DOCKERHUB_NAMESPACE` / `secrets.DOCKERHUB_USERNAME` / `secrets.DOCKERHUB_TOKEN` are missing.
3. **`.github/workflows/v3-weekly-rebuild.yml`** ([../../../.github/workflows/v3-weekly-rebuild.yml](../../../.github/workflows/v3-weekly-rebuild.yml)) — `cron: '17 3 * * 0'` (Sundays 03:17 UTC) + `workflow_dispatch` with optional `tag` override. `resolve-tag` job finds the newest stable `v3.*` tag (excludes `-alpha`/`-rc`) and gates the rebuild on its existence; if no stable tag exists yet (current state) the job no-ops cleanly. `rebuild` job checks out that tag, builds with `no-cache: true` (the entire point — pull fresh base layers + apt indices), repushes the same tag, re-signs and re-attests SBOM (Sigstore accepts multiple sigs per image).
4. **`.github/dependabot.yml`** updated additively — v2 entries (root `pip` daily) untouched. New v3 entries: `uv` ecosystem on `/v3` (single workspace lock covers all Python deps), `npm` on `/v3/services/ui`, `docker` per service Dockerfile dir (4 entries), all on weekly cadence + grouped (`v3-python`, `v3-ui`) so PR volume stays bounded. Labelled `["v3", "dependencies"]` for filtering. The cutover PR (Phase 16) removes the v2 entries and rebases these to repo root.
5. **Configuration handoff to user** — workflows reference `secrets.DOCKERHUB_NAMESPACE` + `secrets.DOCKERHUB_{USERNAME,TOKEN}`. (Originally written as a `vars.` ref to keep the namespace visible in logs; the user added it as a secret on the fork, swapped accordingly. Cosmetic difference; cutover may revisit.) Drop-in cutover plan: fork ships under personal namespace; cutover commit flips the value to `automaticrippingmachine`. Cosign keyless needs no secrets (uses GHA OIDC token).
6. **Verification — exit criterion met live:**
   - **CI**: 10 jobs green on `wolfy/v3-improvments` push (run `25202069219`). Three first-push fixes folded in: pin `python-version: 3.14` in `setup-uv` (uv.lock requires it; runner default is 3.12); use `uvx --from "ruff==${RUFF_VERSION}"` rather than `uv run ruff` since ruff isn't in v3 dev-deps (matches the pre-commit pin); env `DATABASE_URL` not `POSTGRES_URL` for the openapi-drift job (matches `Settings` field name).
   - **Release**: tag `v3.0.0-alpha-2` published 4 signed images to `docker.io/shitwolfymakes/arm-{backend,ripper,transcode,ui}` in ~5 min (run `25269174343`). `cosign verify --certificate-identity=... --certificate-oidc-issuer=...` returned valid: "cosign claims validated · transparency log existence verified · code-signing cert verified."
   - **Pre-commit, shellcheck, mypy** all clean across the new workflow YAML + dependabot edits.
7. **Resolved — `:latest` ownership moved off releases.** Originally a cosmetic bug: despite `tags: type=raw,value=latest,enable=${{ !contains(github.ref_name, '-') }}` rendering as `enable=false` for `v3.0.0-alpha-2`, `docker/metadata-action@v5` published `:latest` anyway (same digest as the alpha tag). The fix was structural rather than the originally-proposed `flavor: latest=auto` + `type=semver`: `release.yml` no longer sets `:latest` at all (it publishes only the semver tag), so no tag push — pre-release or stable — can move it. `:latest` now tracks `main` HEAD and is owned solely by `publish-main.yml` (item 8).
8. **`.github/workflows/publish-main.yml`** (added post-cutover) — adopts the v2 rolling-`:latest` cadence on the v3 per-service topology. Builds, cosign-signs, and SBOM-attests all 4 service images on **every push to `main`** and **nightly** (`cron: '41 3 * * *'`), tagging `:latest` + `:main-<sha>`; the nightly run builds `no-cache` to pull fresh base layers + apt indices. `:latest` therefore tracks `main` HEAD — bleeding edge, **not** a support target (SECURITY.md supports only the newest stable `v3.*` tag). Division of labour: `publish-main.yml` owns `:latest`, `release.yml` owns the semver tags, `weekly-rebuild.yml` keeps the newest stable tag CVE-fresh. One workflow owns `:latest`, so nothing races to overwrite it.

**Depends on:** Phase 0 onward — CI tracks the critical path; setting it up has no phase dependency beyond "there is something to build."

**Cutover follow-ups (Phase 16):**

- Rename `.github/workflows/v3-*.yml` → `.github/workflows/*.yml` (drop prefix); strip `paths: v3/**` filter; rename `branches: [main, 'wolfy/**']` → `[main]`.
- Flip `vars.DOCKERHUB_NAMESPACE` from fork value to `automaticrippingmachine`.
- Remove v2 dependabot entries; rebase v3 entries from `/v3/...` → `/...`.
- Delete v2 workflow files (per [08-v2-isolation-and-cutover.md § Cutover step 5](../arch/08-v2-isolation-and-cutover.md#5-retire-v2-ci-workflows)).
- Add `cosign verify ...` block to README.md.

---

## Phase 15 — Integration rig + full exit criteria (partial — see status below)

**Goal.** Big Buck Bunny ISO end-to-end rip + transcode on a developer's machine, plus the crash-recovery exercise, plus one real BD/DVD/CD rip done on a contributor's machine.

**Exit criteria.** Every checkbox in [08-v2-isolation-and-cutover.md § Readiness criteria](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover) is ticked.

**What shipped:**

1. **Crash drill — `devtools/crash-drill.sh`** ([../../devtools/crash-drill.sh](../../devtools/crash-drill.sh)) — bash drill that injects a synthetic `ripping` job + `in_progress` track via psql, force-kills `armv3-backend` (`docker kill -s KILL`), brings it back via `docker compose up -d`, and asserts the lifespan-startup sweep flipped the track to `queued`/`attempts=1` and stamped `resumed_from_crash=true`. Idempotent cleanup via `trap EXIT`. Prompts before destructive action; `--yes` skips. Drill **passed live** against the dev stack on first proper run.
2. **OpenAPI snapshot regen — `devtools/regen-openapi-snapshot.sh`** ([../../devtools/regen-openapi-snapshot.sh](../../devtools/regen-openapi-snapshot.sh)) — formalizes the path the CI `openapi-drift` job's failure message points at. Imports `arm_backend.main:app`, dumps `app.openapi()` to `services/ui/openapi.snapshot.json`, then `npm run openapi-types` if the UI's `node_modules` is present. Smoke-tested clean (no diff → snapshot already current).
3. **Real-disc smoke checklist — `docs/contributors/real-disc-smoke.md`** ([../contributors/real-disc-smoke.md](../contributors/real-disc-smoke.md)) — host prep, fresh-install vs dev-stack run paths, what to verify (detection / identification / rip / transcode / terminal status / logs zip), what to capture for the PR, known gotchas (MakeMKV beta key rotation, copy-protected discs, slow MusicBrainz, lazy transcode-image pull), and the BD/DVD/CD results table that gates cutover.
4. **Contract test surface** — OpenAPI drift detection ships in `v3-ci.yml` (Phase 14) as the `openapi-drift` job; the regen helper above closes the loop. The "Contract test suite" deliverable per the original plan is largely covered by this drift check plus the existing pytest in `services/backend/tests/` (which exercises router shapes via `TestClient`); a separate framework was not added.

**Validated end-to-end on this dev stack:**

- DVD rip path — **proven 4×** against Sintel DVD: 5 video tracks each, all `done`, ~3.4 GB raw output per rip (`v3/raw/job_*/title_t0[0-4].mkv`). Disc identification (OMDB) populates `title='Sintel' year=2010` cleanly.

**Outstanding (gates cutover):**

- **BBB ISO rig (`devtools/arm-test-rip`)** — **deferred to v3.1**. The plan envisioned mounting BBB.iso as a loop device into a ripper container, but `read_drive_status` does a SCSI ioctl that fails on `/dev/loop*`. A clean fix is a small ripper code change: `--manual-trigger /path/to/iso.iso` mode that bypasses the poll loop and calls `JobController.handle_disc_inserted` directly. Tracked at [07-open-questions.md](../arch/07-open-questions.md) as a v3.1 follow-up. **Cutover impact:** the readiness criterion at [08-v2-isolation-and-cutover.md § Readiness](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover) line 200 ("produces a transcoded file using the Big Buck Bunny ISO fixture") needs to be revisited or fulfilled by a real-DVD substitute.
- **BD + CD smoke** — neither has been executed on this dev stack. Sintel covers the DVD column of the smoke matrix; a Blu-ray and an audio CD still need a real rip on a contributor's machine.
- **Transcode-against-real-rip end-to-end** — `transcode_tasks` table is empty across all 4 successful Sintel rips; no `session_applications` were ever created for them. The dispatcher → ephemeral transcoder → media-output path has unit-test coverage but no integration evidence against a real ripped tree. To validate: apply a session to one of the existing `ripped` jobs via `POST /api/jobs/{job_id}/transcode` (UI form) and watch a transcoder spawn.

**Depends on:** Phases 3, 7, 9.

---

## Phase 15.5 — Ripper single-invocation reversion (shipped)

**Goal.** Stop the recurring drive-stability failures that surfaced during Phase-12-era live rips on the LG BP50NB40 USB Blu-ray drive.

**The problem.** Phase 3's rip pipeline ran one `makemkvcon mkv title=N` invocation per title in a Python loop ([dispatcher.py § per-title loop, before this phase](../../services/ripper/arm_ripper/rip/dispatcher.py)). Between titles the drive briefly idled — kernel autosuspend would drop the device node, then the medium would report SCSI `NOT_READY` (`LOGICAL UNIT IS IN PROCESS OF BECOMING READY`) for another 30–60s. Four production rips over ~a week ended in partial failures or hangs. Each subsequent fix shipped (a between-titles wait + `CDROM_DRIVE_STATUS` ioctl + a `verify_read=True` real-block read probe) was a bandaid on a symptom — the gap itself.

**v2 never had this failure mode** because [arm/ripper/main/makemkv.py:103-106](../../../arm/ripper/main/makemkv.py#L103) shells out exactly once per disc — `makemkvcon mkv ... dev:{job.devpath} all {rawpath} --minlength={MINLENGTH}` — and the drive stays open from first byte to last.

**What shipped:**

1. **`makemkv_rip.rip_disc`** replaces `rip_title`. One `makemkvcon mkv ... all <outdir>` invocation per disc. The robot stream is parsed for per-title attribution: PRGT `Saving title #N` transitions current_title and fires `on_title_start`; PRGV gives fractional progress; MSG:5003 captures per-title failures with reasons; post-exit the output dir is walked for `title_tNN.mkv` files to confirm successful saves.
2. **Dispatcher rewrite.** `rip_all` for DVD/BD now calls `rip_disc` once and fans the lifecycle hooks (`on_track_start` / `on_track_done` / `on_track_progress`) out from the rip-side stream events through a `source_ref → TrackView` lookup. Tracks the user selected but MakeMKV skipped (below `--minlength`) get FAILED with a clear reason rather than silently disappearing.
3. **Drive-readiness machinery deleted.** `_wait_for_drive_ready`, `_is_rip_ready`, `DRIVE_READY_*` constants, and the `verify_read=True` block in `drive_status.py` (along with `_NOT_READY_READ_ERRNOS`) are gone. `probe_drive_media` is now a pure ioctl probe — still used by the heartbeat task and the manual-trigger pre-check, neither of which needs the read-verify.
4. **MINLENGTH baseline + Session override.** New ripper env var `ARM_MIN_LENGTH_SECONDS` (default 600 — matches v2). Backend's `rip_start` resolves `Session.overrides_json["min_length_seconds"]` (when the job has a `pending_session_id`) and threads it through `RipStartResponse.min_length_seconds`; the ripper falls back to its env baseline when the field is None. No schema change — `Session.overrides_json` is already JSONB.
5. **Tests.** 12 dispatcher tests rewritten for the single-invocation flow; 9 new parser tests covering `MSG:5018` / `MSG:5003` / `parse_msg_args` / per-title attribution; 6 new `rip_disc` integration tests against a fake makemkvcon binary that streams a canned robot trace; 9 backend tests for the `_resolve_min_length_override` path. All 69 ripper + 305 backend tests pass.

**The deliberate tradeoff.** One long blocking rip + log-parsing burden, in exchange for never seeing the between-titles failure mode again. **No per-title rip capability remains** — even MAIN_FEATURE rips go through `mkv all` filtered by `--minlength`. TRACKS-mode rips of a few titles waste IO ripping unselected ones (deleted post-rip), but the drive stays open and stable. The dev-box LG BP50NB40 was the catalyst; other USB-BD drives reportedly behave similarly.

**Memory.** [.claude/memory/feedback_ripper_no_per_title.md](../../../.claude/memory/feedback_ripper_no_per_title.md) captures the rationale so the next contributor doesn't re-introduce per-title invocations without the context.

**Depends on:** Phase 3 (rip pipeline shape), Phase 12 (heartbeat + manual-trigger pre-check, both untouched).

---

## Phase 16 — Cutover PR

Mechanical. Follows [08-v2-isolation-and-cutover.md § The cutover PR](../arch/08-v2-isolation-and-cutover.md#the-cutover-pr) step-for-step. Not a design phase.

**Depends on:** Phase 15 (all readiness criteria met).

---

## Parallel tracks

These can proceed alongside the critical path once their entry condition is met. None blocks a phase directly, but all must land before Phase 16.

### Track A — Documentation polish
- Entry: Phase 0.
- Content: README user-facing rewrite (lands in cutover), per-service README.md, ADRs for deferred OQs as they resolve.

### Track B — Observability beyond logs (deferred v3.0)
- Entry: Phase 12.
- Explicitly not shipping in v3.0 per [05-cross-cutting.md § Observability](../arch/05-cross-cutting.md#observability-beyond-logs). Keep the track here so it's not forgotten — add to v3.1 backlog.

### Track C — Platform matrix verification
- Entry: Phase 13 (installer exists).
- Manual smoke on Unraid, Synology, stock Docker on each supported Linux distro. Document results in a per-platform appendix to [06-deployment.md](../arch/06-deployment.md).

### Track D — Community DB plumbing
- Entry: Phase 2.
- `disc_fingerprint` / `aacs_disc_id` columns exist from Phase 0. Populating them is out of scope for v3.0 but the schema is ready. Track is a forward-compat checkpoint, not a v3.0 deliverable.

---

## Dependency graph (critical path, summarized)

```
Phase 0 ─▶ Phase 1 ─┬─▶ Phase 2 ─▶ Phase 3 ─┬─▶ Phase 4 ─┬─▶ Phase 5 ─┬─▶ Phase 6 ─▶ Phase 7 ─┬─▶ Phase 7b
                    │                        │            │             │                     ├─▶ Phase 8
                    │                        │            │             │                     ├─▶ Phase 9
                    │                        │            │             │                     ├─▶ Phase 10
                    │                        │            │             │                     └─▶ Phase 11
                    │                        │            └──────────── Phase 12
                    │                        └──▶ (WS replaces REST-poll fallback in Phase 2)
                    │
                    └─▶ Phase 14 (CI — runs alongside every phase)
                                                                                                ─▶ Phase 13 ─▶ Phase 15 ─▶ Phase 16
```

Key realizations from this graph:
- **Phase 3 unblocks everything downstream** — every later phase either needs a ripped job to demo against or runs in parallel to rip work.
- **Phase 7 is the second pivot** — transcode enables Phases 8, 9, 10 all at once.
- **Phase 14 (CI) has no dependency** and should be set up as early as Phase 1 delivers a real schema, not left until the end.

---

## Open risks to this plan

- **OQ-1 (queue mechanism) stays deferred.** The plan assumes DB-as-queue throughout. If a bottleneck appears during Phase 7 testing, the state machine is designed to swap in Redis/RQ/NATS without reshaping services — but a pivot would still insert a Phase 7.5.
- **MakeMKV licensing** may block CI (noted in [05-cross-cutting.md § Integration rig](../arch/05-cross-cutting.md#integration-rig--big-buck-bunny)). Phase 15 plans a loopback `dd`-based stub as fallback; verify early.
- **Transcode container startup latency** may make the "ephemeral one-per-task" model feel sluggish. If measured startup > ~3s per task becomes a problem, a long-running transcode worker with a task-per-invocation contract is the escape hatch — same state machine, different container lifetime.
- **Browser-facing TLS UX.** Every LAN client needs to trust `arm-ca.crt` once or click through a warning forever. Phase 13 installer should print the import instructions prominently; otherwise the first-run UX degrades.
