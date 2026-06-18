# devtools

Scripts that support local development of the ARM stack. Not shipped to end users.

## setup-dev.sh

One-shot dev-environment bootstrap. Run once after cloning:

```bash
bash devtools/setup-dev.sh
```

What it does (idempotent — safe to re-run):

1. Checks that `uv`, `docker`, `docker compose`, `openssl`, and `lsscsi` are available (`lsscsi` is used to enumerate optical drives — `apt-get install lsscsi` / `dnf install lsscsi` / `pacman -S lsscsi`).
2. Runs `uv sync` to create `.venv/` with all workspace members.
3. Calls `bash install.sh --certs-only --no-env --no-compose --no-udev` if `certs/arm-ca.crt` isn't already present.
4. Creates `.env` from `.env.example` if missing, filling in a random `POSTGRES_PASSWORD` and `ARM_SERVICE_TOKEN`, and detecting `PUID`/`PGID`/`CDROM_GID` from the host. An existing `.env` is left untouched.
5. Creates `docker-compose.yml` from the committed `docker-compose.yml.example` template if it doesn't exist yet — the generated file is **gitignored**, same split as `.env` / `.env.example`, so you never have to discard host-specific changes. Then writes one `arm-ripper-srN` service per optical drive into its generated region (between the `>>>/<<< arm-ripper services` sentinels), pairing each `/dev/srN` with its matching `/dev/sgM` node via `lsscsi -g`. A drive attached after the initial cert bootstrap gets its leaf cert regenerated automatically. The ripper region is rewritten on every run (a no-op when your drives are unchanged); re-run after attaching/removing a drive. To pull static-service updates from the template, delete `docker-compose.yml` and re-run.
6. On a Linux host with optical drives, writes a per-drive host udev rule (`/etc/udev/rules.d/99-arm-no-automount.rules`, via `sudo`) so the desktop's `udisks2`/`gvfs` doesn't grab the disc and block the ripper's post-rip `eject`. Skipped if `udevadm` isn't on PATH or no drive is present. See [../docs/arch/06-deployment.md § Host-side auto-mount](../docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled).

After it finishes: `docker compose up -d --build`.

Cert generation is delegated to [install.sh](../install.sh) — the end-user installer is the single source of truth for the CA + leaves under `certs/`. See [../docs/arch/05-cross-cutting.md § Transport (TLS)](../docs/arch/05-cross-cutting.md#transport-tls) for the full cert design.

## iso-smoke.sh

Fixture-driven Phase 15 smoke — runs the ripper end-to-end against the matrix256-corpus Sintel ISO instead of a physical disc.

```bash
bash devtools/iso-smoke.sh
```

Prereqs: dev stack up (`docker compose up -d arm-db arm-backend arm-ui`). The script stops the live `arm-ripper-sr0` for the duration of the run (it would conflict on the same `drive_id`) and prints the bring-it-back command when it's done.

Defaults to caching the ISO under `~/arm-corpus/` (override with `ISO_CACHE_DIR`). MakeMKV key resolution: `MAKEMKV_KEY` env first (any value MakeMKV accepts — purchased perma-key or a beta you grabbed manually), then a single forum-scrape attempt. See [../docs/contributors/real-disc-smoke.md § Run the test (ISO fixture)](../docs/contributors/real-disc-smoke.md#run-the-test-iso-fixture--no-physical-disc-needed) for the full runbook and known gotchas.

## crash-drill.sh

Phase 9 + 15 backend crash-recovery drill. Injects a synthetic in-flight job into the DB, force-kills the backend, brings it back, and asserts the lifespan-startup sweep recovered the job. Destructive — confirms before touching anything; `--yes` skips the prompt.

## seed-test-data.sh

Populates the running dev DB with a fixture so the UI shows real data instead
of the empty state: one seed drive + 7 jobs spanning statuses
(ripping / ripped / identified / awaiting-id / ripped-partial / failed /
abandoned, mixed disc types, real titles + TMDB posters) + 3 tracks on the
ripped job.

```bash
bash devtools/seed-test-data.sh            # clean-then-seed (idempotent; safe to re-run)
bash devtools/seed-test-data.sh --clean    # remove the seed rows and exit
```

Requires the dev stack running (`docker compose up -d` — needs `arm-db` for the
inserts and `arm-backend` to mint valid ULID ids). Seed rows are tagged
`metadata_json {"seed":true}` (the drive by its display_name); `--clean` and
re-runs key off those, so it never touches real jobs. Dev-only — not invoked by
`setup-dev.sh` or CI. View the result at `https://localhost:8082` (or the Vue UI
at `:8081`).

## trust-ca.sh

Trusts the ARM v3 local CA (`arm/certs/arm-ca.crt`) on your dev machine so
`https://localhost:8081` / `:8082` load without the self-signed-cert warning and
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
