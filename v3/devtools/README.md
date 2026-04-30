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
