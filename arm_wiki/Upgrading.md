# Upgrading

ARM v3 upgrades are image-pulls — you don't rebuild or re-clone anything. The
backend runs any pending database migrations on startup, so the schema moves
forward automatically.

> Coming from **ARM v2**? There is no in-place upgrade path. v3 shares no code,
> no database, and no config format with v2. Treat it as a fresh install
> ([Getting Started](Getting-Started)); v2 stays frozen at the `v2-final` tag and
> the two stacks can even run side by side (their containers and volumes are
> namespaced `armv3-*` vs `arm-*`).

## Minor / patch upgrade

```bash
cd ~/arm
docker compose pull
docker compose up -d
```

That pulls the image tag named in `~/arm/docker-compose.yml`, recreates the
changed containers, and the backend migrates the database to match. To pin or
move to a specific version, set `ARM_IMAGE_TAG` in `~/arm/.env` and run the same
two commands.

## Major-version upgrade

A major release may add new service blocks (e.g. a new ripper layout) or require
new certificate SANs, so rerun the installer first to regenerate
`docker-compose.yml` and the leaf certs, then pull:

```bash
cd ~/arm
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
docker compose pull
docker compose up -d
```

Rerunning the installer is safe: it **preserves your `.env` secrets and your
CA**, regenerates the (disposable) leaf certs, and only adds service blocks for
newly-detected drives. See
[Getting Started § Install](Getting-Started#install).

## Before you upgrade

- **No schema rollback.** Alembic `downgrade` is not supported across versions.
  If you want a safety net, dump Postgres first:

  ```bash
  docker exec armv3-db pg_dump -U arm arm > ~/arm-backup-$(date +%F).sql
  ```

  (The dump contains plaintext secrets — store it somewhere you'd trust with a
  password export.)

- **Watch the release notes / [CHANGELOG](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/CHANGELOG.md)**
  for any manual steps a specific release calls out.

## Rolling back

There's no schema downgrade, so a true rollback means restoring the Postgres
dump you took above and pointing `ARM_IMAGE_TAG` back at the previous version.
For minor versions where the schema didn't change, just resetting `ARM_IMAGE_TAG`
and running `docker compose up -d` is enough.
