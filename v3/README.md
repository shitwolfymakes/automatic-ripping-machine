# ARM v3 — Walking Skeleton

Greenfield rebuild. Architecture lives in [docs/arch/](docs/arch/). This directory is the code; everything at the repo root belongs to frozen v2.

## First run (skeleton)

From the repo root:

```bash
bash v3/devtools/bootstrap-certs.sh
cp v3/.env.example v3/.env
# edit POSTGRES_PASSWORD and ARM_SERVICE_TOKEN to real values
docker compose -f v3/docker-compose.yml up -d --build
```

## What this skeleton does

- Backend boots on `https://arm-backend:8443` (internal-CA-signed leaf cert), runs the first Alembic migration.
- One ripper container (`arm-ripper-sr0`) registers itself via `POST /api/ripper/register` and polls `ioctl(CDROM_DRIVE_STATUS)` on `/dev/sr0` every 2s.
- `POST /api/ripper/identify` creates a `Job` row in `status='created'`. No TMDB lookup, no MakeMKV, no transcode.

See [docs/arch/README.md](docs/arch/README.md) for the full target architecture and what's intentionally absent here.

## Verification

See the "Verification" section of the plan that produced this scaffold, or:

1. `docker compose -f v3/docker-compose.yml exec arm-backend curl -fsS --cacert /etc/ssl/certs/ca-certificates.crt https://arm-backend:8443/api/health`
2. `docker compose -f v3/docker-compose.yml exec arm-db psql -U arm -d arm -c "\dt"`
3. `docker compose -f v3/docker-compose.yml logs arm-ripper-sr0`

## Layout

- `packages/arm_common/` — shared Pydantic schemas, enums, ULID helper
- `services/backend/` — FastAPI app + Alembic migrations
- `services/ripper/` — drive poller + Backend client
- `services/_common/docker-entrypoint.sh` — shared CA-merge + PUID drop + tini exec
- `services/{ui,transcode}/` — stub placeholders for deferred PRs
- `devtools/bootstrap-certs.sh` — manual CA + leaf generator (replaces `install.sh` for the skeleton)
