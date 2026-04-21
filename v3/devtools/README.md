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
3. Calls `bootstrap-certs.sh` if `v3/certs/arm-ca.crt` isn't already present.
4. Creates `v3/.env` from `v3/.env.example` if missing, filling in a random `POSTGRES_PASSWORD` and `ARM_SERVICE_TOKEN`, and detecting `PUID`/`PGID`/`CDROM_GID` from the host. An existing `.env` is left untouched.

After it finishes: `docker compose -f v3/docker-compose.yml up -d --build`.

## bootstrap-certs.sh

Manual replacement for the (not-yet-written) `install.sh` cert flow. Generates the internal CA and per-service leaves under `v3/certs/`:

- `arm-ca.{key,crt}` — internal CA (EC P-384, 10-year)
- `arm-backend.{key,crt}`, `arm-db.{key,crt}`, `arm-ripper-sr0.{key,crt}`, `arm-ui.{key,crt}` — leaves signed by the CA

Rerunning the script reuses the existing CA and reissues every leaf. The CA key never leaves the host — only `arm-ca.crt` is mounted into containers (compose already sets this up).

See [../docs/arch/05-cross-cutting.md § Transport (TLS)](../docs/arch/05-cross-cutting.md#transport-tls) for the full cert design.
