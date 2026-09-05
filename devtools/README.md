# devtools

Scripts that support local development of the ARM stack. Not shipped to end users.

## setup-dev.sh

One-shot dev-environment bootstrap. Run once after cloning:

```bash
bash devtools/setup-dev.sh
```

What it does (idempotent — safe to re-run):

1. Checks that `uv`, `docker`, `docker compose`, and `openssl` are available.
2. Runs `uv sync` to create `.venv/` with all workspace members.
3. Calls `bash install.sh --certs-only --no-env --no-compose --no-udev` if `certs/arm-ca.crt` isn't already present.
4. Creates `.env` from `.env.example` if missing, filling in a random `POSTGRES_PASSWORD` and `ARM_SERVICE_TOKEN`, and detecting `PUID`/`PGID`/`CDROM_GID` from the host. An existing `.env` is left untouched.
5. Creates `docker-compose.yml` from the template — no drive enumeration; enroll drives from the UI.
6. Writes a host-wide udev rule (`KERNEL=="sr[0-9]*"`, `UDISKS_AUTO=0`).

After it finishes: `docker compose up -d --build`.

Cert generation is delegated to [install.sh](../install.sh) — the end-user installer is the single source of truth for the CA + leaves under `certs/`. See [../docs/arch/05-cross-cutting.md § Transport (TLS)](../docs/arch/05-cross-cutting.md#transport-tls) for the full cert design.

## ripper-containers.sh

Manages the `arm-ripper-<serial>` containers the backend creates for enrolled drives — they live outside the compose project, so `docker compose down` leaves them running.

```bash
bash devtools/ripper-containers.sh {list|stop|remove}
```

`list` shows name/drive id/image/state; `stop` stops them (the backend restarts them on next boot or `docker start`); `remove` stops and removes them (the backend recreates enrolled ones at next boot).

## iso-smoke.sh

Fixture-driven Phase 15 smoke — runs the ripper end-to-end against the matrix256-corpus Sintel ISO instead of a physical disc.

```bash
bash devtools/iso-smoke.sh
```

Prereqs: dev stack up (`docker compose up -d arm-db arm-backend arm-ui`) and at least one **enrolled** drive. The script borrows an enrolled drive (`ARM_SMOKE_DRIVE_ID`, or the first enrolled drive from `GET /api/drives`) and stops its manager-created container for the duration of the run (two rippers can't register the same `drive_id`), starting it back up when it's done.

Defaults to caching the ISO under `~/arm-corpus/` (override with `ISO_CACHE_DIR`). MakeMKV key resolution: `MAKEMKV_KEY` env first (any value MakeMKV accepts — purchased perma-key or a beta you grabbed manually), then a single forum-scrape attempt. See [../docs/contributors/real-disc-smoke.md § Run the test (ISO fixture)](../docs/contributors/real-disc-smoke.md#run-the-test-iso-fixture--no-physical-disc-needed) for the full runbook and known gotchas.

## crash-drill.sh

Phase 9 + 15 backend crash-recovery drill. Injects a synthetic in-flight job into the DB, force-kills the backend, brings it back, and asserts the lifespan-startup sweep recovered the job. Destructive — confirms before touching anything; `--yes` skips the prompt.

## seed-test-data.sh

Populates the running dev DB with a fixture so the UI shows real data instead
of the empty state: one seed drive + 9 jobs spanning statuses
(ripping / ripped / identified / awaiting-id / ripped-partial / failed, mixed
disc types incl. music CDs and a multi-title DVD, real titles + TMDB posters),
26 tracks (video + audio, excluded / custom-filename / failed variants), disc
fingerprints, and a per-job log file for each job.

```bash
bash devtools/seed-test-data.sh            # clean-then-seed (idempotent; safe to re-run)
bash devtools/seed-test-data.sh --clean    # remove the seed rows and exit
```

Requires the dev stack running (`docker compose up -d` — needs `arm-db` for the
inserts and `arm-backend` to mint valid ULID ids). Seed rows are tagged
`metadata_json {"seed":true}` (the drive by its display_name); `--clean` and
re-runs key off those, so it never touches real jobs. Dev-only — not invoked by
`setup-dev.sh` or CI. View the result in the UI at `https://localhost:8081`
(default login `admin` / `admin`).

## trust-ca.sh

Trusts the ARM v3 local CA (`arm/certs/arm-ca.crt`) on your dev machine so
`https://localhost:8081` loads without the self-signed-cert warning and
`curl`/`wget` stop needing `-k`.

```bash
bash devtools/trust-ca.sh            # trust (idempotent / rotation-safe; re-run freely)
bash devtools/trust-ca.sh --untrust  # remove the CA from the trust store(s)
```

Installs into the Linux trust store (`update-ca-certificates`, needs `sudo`) and —
when running under WSL — the **Windows CurrentUser Root** store (`certutil.exe`, no
UAC) so Chrome/Edge on Windows trust it too. Idempotent (remove-then-add), so it's
safe to re-run after `install.sh --rotate-ca`. Dev-only — not run by `setup-dev.sh`
or CI. `install.sh` owns CA *generation*; this only *trusts* an existing CA. See
[../docs/arch/05-cross-cutting.md § Transport (TLS)](../docs/arch/05-cross-cutting.md#transport-tls).

## regen-openapi-snapshot.sh

Regenerates `services/ui/openapi.snapshot.json` from the live FastAPI app. The CI `openapi-drift` job points at this script in its failure message.
