# 05 — Cross-Cutting Concerns

Things that touch every service: configuration, authentication, secrets, logging, observability, testing, and the shared Python package.

## Repo layout

v3 is a **monorepo with a shared Python package**, physically isolated under a single top-level `v3/` directory so that **no existing v2 file is touched during development**. See [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) for the full isolation strategy and cutover plan.

```
repo-root/
│
├── arm/ Dockerfile* docker-compose.yml        ← all v2 files untouched
├── devtools/ setup/ scripts/ test_ui/ …       ← all v2 files untouched
│
└── v3/                                        ← every v3 artifact lives here
    ├── packages/
    │   └── arm_common/              # shared Python package
    │       ├── arm_common/
    │       │   ├── schemas/         # Pydantic models (requests, responses, events)
    │       │   ├── models/          # SQLAlchemy ORM (Backend uses; others may import types only)
    │       │   ├── enums.py
    │       │   ├── ulid.py
    │       │   └── client/          # generated OpenAPI client for ripper/transcoder
    │       └── pyproject.toml
    ├── services/
    │   ├── backend/                 # FastAPI app
    │   │   ├── arm_backend/
    │   │   ├── migrations/          # Alembic
    │   │   ├── Dockerfile
    │   │   └── pyproject.toml
    │   ├── ripper/                  # Python ripper
    │   │   ├── arm_ripper/
    │   │   ├── Dockerfile
    │   │   └── pyproject.toml
    │   ├── transcode/               # Python HandBrake wrapper
    │   │   ├── arm_transcode/
    │   │   ├── Dockerfile
    │   │   └── pyproject.toml
    │   └── ui/                      # Vue or React + Vite
    │       ├── src/
    │       ├── package.json
    │       └── Dockerfile
    ├── test_fixtures/
    │   └── big_buck_bunny.iso       # (or a reference to where it lives — see testing below)
    ├── docs/
    │   └── arch/                    # this directory
    ├── devtools/                    # v3-only tooling; root devtools/ stays on v2
    ├── docker-compose.yml           # v3 stack; root compose stays on v2
    ├── .env.example
    └── pyproject.toml               # workspace root (uv or hatch)
```

Key properties:
- A single PR can change a Pydantic schema in `arm_common` and its producers + consumers in `services/*`. Protocol changes are always atomic.
- No v3 PR ever modifies a v2 file. v3 merges are strictly additive to the repo tree; v2 keeps building and running the entire time.

## Configuration strategy

Two tiers:

**Tier 1 — bootstrap (env vars, sourced from `.env`).** Compose reads `v3/.env` via `${VAR}` substitution and injects only what each container actually reads.

**What the user sets in `.env`:**

| Var | Purpose |
|---|---|
| `POSTGRES_USER` | Postgres role (Postgres image init contract) |
| `POSTGRES_PASSWORD` | Postgres password (Postgres image init contract) |
| `POSTGRES_DB` | Postgres database (Postgres image init contract) |
| `ARM_SERVICE_TOKEN` | Shared bearer token for service-to-service auth. Generated once by the install script (`openssl rand -hex 32`), never rotated in normal operation. Backend rejects any request without it. Defense-in-depth against misconfigured compose that exposes Backend's port. |
| `ARM_LOG_LEVEL` | `debug`/`info`/`warn`/`error`. Optional, default `info`. |
| `PUID` | Numeric UID the ripper and transcoder drop to before writing `/raw` and `/media`. Should match the UID that owns the host-side mount (or the UID the user's media server runs as). Default `1000`. |
| `PGID` | Numeric GID shared by ripper and transcoder so group-writable handoff on `/raw` works. Should match the group that owns the host-side mount. Default `1000`. |
| `CDROM_GID` | Numeric GID of the host's optical group (`stat -c %g /dev/sr0`). Passed to ripper containers via `group_add` so the PUID-dropped process can read `/dev/sr*`. Default `44` (Debian/Ubuntu `cdrom`). Installer detects and writes this on first boot. |

**What compose derives and injects per-service:**

| Var | Consumer | Derivation |
|---|---|---|
| `DATABASE_URL` | Backend | Composed in `compose.yml` as `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@arm-db:5432/${POSTGRES_DB}`. User never edits it directly. |
| `ARM_BACKEND_URL` | Ripper, Transcode | Static `http://arm-backend:8000` — hard-coded in compose, not in `.env`. |
| `ARM_DRIVE_DEV` | Ripper (per-service) | Declared per-ripper-service block in compose (`ARM_DRIVE_DEV: /dev/sr0` on `arm-ripper-sr0`, etc.). |
| `ARM_GPU_DEVICE` | Transcode (per-spawn) | Injected at spawn time by Backend based on the claimed `gpus` row. |

**Crucially, Ripper and Transcode containers have no DB env vars.** They talk only to Backend via the shared service token.

**Tier 2 — runtime (DB).** Everything the user tweaks in the UI: third-party API keys, retention policy, auto-transcode flag, Apprise URLs. Stored in the `config` table as plaintext; UI writes, Backend reads.

No YAML files. No mounted `/etc/arm/*.conf`. The v2 `arm.yaml` pattern is retired.

## Authentication model

### User-facing (UI → Backend)

- **Local users** stored in the `users` table. Passwords hashed with argon2id.
- One `admin` account is seeded on first boot with a random generated password printed to the Backend's stdout. First login forces a password change.
- **Auth is JWT-based, not cookie-based.** `POST /api/auth/login` with `{username, password}` → `{access_token, expires_at}`. UI stores the token in `localStorage` and sends it on every REST call as `Authorization: Bearer <jwt>`. WS auth is a first-message handshake (`{"op": "auth", "token": "<jwt>"}`); Backend closes the connection if auth doesn't arrive within 5 seconds.
- Tokens are signed HS256 with the value of `config.session_signing_key` (auto-generated on first Backend boot). Symmetric signing is fine because Backend is both issuer and verifier.
- Token TTL: 7 days, non-refreshing. User re-logs in once a week. No refresh token in v3.0 — simpler, and the friction is low for a single-user homelab.
- Logout is client-side (drop the token). There is no server-side token blocklist in v3.0. Emergency "log out everywhere" is a manual operation: rotate `config.session_signing_key` (via a future admin action or by hand), which invalidates every outstanding JWT at once.
- No MFA in v3.0. Single-user homelab scope. Revisit if scope changes.

**Why JWT and not session cookies.** Homelab operators deploy ARM in ways we can't predict, including behind reverse proxies with public hostnames. Session cookies touch GDPR/CCPA consent law; Bearer-in-header / localStorage sidesteps it. The single-user scope also means cookie-specific wins (easy server-side revocation, HttpOnly XSS protection) don't buy much here.

The default-creds footgun that v2 has (ships with `admin`/`password` and does not force change) is closed by the random generated password.

### Service-to-service

- A single long-lived **service token** (`ARM_SERVICE_TOKEN`) lives in `.env` and is injected into Backend, Ripper, and Transcode containers via Compose.
- Every container reads it from its own environment. There is no authoritative DB copy — the `.env` file is the single source of truth.
- Attached to every ripper/transcoder REST call as `Authorization: Bearer <token>`.
- WebSocket connections authenticate via the same token in the initial `Sec-WebSocket-Protocol` header or via a one-time WS auth message.

Generated once by the install script (`openssl rand -hex 32`). No rotation ceremony — on a private homelab LAN the threat model doesn't justify it. If a user accidentally commits or leaks `.env`, the manual remediation is: edit `.env` with a new token, `docker compose up -d` to recreate containers. Documented as troubleshooting, not routine.

## Secrets handling

- Third-party API keys (TMDB, OMDB, MusicBrainz) and Apprise URLs are stored **plaintext** in the `config` table.
- Consequence: DB dumps contain secrets. Treat Postgres backups as sensitive files.
- No secrets are logged. Log lines that touch `config` rows MUST redact the API-key/URL fields — enforced by a structured-logging helper that knows which fields to drop.

## Logging

### Format

Every service logs **structured JSON to stdout**. One event per line (JSONL). Required fields on every line:

```json
{
  "ts": "2026-04-18T14:32:10.123Z",
  "level": "info",
  "service": "arm-ripper-sr0",
  "job_id": "job_01HXYZ…",
  "track_id": "trk_01HXYZ…",
  "session_application_id": null,
  "msg": "track rip complete",
  "extra": { … arbitrary structured context … }
}
```

`job_id`, `track_id`, `session_application_id` may be null when the log line is not in the context of a specific job (startup, config reload, etc.). When a log is inside a job context, they MUST be populated — this is what makes the per-job log view work.

### Persistence

- Logs are emitted to stdout (so `docker logs` works).
- Logs are ALSO appended to `/logs/<service>.log` (shared volume). Each service manages its own file with size-based rotation (10MB × 5 files = 50MB per service ceiling).
- The Backend reads `/logs/*.log` on demand to serve the per-job log view in the UI — a simple grep on `job_id` across all service logs.
- A zip-for-bug-report endpoint in the UI (`GET /api/logs/{job_id}.zip`) streams the per-job slice of every service log, ready to drag onto a GitHub issue. This mirrors the v2 workflow documented in [CONTRIBUTING.md](../../CONTRIBUTING.md).

### DEBUG level

- `ARM_LOG_LEVEL=debug` can be set per-service via compose override. No UI toggle in v3.0 — restart-to-change is acceptable for a homelab.
- The UI shows the current log level per service on a diagnostics page and links to the bug-report zip endpoint.

### What we don't do

- No Loki / Promtail / ELK. Gold-plated for this scale. Users who want it can ship `/logs` to their own stack.
- No syslog. No journald.

## Observability beyond logs

**v3.0 ships logs only.** No Prometheus `/metrics`, no OpenTelemetry traces. Homelab operators who need them can scrape Docker engine metrics or add their own sidecars.

The explicit structure of the typed event log (`events` table) is the closest thing to metrics in v3.0 — an operator can SQL it for "how many rips succeeded this week" without an external TSDB.

## Testing strategy

Two tiers, both in CI:

### Tier 1 — per-service unit tests

- `pytest` per service, no mocks for arm_common types.
- Backend: tests against a real Postgres spun up in CI via the existing compose pattern (`docker compose up arm-db-test` equivalent).
- Ripper: tests drive the ripper's Python logic with a fake Backend (httpx-mock + fake WS). Pure logic tests, no drive access.
- Transcode: tests drive the wrapper with a synthetic input file; HandBrake is shelled out but can be replaced with a no-op for fast CI.

### Tier 2 — contract tests

- Published OpenAPI (from FastAPI) is checked against `arm_common.schemas` on every PR.
- A contract test per ripper/transcoder call: the test frames a real request, posts it to a spun-up Backend in test mode, asserts shape + status.
- This catches "producer changed, consumer didn't" before it hits runtime.

### Integration rig — Big Buck Bunny

The project lead owns a copy of **Big Buck Bunny** (CC-BY, legally redistributable). A BBB ISO serves as the integration fixture:

- `devtools/arm-test-rip` script: mounts the BBB ISO as a loop device in a disposable ripper container, lets the real MakeMKV (or a loopback `dd`-based stub for CI where MakeMKV licensing is awkward) process it, and asserts the output lands in `/raw/` with correct metadata.
- Works on a developer's machine; may be reduced in CI to a recorded fixture if MakeMKV's container licensing is a blocker.

### What we don't test

- Browser e2e with Playwright. Fragile; returns too little per unit of maintenance. WS+REST contract tests cover the data plane; the UI is thin enough to be reviewed visually.
- Arbitrary proprietary discs. Obvious legal reasons.

## Notifications

v3 ships **Apprise with a native pass-through config**. Users paste Apprise URLs into a textarea in the UI; Backend feeds those URLs directly to `apprise.Apprise().add(url)` with no ARM-side per-service dictionary.

Rationale: v2 hand-maintained a 30-service dictionary mapping ARM-specific keys to Apprise URLs and went stale — new services (Signal, Home Assistant, MQTT, Pushover, Fluxer) piled up as feature requests, and bug reports accumulated around URL-assembly edge cases. Passing URLs through verbatim means every service Apprise supports works the day it supports it, with no PR to ARM.

- Backend emits typed events to the `events` table and on WS topics.
- `NotificationDispatcher` interface in the Backend; v3.0 ships one implementation (`AppriseDispatcher`) that iterates `config.notification_apprise_urls` on each event.
- Event naming convention: `<domain>.<verb_past_tense>` (e.g. `rip.completed`, `transcode.failed`).
- Event payloads share an envelope: `{event_id, event_type, emitted_at, job_id?, track_id?, data: {...}}`. New payload shapes are added by emitting new event types, never by mutating the shape of an existing type.

Specific event types grow organically as features land. The event *taxonomy* is not pre-enumerated — but the *naming rule* and the *envelope shape* are fixed so new events slot in without protocol churn.
