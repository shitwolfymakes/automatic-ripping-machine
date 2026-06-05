# v3 devtools

Scripts that support local development of the v3 stack. Not shipped to end users.

## setup-dev.sh

One-shot dev-environment bootstrap. Run once after cloning:

```bash
bash v3/devtools/setup-dev.sh
```

What it does (idempotent — safe to re-run):

1. Checks that `uv`, `docker`, `docker compose`, and `openssl` are available.
2. Runs `uv sync` in `v3/` to create `v3/.venv/` with all workspace members.
3. Calls `bash v3/install.sh --prefix v3 --certs-only --no-env --no-compose --no-udev` if `v3/certs/arm-ca.crt` isn't already present.
4. Creates `v3/.env` from `v3/.env.example` if missing, filling in a random `POSTGRES_PASSWORD` and `ARM_SERVICE_TOKEN`, and detecting `PUID`/`PGID`/`CDROM_GID` from the host. An existing `.env` is left untouched.

After it finishes: `docker compose -f v3/docker-compose.yml up -d --build`.

Cert generation is delegated to [v3/install.sh](../install.sh) — the end-user installer is the single source of truth for the CA + leaves under `v3/certs/`. See [../docs/arch/05-cross-cutting.md § Transport (TLS)](../docs/arch/05-cross-cutting.md#transport-tls) for the full cert design.

## iso-smoke.sh

Fixture-driven Phase 15 smoke — runs the ripper end-to-end against the matrix256-corpus Sintel ISO instead of a physical disc.

```bash
bash v3/devtools/iso-smoke.sh
```

Prereqs: dev stack up (`docker compose up -d arm-db arm-backend arm-ui`). The script stops the live `arm-ripper-sr0` for the duration of the run (it would conflict on the same `drive_id`) and prints the bring-it-back command when it's done.

Defaults to caching the ISO under `~/arm-corpus/` (override with `ISO_CACHE_DIR`). MakeMKV key resolution: `MAKEMKV_KEY` env first (any value MakeMKV accepts — purchased perma-key or a beta you grabbed manually), then a single forum-scrape attempt. See [../docs/contributors/real-disc-smoke.md § Run the test (ISO fixture)](../docs/contributors/real-disc-smoke.md#run-the-test-iso-fixture--no-physical-disc-needed) for the full runbook and known gotchas.

## crash-drill.sh

Phase 9 + 15 backend crash-recovery drill. Injects a synthetic in-flight job into the DB, force-kills the backend, brings it back, and asserts the lifespan-startup sweep recovered the job. Destructive — confirms before touching anything; `--yes` skips the prompt.

## regen-openapi-snapshot.sh

Regenerates `v3/services/ui/openapi.snapshot.json` from the live FastAPI app. The v3 CI `openapi-drift` job points at this script in its failure message.
