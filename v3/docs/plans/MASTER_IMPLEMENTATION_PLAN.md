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
- [packages/arm_common/](../../packages/arm_common/) has enums (`DriveStatus`, `JobStatus`, `DiscType`), ULID helper, and the two ripper schemas (`RegisterRequest/Response`, `IdentifyRequest/Response`).

**Not delivered:** every other table, real disc identification, MakeMKV invocation, WebSocket hub, UI, transcode, auth, notifications, installer, supply-chain hygiene. Roughly **5%** of the target architecture.

---

## Phase 1 — Data model completion

**Goal.** Every entity the architecture describes exists in the DB, with the relationships enforced at the schema layer. No behavior wired up yet — this is runway for Phases 2–7.

**Exit criteria.** `\dt` in `armv3-db` shows every table listed in [04-data-model.md](../arch/04-data-model.md). Seeded built-in rip presets, transcode presets, and sessions are present after a fresh migration. SQLModel classes in `arm_common` match the migrations 1:1.

**Deliverables:**
1. SQLModel adoption — port the current SQLAlchemy-only `Drive`/`Job` models to SQLModel so they double as Pydantic schemas. ([04-data-model.md § Schema definition and migrations](../arch/04-data-model.md#schema-definition-and-migrations))
2. Add `users`, `config`, `events` tables + migration.
3. Add `tracks`, `rip_presets`, `transcode_presets`, `sessions`, `session_applications`, `transcode_tasks`, `gpus` tables + migration(s).
4. Postgres enum types for every status/mode column (not CHECK constraints).
5. Partial unique index on `transcode_tasks(output_path) WHERE status IN ('queued','in_progress','done')`.
6. First-boot seeders: default admin user (random password logged to stdout + `/logs/first-boot.log`), `config` singleton row, built-in presets and sessions (`is_builtin=true`).

**Depends on:** Phase 0.

---

## Phase 2 — Real disc identification

**Goal.** An inserted disc is scanned, identified against external metadata, and produces either an `identified` or `awaiting_user_id` job. No ripping yet.

**Exit criteria.** Inserting a real DVD/BD/CD transitions its job through `created → identified` (on lookup hit) or `created → awaiting_user_id` (on miss, with `config.block_on_miss=true`). `metadata_json` is populated with the lookup result. Disc fingerprint columns stay null in v3.0 but the scaffolding exists.

**Deliverables:**
1. **Ripper:** MakeMKV scan wrapper (`makemkvcon -r info`) for DVD/BD; MusicBrainz Disc ID probe for CD; data-disc fallback. Surface volume label + per-title durations in `scan_result`. Install MakeMKV/libdvdcss/abcde in `services/ripper/Dockerfile`.
2. **Backend adapters:** `TMDBClient`, `OMDBClient`, `MusicBrainzClient` — plain `httpx.AsyncClient` with keys read from `config` row. Outbound HTTPS verified via the merged trust store ([05-cross-cutting.md § Transport (TLS)](../arch/05-cross-cutting.md#transport-tls)).
3. **Backend state machine:** the inline identify handler upgrades from "always return `CREATED`" to running the lookup, persisting `title`/`year`/`metadata_json`, and returning `identified` or `needs_user_input`. Ripper blocks on this call with a generous timeout.
4. **Ripper command channel (REST-polling fallback).** The WS hub doesn't exist yet; for now a ripper parked in `awaiting_user_id` polls `GET /api/ripper/jobs/{job_id}` every few seconds to pick up UI-supplied resolution. Replaced by WS in Phase 4.
5. **`POST /api/jobs/{job_id}/resolve`** UI-side endpoint (UI consumer still stubbed — curl-testable).

**Depends on:** Phase 1.

---

## Phase 3 — Rip pipeline (MVP end-to-end)

**Goal.** From disc insertion to `/raw/<job_id>/title_tNN.mkv` on disk, with the job in `ripped` state. This is the **"bits first" MVP** and the first real demo.

**Exit criteria.** Identified DVD rips to `/raw/<job_id>/`, all tracks transition `queued → in_progress → done`, job transitions `identified → ripping → ripped`. CD equivalent via abcde. No UI yet — verified by `psql` and `ls /raw/`.

**Deliverables:**
1. **`POST /api/ripper/jobs/{job_id}/tracks`** — ripper creates track rows from the MakeMKV scan.
2. **Ripper rip loop:** shell out `makemkvcon mkv --robot` per selected title; parse progress; write to `/raw/<job_id>/`. Sequential per-job (no parallelism within one drive).
3. **`PATCH /api/ripper/tracks/{track_id}/complete`** + **`/fail`** + **`POST /api/ripper/jobs/{job_id}/complete`** — wire each state transition. Retry with exponential backoff ([02-job-lifecycle.md § What this buys us](../arch/02-job-lifecycle.md#what-this-buys-us)).
4. **Track-selection rules** (initial): respect `rip_presets.track_selection = main_feature | all_tracks | archive`. `custom` deferred to Phase 6.
5. **Eject on completion**, resume polling (`ioctl(CDROM_DRIVE_STATUS)`).
6. **Auth scoping:** Backend verifies the caller's registered hostname owns the drive that owns the job ([05-cross-cutting.md § Authorization rules](../arch/05-cross-cutting.md#authorization-rules)).
7. **CD path:** abcde wrapper writing WAV/FLAC to `/raw/<job_id>/`.

**Depends on:** Phase 1 (`tracks`, `rip_presets`), Phase 2 (a job is identified before rip begins, except under placeholder mode — deferred).

---

## Phase 4 — WebSocket hub

**Goal.** Live progress streams from rippers to Backend to any subscriber. Command channel delivers identify-resolution events to parked rippers (replaces the REST-polling fallback).

**Exit criteria.** A test client connecting to `wss://arm-backend:8443/ws` with a valid service token can subscribe to `ripper.progress.{job_id}` and see progress ticks during a rip. `ripper.commands.{drive_id}` delivers `identify.resolved` to the correct ripper. Principal-to-topic authorization rejects cross-drive subscriptions.

**Deliverables:**
1. `/ws` endpoint with first-message auth, origin allowlist (`ARM_ALLOWED_ORIGINS` from `.env`), 5s unauth timeout, topic-subscription gating ([05-cross-cutting.md § WebSocket security](../arch/05-cross-cutting.md#websocket-security)).
2. **Fan-out hub** (in-memory subscriber table) supporting the topics enumerated in [03-protocol.md § WebSocket channels](../arch/03-protocol.md#websocket-channels).
3. **Ripper WS producer** for `ripper.progress.{job_id}` — ticks parsed from `makemkvcon --robot` output.
4. **Ripper WS consumer** for `ripper.commands.{drive_id}` — replaces the REST poll in Phase 2.
5. **`events` persistence.** Every typed event that hits the WS also appends to the `events` table with the standard envelope.

**Depends on:** Phase 3 (there's something to stream progress *about*).

---

## Phase 5 — User auth + UI walking skeleton

**Goal.** Browser lands at a login screen, admin authenticates with a one-time password printed at first boot, sees a jobs list rendered from REST. No WS in UI yet. No transcode yet.

**Exit criteria.** `https://host:8081/` → login → forced password change → jobs list that auto-updates every N seconds via REST polling. Built-in sessions visible (read-only UI). JWTs signed with `config.session_signing_key`.

**Deliverables:**
1. **Framework decision** (resolves [07-open-questions.md OQ-2](../arch/07-open-questions.md#oq-2-frontend-framework--vue-vs-react)). Scaffold `services/ui/` with Vite, nginx Dockerfile, OpenAPI client generation from the Backend spec.
2. **Auth endpoints:** `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/password`, argon2id hasher wrapper in `arm_common`, `session_signing_key` auto-generation on first Backend boot.
3. **UI JWT principal plumbing** — REST middleware that routes a `Bearer` header to either the service token or UI JWT and enforces the split rules in [05-cross-cutting.md § Authorization rules](../arch/05-cross-cutting.md#authorization-rules).
4. **UI pages (MVP):** Login, Force-Change-Password, Jobs List, Job Detail (static — tracks + metadata from `GET /api/jobs/{id}`), Drives list, Config form, Sessions list (read-only).
5. **nginx reverse proxy** (`/api/*`, `/ws/*`) with TLS-everywhere, internal CA trust, external leaf cert served to the browser.
6. **Log level toggle** on a Diagnostics page (surfaces `ARM_LOG_LEVEL` per service — restart-to-change; no live mutation).

**Depends on:** Phase 1 (`users`, `config`), Phase 3 (jobs exist and have completed at least one state machine lap).

---

## Phase 6 — Sessions & session applications

**Goal.** The CRUD layer for user-authored sessions. Creating a session application against a ripped job produces `transcode_tasks` rows in `queued` state — but nothing transcodes them yet (Phase 7).

**Exit criteria.** A user can clone a built-in session, tweak it, apply it to a ripped job via `POST /api/jobs/{job_id}/transcode`, and see the resulting `session_applications` + `transcode_tasks` rows. Path-template validation rejects templates that produce empty required tokens. Cross-session and cross-job collisions surface the dialog described in [02-job-lifecycle.md § Concurrent write safety](../arch/02-job-lifecycle.md#concurrent-write-safety).

**Deliverables:**
1. **REST:** `GET/POST/PATCH/DELETE /api/sessions`, `GET /api/transcodes`, `DELETE /api/transcodes/{id}` (queue only — running cancel lands in Phase 7).
2. **Path-template expansion + validation** at save time against a synthetic job of the session's `media_type`.
3. **Apply-time fan-out.** Resolve every output path, check for cross-session and cross-job collisions (`SELECT` against `transcode_tasks.output_path` in live states + filesystem check). Surface the overwrite dialog on the UI side; set `session_applications.overwrite=true` when confirmed.
4. **Idempotency** for `POST /api/jobs/{job_id}/transcode` — re-applying the same session to the same job returns the existing `session_application`.
5. **UI "New Session" wizard** prefilled from built-ins; rip-preset + transcode-preset dropdowns filtered by the session's `media_type`.
6. **`custom` rip-preset support** — the `track_filters_json` declarative rules the MVP track selector skipped in Phase 3.

**Depends on:** Phase 1 (every session-related table), Phase 3 (applying against real ripped jobs), Phase 5 (UI to drive it).

---

## Phase 7 — Transcode container (ephemeral, per-task)

**Goal.** Backend dequeues `transcode_tasks` and spawns `arm-transcode-<uuid>` containers via the Docker socket. Each container transcodes one raw into one output under `/media/`. Full rip→transcode flow completes end-to-end.

**Exit criteria.** Applying a "Plex 1080p H.265" session to a ripped movie produces a file at `/media/Movies/{Title} ({Year})/{Title} ({Year}) - plex-1080p-h265.mkv`. Task goes `queued → in_progress → done`. `.arm-inprogress` atomic-rename flow verified by killing a transcoder mid-run. CPU-only path only — GPU in a sub-phase.

**Deliverables:**
1. **`services/transcode/` real image** — `python:3.14-slim-bookworm` + HandBrakeCLI + ffmpeg + abcde. `docker-entrypoint.sh` CA merge + PUID drop + tini.
2. **Backend spawn logic** — docker-py, mounts (`/raw` ro, `/media` rw, certs, logs), env (`ARM_TRANSCODE_TASK_ID`, `ARM_BACKEND_URL`, `ARM_SERVICE_TOKEN`). Queue dequeuer uses `SELECT … FOR UPDATE SKIP LOCKED`.
3. **Transcode endpoints:** `/api/transcoder/register`, `/claim`, `/heartbeat` (30s), `/complete`, `/fail`.
4. **Atomic rename** — write to `<final>.arm-inprogress`, `fsync`, `rename(2)`.
5. **Crash sweep for `.arm-inprogress`** — on transcoder startup, delete orphans under `/media` whose task row isn't `in_progress`.
6. **WS progress topic** `transcode.progress.{task_id}` and events (`session.started`, `task.completed`, etc.).
7. **UI:** transcode progress bars per task; running-transcode cancel (kills container, marks task failed).
8. **Stale-claim sweep** — Backend background task marks tasks `stale → queued` when heartbeat lapses.

**Depends on:** Phase 6 (queued tasks exist), Phase 4 (progress WS).

### Phase 7b — GPU transcoding

Split out so CPU-only can ship first.

1. **GPU probe at Backend startup** — VAAPI via `/dev/dri/renderD*`, NVENC via `nvidia-smi`, QSV via MediaSDK. Populate `gpus` table (truncate-and-fill). Emit `transcode.hw_unavailable` on empty.
2. **Spawn injects `ARM_GPU_DEVICE`** or nvidia runtime flags. Claim-and-release via `SELECT … FOR UPDATE SKIP LOCKED` on the `gpus` row.
3. **`hw_preference` respected** in dispatch — `NULL`/`cpu_only`/`any` semantics.

---

## Phase 8 — Auto-session / default_session_id

**Goal.** `drives.default_session_id` + `config.auto_transcode_on_idle=true` causes each successful rip to auto-queue its default session.

**Exit criteria.** Inserting a disc into a drive with a default session produces a completed `/media/` file with zero UI interaction.

**Deliverables:**
1. **Backend hook on `rip.completed`** — if drive has `default_session_id` and auto-transcode is enabled, create a `session_application` identical to the manual path.
2. **UI:** per-drive "Default Session" dropdown on the Drives page.
3. **Event coverage:** `session.queued` with `source: auto|manual` in the payload.

**Depends on:** Phase 7.

---

## Phase 9 — Crash recovery

**Goal.** The top-2 pain point that motivated v3 ([00-vision.md](../arch/00-vision.md)). Five queued rips + simulated power cut mid-batch resumes cleanly.

**Exit criteria.** The integration exercise in the cutover readiness criteria passes. `resumed_from_crash` badge appears in UI until the next terminal state.

**Deliverables:**
1. **Backend-startup sweep** — before serving traffic, find every `jobs.status='ripping'`, reset all tracks to `queued`, increment `attempts`, set `resumed_from_crash=true`, instruct rippers to wipe `/raw/<job_id>/`.
2. **Ripper-startup probe** — on boot, poll `ioctl`, and if a disc is present call `POST /api/ripper/jobs/{job_id}/resume` for any in-flight job on this drive. Backend performs the same reset.
3. **`/raw/<job_id>/` wipe** on both paths before re-rip.
4. **Transcode stale-claim sweep** — already landed in Phase 7; confirm end-to-end.
5. **UI banner** "resumed from crash" on affected jobs.

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

## Phase 11 — Notifications

**Goal.** Apprise dispatcher consumes typed events and fires outbound webhooks.

**Exit criteria.** Adding an Apprise URL (`discord://...`, `mailto://...`, etc.) in the UI causes `rip.completed`, `rip.failed`, `session.completed` events to trigger notifications end-to-end.

**Deliverables:**
1. **`NotificationDispatcher` interface** + `AppriseDispatcher` implementation; iterates `config.notification_apprise_urls` on each event.
2. **UI textarea** for Apprise URLs with validation on save.
3. **Event payload shapes** frozen for the events we actually emit (new events welcome; existing ones never change shape — [03-protocol.md § Versioning](../arch/03-protocol.md#versioning)).
4. **Redacting logger** — `config` row reads never log URLs / API keys.

**Depends on:** Phase 4 (events persist).

---

## Phase 12 — Logs persistence + per-job log view

**Goal.** Every service's JSONL log is queryable by `job_id`; UI per-job view shows correlated lines; bug-report zip endpoint works.

**Exit criteria.** `GET /api/logs/{job_id}.zip` returns a zip containing the per-job slice of every service log. UI log viewer live-tails via `logs.{job_id}` WS topic.

**Deliverables:**
1. **Structured logging helpers** in `arm_common` — shape from [05-cross-cutting.md § Logging](../arch/05-cross-cutting.md#logging). Enforced via a lint rule or test.
2. **Per-service log files** at `/logs/<service>.log` with size-based rotation (10MB × 5).
3. **Backend log-query** — grep across `/logs/*.log` for `job_id`; streaming response.
4. **WS `logs.{job_id}` topic** via file-tail.
5. **Zip endpoint** + UI download button on job detail page.

**Depends on:** Phase 4 (WS hub), Phase 5 (UI).

---

## Phase 13 — Installer (install.sh)

**Goal.** The one-command bootstrap in [06-deployment.md § Install](../arch/06-deployment.md#install). Replaces the `v3/devtools/bootstrap-certs.sh` + manual `.env` + manual compose-up sequence that the walking skeleton uses today.

**Exit criteria.** Fresh host with Docker ≥ 24 runs the `curl | bash` one-liner and lands at `https://host:8081/` login screen in under 5 minutes.

**Deliverables:**
1. **`v3/install.sh`** — prereq check, prefix creation, CA generation (EC P-384, 10y), drive probe, leaf cert generation, `.env` seed, compose generation from template with one ripper block per detected drive.
2. **`--rotate-ca`, `--prefix`, `--start`** flags.
3. **Idempotent rerun** — preserves `.env` and CA, appends new drive blocks, regenerates leaves.
4. **Retire `v3/devtools/bootstrap-certs.sh`** (the skeleton scaffolding) or fold its logic into `install.sh`.

**Depends on:** Phase 7 (installer needs the full compose topology it's generating to be correct).

---

## Phase 14 — Supply chain + CI

**Goal.** Every published image is pinned-by-digest, has a signed SBOM, and is rebuilt weekly for security updates.

**Exit criteria.** `cosign verify docker.io/automaticrippingmachine/arm-<service>:v3.0.0` succeeds with OIDC identity `https://token.actions.githubusercontent.com`. `syft` SBOM is attached to each image. Weekly scheduled rebuild runs and ships green.

**Deliverables:**
1. **`.github/workflows/v3-ci.yml`** — builds, per-service pytest, contract tests, lint. `paths: v3/**` filter so v2 CI stays untouched ([08-v2-isolation-and-cutover.md § CI](../arch/08-v2-isolation-and-cutover.md#ci)).
2. **`.github/workflows/v3-release.yml`** — tagged build, cosign keyless signing, syft SBOM, cosign-attach-sbom, push.
3. **`.github/workflows/v3-weekly-rebuild.yml`** — scheduled weekly on `main` tag; pushes image with same tag.
4. **Renovate / Dependabot config** pinned to base digests.
5. **`cosign verify` documented in `README.md`** (lands in Phase 16).

**Depends on:** Phase 0 onward — CI tracks the critical path; setting it up has no phase dependency beyond "there is something to build."

---

## Phase 15 — Integration rig + full exit criteria

**Goal.** Big Buck Bunny ISO end-to-end rip + transcode on a developer's machine, plus the crash-recovery exercise, plus one real BD/DVD/CD rip done on a contributor's machine.

**Exit criteria.** Every checkbox in [08-v2-isolation-and-cutover.md § Readiness criteria](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover) is ticked.

**Deliverables:**
1. **`devtools/arm-test-rip`** — mounts BBB ISO as a loop device in a disposable ripper container; asserts `/raw/<job_id>/` layout + metadata.
2. **Contract test suite** — OpenAPI published from Backend vs `arm_common.schemas` on every PR.
3. **Crash drill** — scripted "kill -9 arm-backend mid-rip-batch; docker compose up -d; assert recovery."
4. **Real-disc smoke doc** — checklist for contributors running a physical BD/DVD/CD rip before cutover.

**Depends on:** Phases 3, 7, 9.

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
- **OQ-2 (frontend framework) blocks Phase 5.** Not a technical blocker but a contributor-recruiting one. Decide before starting Phase 5; if no lead steps up, pick one arbitrarily and move on rather than let Phase 5 stall everything downstream.
- **MakeMKV licensing** may block CI (noted in [05-cross-cutting.md § Integration rig](../arch/05-cross-cutting.md#integration-rig--big-buck-bunny)). Phase 15 plans a loopback `dd`-based stub as fallback; verify early.
- **Transcode container startup latency** may make the "ephemeral one-per-task" model feel sluggish. If measured startup > ~3s per task becomes a problem, a long-running transcode worker with a task-per-invocation contract is the escape hatch — same state machine, different container lifetime.
- **Browser-facing TLS UX.** Every LAN client needs to trust `arm-ca.crt` once or click through a warning forever. Phase 13 installer should print the import instructions prominently; otherwise the first-run UX degrades.
