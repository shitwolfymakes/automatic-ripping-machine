# 03 — Protocol: REST + WebSocket Contract

Services communicate over two transports, and only two:

- **REST (HTTP/1.1, JSON bodies)** for request/response: config fetches, state transitions, blocking lookups, CRUD. HTTP/1.1 is sufficient — the call volume between services is low (config fetch, state transition, complete) and the multiplexing/header-compression wins of HTTP/2 don't pay for the operational complexity at this scale.
- **WebSocket** for streaming: live progress, events, and async push from Backend to UI.

Everything else (direct DB access between services, file-based IPC, shared memory) is explicitly out of scope. Workers never read other workers' state.

All schemas are defined as Pydantic models in `packages/arm_common/schemas/` and exported as OpenAPI from the Backend at `/api/openapi.json`. Both sides (Backend as producer, Ripper/UI as consumers) import from the same package. Contract tests (see [05-cross-cutting.md](05-cross-cutting.md)) assert that the published OpenAPI matches the consumers' expectations.

## Base URLs

- Backend listens on port `8443` inside its container (TLS only; there is no plaintext port).
- UI's nginx proxies `/api/*` and `/ws/*` to `https://arm-backend:8443`.
- Rippers and Transcoders reach Backend at `https://arm-backend:8443` on the compose network, verifying the server cert against the internal CA mounted at `/etc/ssl/certs/arm-ca.pem`. See [05-cross-cutting.md § Transport (TLS)](05-cross-cutting.md#transport-tls).

## Authentication between services

Internal services (Ripper, Transcode) authenticate with a **shared service token** passed as `Authorization: Bearer <token>`. The token is generated once at install time (`openssl rand -hex 32`), stored in `~/arm/.env`, and injected into Backend, Ripper, and Transcode containers via Compose as `ARM_SERVICE_TOKEN`. Every container reads it from its own environment; there is no DB copy.

The UI authenticates as a logged-in user with a JWT in `Authorization: Bearer <jwt>` on REST and via a first-message `{"op": "auth", "token": "<jwt>"}` handshake on WS. See [05-cross-cutting.md](05-cross-cutting.md) for the full auth model.

## REST API surface

### Ripper ↔ Backend

All ripper routes are under `/api/ripper/`. The Ripper is the client.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/ripper/register` | Ripper startup handshake. Body: `{hostname, device_path, ripper_version, hw_caps}`. Response: `{drive_id, drive_config, service_token_verified}`. |
| `GET` | `/api/ripper/drives/{drive_id}/config` | Fetch rip parameters for this drive (MakeMKV flags, DVD decrypt settings, default rip profile). |
| `POST` | `/api/ripper/identify` | Identify a disc. Body: `{drive_id, disc_type, volume_label, scan_result}` (scan_result is the MakeMKV scan output for DVD/BD, the MusicBrainz Disc ID for CD). Response: `{job_id, status: "identified"}` with metadata, or `{job_id, status: "needs_user_input"}`. This call **blocks** on the server side while external lookup runs (with a generous timeout). |
| `GET` | `/api/ripper/jobs/{job_id}` | Poll job status (rarely needed; WS is preferred). |
| `POST` | `/api/ripper/jobs/{job_id}/tracks` | Create track rows after identification succeeds. Body: list of track specs. |
| `POST` | `/api/ripper/jobs/{job_id}/resume` | Ripper-initiated on container startup when its drive has an in-flight job in `status='ripping'`. Backend marks `resumed_from_crash=true`, resets every track for the job to `queued`, and increments each track's `attempts`. Ripper then wipes `/raw/<job_id>/` and re-runs MakeMKV from scratch — no per-track resume. See [02-job-lifecycle.md § Crash recovery](02-job-lifecycle.md#crash-recovery-restart-the-rip-from-scratch). |
| `PATCH` | `/api/ripper/tracks/{track_id}/complete` | Mark track done. Body: `{output_path, sha256, size_bytes, duration_seconds}`. |
| `PATCH` | `/api/ripper/tracks/{track_id}/fail` | Mark track failed. Body: `{error_code, error_message, retriable}`. |
| `POST` | `/api/ripper/jobs/{job_id}/complete` | All tracks terminal; mark job done. |

There is no ripper heartbeat endpoint. Live progress streams over WS (see "WebSocket channels" below); crash detection happens at container-restart time, not via timeout. State-transition calls (`complete`, `fail`, `complete-job`) retry until acknowledged.

### UI ↔ Backend

All UI routes are under `/api/`. The UI is the client; a logged-in admin is the authenticated principal.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | Body: `{username, password}`. Response: `{access_token, expires_at}`. HS256 JWT signed with `config.session_signing_key`. |
| `POST` | `/api/auth/logout` | No-op server-side in v3.0 (JWTs are not tracked). Present for API symmetry; the client discards the token. |
| `POST` | `/api/auth/password` | Change password. Required before anything else on first login. |
| `GET` | `/api/config` | Read app config (API keys, retention, etc.). |
| `PATCH` | `/api/config` | Update app config. |
| `GET` | `/api/drives` | List configured drives and their live status. |
| `PATCH` | `/api/drives/{drive_id}` | Update per-drive config. |
| `GET` | `/api/jobs` | List jobs with filtering. |
| `GET` | `/api/jobs/{job_id}` | Job detail with tracks. |
| `POST` | `/api/jobs/{job_id}/resolve` | Resolve an `awaiting_user_id` job with a manual identification. |
| `POST` | `/api/jobs/{job_id}/abandon` | Give up on a job and eject. |
| `GET` | `/api/sessions` | List sessions (built-in and user-authored). |
| `POST` | `/api/sessions` | Create a session (from scratch or cloned from a built-in). |
| `PATCH` | `/api/sessions/{id}` | Update a session. |
| `DELETE` | `/api/sessions/{id}` | Delete a non-built-in session. |
| `POST` | `/api/jobs/{job_id}/transcode` | Queue a session against a rip. Body: `{session_id, overrides?}`. |
| `GET` | `/api/transcodes` | List transcode tasks. |
| `DELETE` | `/api/transcodes/{id}` | Cancel a queued or running transcode task (running = kill container, mark failed). |
| `GET` | `/api/logs` | Global log query. Params: `job_id`, `service`, `level`, `since`. |
| `GET` | `/api/logs/{job_id}` | Per-job log view. Returns JSONL. |

### Transcode container ↔ Backend

The transcode container is short-lived and single-purpose. Its API surface is minimal.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/transcoder/register` | Container startup. Body: `{task_id, hostname, hw_caps}`. Server verifies the task exists and is still expected. |
| `POST` | `/api/transcoder/tasks/{task_id}/claim` | Claim the task. |
| `PATCH` | `/api/transcoder/tasks/{task_id}/heartbeat` | Heartbeat every 30s with progress. |
| `PATCH` | `/api/transcoder/tasks/{task_id}/complete` | Mark done. |
| `PATCH` | `/api/transcoder/tasks/{task_id}/fail` | Mark failed. |

## WebSocket channels

There is one WS endpoint on Backend: `/ws`. After connecting, the client subscribes to named topics with `{op: "subscribe", topic: "…"}` messages. Auth, origin validation, per-topic authorization, and JWT-expiry handling are specified in [05-cross-cutting.md § WebSocket security](05-cross-cutting.md#websocket-security) — the topics below assume a principal that has already passed those checks. Topics are:

| Topic | Direction | Producers | Consumers | Payload |
|---|---|---|---|---|
| `ripper.progress.{job_id}` | Backend → subscribers | Rippers (push directly over WS, fanned out) | UI, other tooling | `{track_id, progress_pct, eta_seconds, updated_at}` |
| `ripper.events` | Backend → subscribers | Backend | UI | Typed events: `rip.started`, `rip.completed`, `rip.failed`, `rip.needs_user_input`, `rip.resumed_from_crash` |
| `transcode.progress.{task_id}` | Backend → subscribers | Transcoders | UI | `{progress_pct, current_pass, eta_seconds}` |
| `transcode.events` | Backend → subscribers | Backend | UI | Typed events: `session.queued`, `session.started`, `session.completed`, `session.failed`, `task.started`, `task.completed`, `task.failed` |
| `system.events` | Backend → subscribers | Backend | UI | Drive online/offline, backend restart, config change. |
| `logs.{job_id}` | Backend → subscribers | Log collector in Backend | UI log viewer | Tails the per-job log stream. |
| `ripper.commands.{drive_id}` | Backend → one ripper | Backend | The ripper registered on that `drive_id` | Typed commands to the owning ripper: `identify.resolved` (user-resolved identity delivered to a ripper parked in `awaiting_user_id`), `job.cancel`. Only the ripper whose hostname matches the drive's `hostname` may subscribe. |
| `transcoder.commands.{task_id}` | Backend → one transcoder | Backend | The transcoder that claimed that task | Typed commands: `task.cancel`. Only the transcoder holding the claim may subscribe. |

### UI session scope

The UI's WS connection is session-scoped: opened after login, closed on logout or page unload. The UI MUST NOT keep a WS alive in a service worker or background tab — "tell me what happened while I wasn't watching" is Apprise's job, not the UI's. On page load the UI reads *current* state (job list, track statuses, etc.) from REST and then opens a WS for live updates going forward; there is no event replay, no catch-up from the `events` table, no "what did I miss." If the user cares about something that already happened, the REST-rendered state reflects it; if they needed to be told about it in real time, they already were — by Apprise.

The ripper's WS producer side is indifferent to whether any UI is subscribed. It pushes progress regardless; Backend's fanout is a no-op when the subscriber set is empty. A user who logs in mid-rip sees the next progress tick immediately (~1s), no warm-up needed.

### Why WS for progress, REST for state transitions?

Two different cost models, two different transports.

**State transitions are REST.** `complete`, `fail`, and `complete-job` *must* land — they're the source of truth for what's been ripped. REST gives us request/response acknowledgement, retry-until-acked semantics on the client, and a clean failure mode (HTTP error code) when something goes wrong. Idempotency keys handle the at-least-once retry case.

**Progress is WS push from the ripper.** Live progress (`{track_id, progress_pct, eta_seconds}`) is fire-and-forget telemetry — losing a tick during a Backend restart is invisible to the user; the next tick replaces it. WS amortizes per-message overhead across the rip, no HTTP handshake per heartbeat tick. The same connection delivers identify-resolution events back to the ripper, so we get one durable connection instead of one + polling.

**No heartbeat at all.** Crash detection is handled at container-restart time (Backend-startup sweep + ripper-startup probe — see [02-job-lifecycle.md § Crash recovery](02-job-lifecycle.md#crash-recovery-restart-the-rip-from-scratch)), not via timeout-based liveness pings. WS protocol-layer ping/pong keeps the connection alive; nothing more is needed.

The transcoder still uses REST + claim/heartbeat (see `/api/transcoder/tasks/{task_id}/heartbeat` below) because multiple ephemeral transcoders compete for queued tasks, which actually requires per-task liveness tracking — a different problem from the one-ripper-per-drive case.

## Event payload shape

All events share a common envelope:

```json
{
  "event_id": "evt_01HXYZ…",
  "event_type": "rip.completed",
  "emitted_at": "2026-04-18T14:32:10.123Z",
  "job_id": "job_01HXYZ…",
  "track_id": null,
  "payload": { … event-specific … }
}
```

Events are also persisted to an `events` table for audit and post-hoc debugging. The `NotificationDispatcher` (Apprise-backed, see [05-cross-cutting.md](05-cross-cutting.md)) consumes them from the table + WS stream.

## Versioning

- The REST API is versioned by URL prefix if we ever need to break: `/api/v2/…`. v3.0 ships `/api/` as implicit v1.
- The Pydantic schemas in `arm_common` are versioned by semver; all services in a release pin the same `arm_common` version.
- Inside a major, we add fields freely (OpenAPI clients tolerate unknown fields). We never remove or rename fields — we deprecate and remove across majors.

## What this contract deliberately does NOT include

- **Inter-worker communication.** Rippers never call Transcoders and vice versa. All cross-worker coordination goes through Backend.
- **Backend → Ripper calls.** Backend does not initiate REST calls to Rippers. If Backend needs to tell a ripper to do something (e.g. "cancel this rip"), it does so by updating DB state and pushing a WS event to which the ripper subscribes. Rippers are never HTTP servers — they only make outbound calls.
- **Binary transport.** Everything is JSON. Large payloads (log batches, metadata blobs) are still JSON; we don't optimize until we measure.
