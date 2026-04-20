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

**Tier 1 — bootstrap (env vars, sourced from `.env`).** Compose reads `~/arm/.env` via `${VAR}` substitution and injects only what each container actually reads. See [06-deployment.md § Install prefix and layout](06-deployment.md#install-prefix-and-layout) for how the installer seeds it.

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
| `DATABASE_URL` | Backend | Composed in `compose.yml` as `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@arm-db:5432/${POSTGRES_DB}?sslmode=verify-full&sslrootcert=/etc/ssl/arm/arm-ca.crt`. User never edits it directly. |
| `ARM_BACKEND_URL` | Ripper, Transcode, UI nginx | Static `https://arm-backend:8443` — hard-coded in compose, not in `.env`. Clients verify against the merged system trust store, which includes the internal CA merged in at container startup. See [Transport (TLS)](#transport-tls). |
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

**Why argon2id and not bcrypt.** Argon2id is the 2015 Password Hashing Competition winner and the current OWASP recommendation. It is memory-hard — cost is tunable on three axes (time, memory, parallelism) instead of bcrypt's single rounds parameter — which forces an attacker to spend RAM per guess and neutralises the GPU/ASIC speedup bcrypt is vulnerable to. The `id` variant combines Argon2i's side-channel resistance with Argon2d's GPU resistance. Secondary wins: no 72-byte silent truncation (bcrypt's long-standing footgun), and the encoded hash embeds its parameters so cost can be raised later via transparent rehash-on-verify without a schema change. Implementation: `argon2-cffi`'s `PasswordHasher` with OWASP-default parameters (memory=19 MiB, iterations=2, parallelism=1); tune upward if login latency budget allows. bcrypt would not be *broken*, just a weaker default for something designed in 2026.

The default-creds footgun that v2 has (ships with `admin`/`password` and does not force change) is closed by the random generated password.

### Service-to-service

- A single long-lived **service token** (`ARM_SERVICE_TOKEN`) lives in `.env` and is injected into Backend, Ripper, and Transcode containers via Compose.
- Every container reads it from its own environment. There is no authoritative DB copy — the `.env` file is the single source of truth.
- Attached to every ripper/transcoder REST call as `Authorization: Bearer <token>`.
- WebSocket connections authenticate via the same token in the initial `Sec-WebSocket-Protocol` header or via a one-time WS auth message.

Generated once by the install script (`openssl rand -hex 32`). No rotation ceremony — on a private homelab LAN the threat model doesn't justify it. If a user accidentally commits or leaks `.env`, the manual remediation is: edit `.env` with a new token, `docker compose up -d` to recreate containers. Documented as troubleshooting, not routine.

**Shared-token tradeoff.** The service token identifies "an ARM internal service," not "this specific ripper vs that one." A ripper container compromised at the host level could present the same token and pretend to be a different ripper or the transcoder. The mitigation is authorization scoping at the endpoint level (see below), not token-per-service — on a private LAN with three or four containers the ceremony of per-service tokens buys little and costs a lot of operational surface.

### Authorization rules

Authentication answers "is this request from a known principal." Authorization answers "is that principal allowed to do *this*." Backend enforces the following rules, in addition to the bearer-token check:

- **Drive-scoped ripper endpoints** (`POST /api/ripper/jobs/{job_id}/resume`, `POST /api/ripper/identify`, `PATCH /api/ripper/tracks/{track_id}/*`, `POST /api/ripper/jobs/{job_id}/complete`): Backend verifies that the referenced `job_id` (or the track's parent job) belongs to a `drive_id` whose `hostname` matches the ripper's registered hostname. A ripper cannot reset, complete, or fail a job on a different drive.
- **Task-scoped transcoder endpoints** (`/api/transcoder/tasks/{task_id}/*`): Backend verifies the task is currently claimed by the hostname on the bearer context. An unclaimed task cannot be completed; a task claimed by a different transcoder cannot be touched.
- **UI-only endpoints** (`/api/config`, `/api/sessions`, `/api/drives`, job CRUD): service token is rejected. UI JWT is required.
- **Ripper/transcoder endpoints** (`/api/ripper/*`, `/api/transcoder/*`): UI JWT is rejected. Service token is required.

These rules close the "compromised ripper acts as a different ripper" gap down to "compromised ripper acts as itself," which is the best an endpoint-layer check can do with a shared credential.

## Transport (TLS)

**All HTTP-layer traffic is TLS, always.** Both REST and WebSocket — intra-compose (UI ↔ Backend, Ripper ↔ Backend, Transcode ↔ Backend) and LAN-side (browser ↔ UI). There is no "plaintext internal hop." Same rule for REST and WS: if it's HTTP-based, it's `https://` / `wss://`.

The Docker bridge network is technically not reachable from outside the host, but "not reachable today" isn't the same as "not reachable." A misconfigured port publish, a compromised sibling container, or a future docker-network gotcha is enough to turn an intra-compose plaintext hop into a JWT-sniffing or service-token-sniffing opportunity. TLS-everywhere removes the class of problem instead of depending on operator discipline.

**Deployment scope: LAN-only, never internet-exposed.** ARM v3 is designed to be reached from a browser on the same LAN (or through a VPN into that LAN). It is not intended to be exposed to the public internet, ever — the threat model and the single-admin / homelab auth surface assume a trusted network boundary. Users who want remote access should run WireGuard or Tailscale back to their home network rather than port-forwarding `8081`. This framing has a direct consequence for certs: Let's Encrypt's HTTP-01 challenge requires a publicly-reachable HTTP server, which we explicitly do not have; even DNS-01 requires a real owned domain just to cert a LAN service, which is ceremony without payoff. The internal CA below is the expected path for every hop, including browser ↔ UI.

### Cert layout

Everything lives under `~/arm/certs/` on the host (see [06-deployment.md § Install prefix and layout](06-deployment.md#install-prefix-and-layout)) and is generated by the installer — the user never touches `openssl`.

- **Internal CA, generated once at install time.** `install.sh` produces `~/arm/certs/arm-ca.key` (EC P-384, mode `0400`) + `~/arm/certs/arm-ca.crt` with a 10-year expiry. Unique per install; no two ARM deployments share a CA.
- **Per-service leaf certs**, signed by the internal CA, one per listening service: `arm-backend.{key,crt}`, `arm-ui.{key,crt}`, `arm-db.{key,crt}`, and `arm-ripper-sr{N}.{key,crt}` — one leaf per optical drive detected at install time. SANs cover the compose hostname (`arm-backend`, `arm-db`, `arm-ripper-sr0`, etc.); for `arm-ui`, the leaf additionally SANs the host's LAN hostname(s) if the installer can determine them. Also 10-year expiry.
- **Every container bind-mounts `~/arm/certs/arm-ca.crt` read-only** at `/etc/ssl/arm/arm-ca.crt`. Listening services additionally mount their own leaf `.crt` + `.key` at `/etc/ssl/arm/tls.crt` / `/etc/ssl/arm/tls.key`.
- **Browser-facing UI cert**: by default, nginx uses the same internal-CA-signed leaf as every other hop. Browsers show an "untrusted CA" warning on first visit; users either click through or (recommended) import `~/arm/certs/arm-ca.crt` into their browser/OS trust store once, after which the warning goes away for every device that trusts the CA. Advanced users who already run their own home-lab CA or have a wildcard cert for a LAN-local domain can override via `TLS_CERT_PATH` / `TLS_KEY_PATH` in `.env`. Either way, the stack is never plaintext.
- **Postgres is TLS too.** The `arm-db` container runs Postgres with `ssl=on`, using the `arm-db.{crt,key}` leaf from the internal CA. Backend connects with `sslmode=verify-full` against the same mounted CA. No carve-out: the "compromised sibling container sniffs a plaintext hop" threat model that motivates TLS-everywhere for HTTP applies identically to DB traffic — `DATABASE_URL` carries Postgres credentials on every connection, and rows in flight include argon2id hashes, `config.session_signing_key`, and third-party API keys.

### CA lifecycle and key security

- **Who generates it:** the installer (`install.sh`), running on the host as the invoking user, using the host's `openssl`. Never baked into an image; never generated inside a container. Every install gets a unique CA.
- **Where the key lives:** `~/arm/certs/arm-ca.key` on the host filesystem, mode `0400`, owned by the invoking user. **The CA key is never mounted into any service container.** Only `arm-ca.crt` (the public cert) is bind-mounted into containers. Once leaves are issued, no running service needs the key at all; it sits idle on the host until the user adds a new drive or rotates.
- **Adding a new drive:** user edits compose (or, better, reruns `install.sh` to re-probe and append), which signs a new leaf against the existing CA key. Existing leaves keep working; no re-trust required on LAN clients.
- **Rotation** is explicit and rare: `install.sh --rotate-ca` regenerates the CA and every leaf with a confirmation prompt, then the user re-imports `arm-ca.crt` on every LAN client that previously trusted it. There is no OCSP, no CRL, no auto-rotation — this is the nuclear option for suspected compromise.
- **Threat model.** Host compromise = CA compromise; the design does not try to defend a compromised host from itself. The real risk is accidental exposure of `arm-ca.key` — chiefly via a backup written to somewhere less protected than the host. Back it up alongside `.env` and treat it like a password.

### Container-side trust store: merged bundle at startup

Each service image has an entrypoint step that runs before the main process:

```sh
cp /etc/ssl/arm/arm-ca.crt /usr/local/share/ca-certificates/arm-ca.crt
update-ca-certificates
```

This merges the mounted per-install internal CA into `/etc/ssl/certs/ca-certificates.crt` alongside the Mozilla root bundle that ships with the Debian-based base image. The merged bundle is what Python's `ssl` module, `httpx` (via the system default), `curl`, `wget`, and everything else picks up — without any per-client `verify=` plumbing in application code.

This pattern intentionally avoids setting `REQUESTS_CA_BUNDLE` or `SSL_CERT_FILE` to the internal CA alone: doing so would make httpx trust *only* that CA, and outbound calls to `api.themoviedb.org` / Apprise endpoints / SMTP-over-TLS would fail public-cert verification. The merge lets the same trust store handle both public outbound and intra-compose internal HTTPS.

The division of responsibility is:
- **Installer** → generates CA, drops `arm-ca.crt` into `~/arm/certs/`, compose bind-mounts it into each container at `/etc/ssl/arm/arm-ca.crt`.
- **Image** → entrypoint merges mounted CA into system bundle on startup. Runs in ~50ms per container start. Keeps images hermetic (no per-install data baked in).
- **Application code** → plain `httpx.AsyncClient()` with default trust. No per-request or per-client `verify=` argument needed.

### Env/URL consequences

- `ARM_BACKEND_URL` is `https://arm-backend:8443` (not `http://…:8000`). Backend listens on 8443 with TLS; port 8000 does not exist.
- UI nginx proxies `/api/*` to `https://arm-backend:8443`, using the merged system trust store (and therefore the internal CA) as trust anchor. `/ws/*` the same (`wss://arm-backend:8443/ws`).
- Rippers and Transcoders dial `https://arm-backend:8443` directly, verifying the server cert via the same merged trust store.
- `DATABASE_URL` carries `?sslmode=verify-full&sslrootcert=/etc/ssl/arm/arm-ca.crt`. Backend refuses to connect to a Postgres that presents any cert not signed by the internal CA or not matching `arm-db`. The `arm-db` container is launched with `command: -c ssl=on -c ssl_cert_file=/etc/ssl/arm/tls.crt -c ssl_key_file=/etc/ssl/arm/tls.key`, mounting its leaf the same way every other service does.

### What we deliberately do NOT do

- **mTLS.** Client cert distribution + per-service cert issuance on startup is operational surface the stack doesn't need. The shared service token authenticates the caller; server-side TLS protects it in transit. mTLS would let us drop the shared token eventually, but the cert-per-container story is more moving parts than a homelab wants.
- **Auto-rotation.** Certs expire in 10 years. If the user cares about rotation, they rerun `install.sh --rotate-ca` and `docker compose up -d`.
- **Public-CA-issued certs.** Let's Encrypt and other public CAs sign only publicly-resolvable hostnames, and we've designed for LAN-only deployment — so no public CA fits the default path. The `TLS_CERT_PATH` / `TLS_KEY_PATH` override exists for users who have their own setup (home-lab CA, wildcard cert, ACME-against-a-private-ACME-server like `step-ca`), but nothing in v3.0 automates or recommends a public-CA integration.

## WebSocket security

The WS endpoint (`/ws` on Backend) is exposed through the same nginx that fronts REST and is WSS end-to-end — browser ↔ UI nginx is `wss://` (external cert), UI nginx ↔ Backend is `wss://arm-backend:8443` (internal CA). There is no plaintext WS hop at any layer; see [Transport (TLS)](#transport-tls). Specific rules beyond what the general auth model covers:

- **First-message auth window.** A freshly-upgraded WS connection is in a `pending_auth` state. The only op accepted in that state is `{"op": "auth", "token": "..."}`; anything else closes the connection with code 4401. Backend closes the connection after 5 seconds if no auth message arrives. Subscribes sent before the server has ack'd auth are rejected, not queued.
- **Origin validation at upgrade.** Browsers send `Origin` on WS handshakes but do *not* enforce same-origin the way they do for XHR — a malicious page could otherwise open a WS to Backend while a logged-in user is on another tab. Backend matches `Origin` against an allowlist (the configured UI hostname(s), configurable in `.env` as `ARM_ALLOWED_ORIGINS`). Service-token connections skip this check (they come from sibling containers with no `Origin`).
- **Per-topic authorization.** After auth, topic subscription is gated by principal type:
    - UI-JWT principals may subscribe to: `ripper.progress.{job_id}`, `ripper.events`, `transcode.progress.{task_id}`, `transcode.events`, `system.events`, `logs.{job_id}`.
    - Service-token ripper principals may subscribe *only* to their own inbound command topic (e.g. `ripper.commands.{drive_id}`, used by Backend to push identify-resolution events back to the owning ripper). A ripper cannot subscribe to another drive's command topic, nor to any UI-facing topic.
    - Service-token transcoder principals may subscribe *only* to `transcoder.commands.{task_id}` for the task they hold a claim on.
    - Unknown topics are rejected, not silently ignored.
- **Backend → ripper command scoping.** Outbound commands (identify-resolution events, cancellation) are routed to the specific ripper whose registered `hostname` matches the `drives` row for the target `job_id`. The topic name (`ripper.commands.{drive_id}`) is the mechanism; the authorization check above is the guarantee.
- **JWT expiry vs long-lived WS.** Tokens are validated at handshake only. A WS opened with a still-valid token remains authorized until the client closes it or the network drops — even if the token expires mid-connection. With 7-day token TTL and the longest realistic rip session measured in hours, this is the simpler behavior. When an expired token causes a REST call to 401, the UI forces re-login and reconnects the WS with the new token; server-side eviction at token expiry is unnecessary complexity for the single-user homelab scope.
- **Rate limiting.** Not enforced in v3.0. A per-connection cap on inbound messages/sec could be added later; for the scale of one or two rippers pushing progress at ~1 Hz it is not load-bearing. Documented as accepted.

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
