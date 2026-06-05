# Automatic Ripping Machine (ARM) v3

A greenfield rebuild: FastAPI Backend, Vue UI, Postgres, one ripper per optical
drive, and an ephemeral transcoder. The architecture lives in
[docs/arch/](docs/arch/). ARM v2 is frozen and preserved at the `v2-final` git
tag — it shares nothing with this tree at the code level.

## Install (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
```

For users who want a TTY before the script runs: `bash -c "$(curl -fsSL .../install.sh)"`. Override the prefix with `--prefix /srv/arm`; auto-start with `--start`; rotate the CA with `--rotate-ca`. See `bash install.sh --help` for everything.

The installer drops everything under `~/arm/` (or `--prefix`):

- `certs/` — internal CA + per-service leaf certs (EC P-384, 10y).
- `.env` — bootstrap secrets, generated random on first run.
- `docker-compose.yml` — one ripper service per detected drive (with the right `/dev/sg<M>` SCSI-generic pairing). Image-based; pulls `docker.io/automaticrippingmachine/arm-<svc>:v3.x.y`.
- `docker-compose.gpu.yml` — overlay for VAAPI/QSV/NVENC hosts.
- `raw/`, `media/`, `logs/` — bind-mounted into the stack.

After install: `cd ~/arm && docker compose up -d`. First-boot credentials are `admin` / `admin` (printed in `docker exec armv3-backend cat /logs/first-boot.log` on every boot until you change it). Open `https://localhost:8080`; you'll be forced to set a real password on first login. See [docs/arch/06-deployment.md § Install](docs/arch/06-deployment.md#install) for the full UX.

> ⚠️ If the published registry images don't yet cover your platform or tag, build locally (see "Local development" below) and tag the result so the installer's compose finds it.

## Local development

For contributors editing ARM. From the repo root:

```bash
bash devtools/setup-dev.sh        # uv sync, certs, .env
docker compose up -d --build      # build + start
```

`setup-dev.sh` delegates cert generation to `install.sh --certs-only`; the dev compose at [docker-compose.yml](docker-compose.yml) keeps its `build:` blocks (vs. the installer's `image:` references) so you iterate against your own working tree. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor workflow (trunk-based branching, tests, lint, the OpenAPI contract).

## What's in this tree

- `packages/arm_common/` — shared Pydantic schemas, enums, ULID helper, structured-logging helpers
- `services/backend/` — FastAPI app + Alembic migrations + WS hub + dispatchers (transcode, notification, log-tail)
- `services/ripper/` — drive poller + Backend client + makemkv/HandBrake/abcde drivers
- `services/transcode/` — ephemeral per-task transcoder spawned by the Backend
- `services/ui/` — Vue 3 SPA served by nginx
- `services/_common/docker-entrypoint.sh` — shared CA-merge + PUID drop + tini exec
- `install.sh` — end-user installer (image-based, generates `~/arm/`)
- `devtools/` — contributor tooling (`setup-dev.sh` bootstrap, `iso-smoke.sh`, `crash-drill.sh`, `regen-openapi-snapshot.sh`)

See [docs/arch/README.md](docs/arch/README.md) for the architecture overview and [docs/plans/MASTER_IMPLEMENTATION_PLAN.md](docs/plans/MASTER_IMPLEMENTATION_PLAN.md) for the per-phase rollout.
