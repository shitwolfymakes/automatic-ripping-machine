# 06 — Deployment

Docker Compose is the one and only supported deploy target for v3.

## Supported targets

- Bare-metal Docker on Linux (Ubuntu, Debian, Fedora, Arch).
- Unraid (runs stock Docker).
- Synology DSM (runs stock Docker).
- Any Linux host with Docker Engine ≥ 24 and Compose v2 ≥ 2.20.

## Explicitly NOT supported

- TrueNAS / iX Systems. Not a goal. Do not file bugs against it.
- Kubernetes / Helm.
- Docker Desktop on macOS/Windows **for ripping**. Internal SATA optical drives cannot be passed to the WSL2/macOS VM; USB drives via `usbipd-win` may work but are not tested. Windows and macOS users can still run the UI + transcoder stack as a library-management frontend (PUID/PGID works correctly on WSL2-native paths, named volumes, and SMB mounts — see "File ownership" below). NTFS bind mounts from `C:\...` are unsupported: the translation layer fakes ownership and ignores `chown`, so PUID becomes cosmetic.
- Podman (may work by accident; not tested).

## Install prefix and layout

The install script (see "Install" below) drops everything under a single prefix, **`~/arm/` by default**. The user never clones the repo, never runs a build, never reads source. The stack is entirely image-based.

```
~/arm/
├── .env                            # 0600 — generated; user edits optional fields
├── docker-compose.yml              # 0644 — generated per host (one ripper service per detected drive)
├── certs/                          # 0700
│   ├── arm-ca.key                  # 0400 — CA private key; NEVER mounted into a container
│   ├── arm-ca.crt                  # 0444 — mounted read-only into every service
│   ├── arm-backend.{key,crt}       # leaf for Backend
│   ├── arm-ui.{key,crt}            # leaf for UI nginx
│   └── arm-ripper-sr{N}.{key,crt}  # one leaf per detected optical drive
├── db/                             # Postgres data (bind-mount)
├── logs/                           # shared logs (PUID:PGID)
├── raw/                            # rip output (PUID:PGID, 2775 setgid)
└── media/                          # transcoded library (PUID:PGID, 2775 setgid)
```

The user runs the stack from this directory: `cd ~/arm && docker compose up -d`. All bind-mounts in the generated compose are relative (`./certs/...`, `./raw`, etc.), so moving `~/arm/` to `/srv/arm/` or `/mnt/tank/arm/` is a matter of moving the directory — nothing is hard-coded to `$HOME`.

## Compose topology

The generated `~/arm/docker-compose.yml` references pinned images from `docker.io/automaticrippingmachine/` and bind-mounts paths under its own directory. No `build:` directives; nothing is compiled on the host.

```yaml
name: armv3   # compose project name; keeps container/volume names distinct from v2

services:
  arm-db:
    image: postgres:18
    container_name: armv3-db
    restart: unless-stopped
    # Entrypoint wrapper copies the bind-mounted leaf into a postgres-owned
    # location with mode 0600. Postgres refuses ssl_key_file otherwise.
    entrypoint:
      - bash
      - -c
      - |
        install -o postgres -g postgres -m 0600 /etc/ssl/arm/tls.key /tmp/pg.key
        install -o postgres -g postgres -m 0644 /etc/ssl/arm/tls.crt /tmp/pg.crt
        exec docker-entrypoint.sh postgres \
          -c ssl=on \
          -c ssl_cert_file=/tmp/pg.crt \
          -c ssl_key_file=/tmp/pg.key \
          -c ssl_ca_file=/etc/ssl/arm/arm-ca.crt
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - ./db:/var/lib/postgresql/data
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-db.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-db.key:/etc/ssl/arm/tls.key:ro

  arm-backend:
    image: docker.io/automaticrippingmachine/arm-backend:v3.0.0
    container_name: armv3-backend
    restart: unless-stopped
    depends_on: [arm-db]
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@arm-db:5432/${POSTGRES_DB}?sslmode=verify-full&sslrootcert=/etc/ssl/arm/arm-ca.crt
      ARM_SERVICE_TOKEN: ${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: ${ARM_LOG_LEVEL:-info}
      PUID: ${PUID:-1000}
      PGID: ${PGID:-1000}
    volumes:
      - ./raw:/raw
      - ./media:/media
      - ./logs:/logs
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-backend.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-backend.key:/etc/ssl/arm/tls.key:ro
      - /var/run/docker.sock:/var/run/docker.sock   # for spawning arm-transcode

  arm-ui:
    image: docker.io/automaticrippingmachine/arm-ui:v3.0.0
    container_name: armv3-ui
    restart: unless-stopped
    depends_on: [arm-backend]
    ports:
      - "8081:443"   # v3 on 8081 (TLS); v2 stays on 8080 during co-existence
    volumes:
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ui.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ui.key:/etc/ssl/arm/tls.key:ro

  arm-ripper-sr0:
    image: docker.io/automaticrippingmachine/arm-ripper:v3.0.0
    container_name: armv3-ripper-sr0
    restart: unless-stopped
    depends_on: [arm-backend]
    devices:
      - "/dev/sr0:/dev/sr0"
    group_add:
      - "${CDROM_GID:-44}"   # host's optical group GID so PUID-dropped process can read /dev/sr0
    environment:
      ARM_DRIVE_DEV: /dev/sr0
      ARM_BACKEND_URL: https://arm-backend:8443
      ARM_SERVICE_TOKEN: ${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: ${ARM_LOG_LEVEL:-info}
      PUID: ${PUID:-1000}
      PGID: ${PGID:-1000}
    volumes:
      - ./raw:/raw
      - ./logs:/logs
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ripper-sr0.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ripper-sr0.key:/etc/ssl/arm/tls.key:ro

  # One arm-ripper-srN block per detected drive — emitted by the installer,
  # not hand-edited. Rerun install.sh after adding a new drive.
```

The `armv3-` prefix on container names and `name: armv3` project namespace guarantee zero collision with v2 containers (which use `arm-` names) so `docker compose ls`, `docker compose down`, and `docker volume ls` all show v3 and v2 as distinct projects.

Each service container, on startup, copies the mounted `/etc/ssl/arm/arm-ca.crt` into `/usr/local/share/ca-certificates/` and runs `update-ca-certificates`. This merges the per-install internal CA with the base image's Mozilla root bundle, so outbound HTTPS (TMDB, OMDB, Apprise) verifies against public roots and inbound/intra-compose HTTPS verifies against the internal CA — all via the default system trust store, no per-client `verify=` plumbing in application code. See [05-cross-cutting.md § Transport (TLS)](05-cross-cutting.md#transport-tls) for the full cert layout and rationale.

Note that v2 may be simultaneously bound to `/dev/sr0`. If you want to run a real v3 rip, stop v2 first — the kernel permits multiple containers to map the same device but MakeMKV won't play nicely with the disc being used by two processes. This is the one unavoidable resource conflict and it only matters during the transition period.

Transcode services are NOT declared in compose — they are spawned dynamically by the Backend via Docker socket.

## Why one ripper service per drive

Ripper-per-drive is explicit and declarative: users see which drives they have by reading compose, device pass-through is one line per service, and a failing ripper doesn't take down its siblings. Each ripper watches its own drive via a 2s `ioctl(CDROM_DRIVE_STATUS)` poll — no udev rules on host or in container, no distro-specific wiring. This is the trade-off we accepted vs. dynamic ripper spawning — one line of config per drive is a small price for "it's all visible in one file."

If a user has drives `sr0` and `sr1` they duplicate the ripper block twice. There is no "cluster of interchangeable rippers" — each ripper owns one physical device.

## Environment file

`~/arm/.env` holds bootstrap values. The installer generates it with sensible defaults; the user edits only the optional fields (API keys, non-default ports) — and even those are primarily set via the UI, not the env file.

```bash
# Generated by the installer — do not commit
POSTGRES_USER=arm
POSTGRES_PASSWORD=<generated: openssl rand -hex 24>
POSTGRES_DB=arm
ARM_SERVICE_TOKEN=<generated: openssl rand -hex 32>
PUID=<host user's UID, `id -u`>
PGID=<host user's GID, `id -g`>
CDROM_GID=<detected via `stat -c %g /dev/sr0`, else 44>
ARM_LOG_LEVEL=info
```

`DATABASE_URL` is composed from these at compose-parse time for the Backend; see the compose snippet above.

The pair of `~/arm/.env` + `~/arm/docker-compose.yml` is all a running install depends on. Re-running the installer on an existing install preserves `.env` (only re-derives `PUID`/`PGID`/`CDROM_GID` if those host facts changed), preserves the CA, and only *adds* new ripper service blocks for newly-attached drives. Upgrades come from the image tags in the compose file, not from editing `.env`.

## File ownership

v3 uses the linuxserver.io-style `PUID`/`PGID` pattern to keep files on `/raw` and `/media` owned by a UID/GID the user controls — typically matching their media server (Plex/Jellyfin) so downstream consumers can read the files without any post-hoc `chown`.

**How it works:**

- Each service's entrypoint starts as root, creates (or adjusts) an internal user to match `PUID:PGID` from the environment, then `gosu`/`s6-setuidgid` drops privileges before any filesystem write. Every byte ARM writes is owned by `PUID:PGID`.
- Ripper and transcoder share `PGID` so group-writable handoff on `/raw` works (transcoder reads + deletes intermediate files written by ripper). They also share `PUID` for simplicity; Backend and UI use the same PUID/PGID but never write to user-facing volumes — DB state lives in the Postgres-managed volume, which doesn't need to match.
- The writing process runs with `umask 002` and the output roots (`/raw`, `/media`) have the `setgid` bit (`chmod g+s`) set on first boot, so every subdirectory ARM creates inherits the parent group and is group-writable. This is what fixes the "directories ARM creates are owned by root" failure mode.
- **v3 never `chown -R` a user-mounted volume.** If ownership is wrong at startup, the container logs a clear diagnostic and exits; it does not mutate the mount. This is the single biggest lesson from v2: recursive chown at startup clobbered user-owned Plex libraries (issue #1147), broke NFS mounts (#1186), and generated a long string of "fix permissions AGAIN" commits. v3 treats bind-mount ownership as user-owned state, not something the container manages.

**Host preparation (once, at install):**

- Create the `/raw` and `/media` host directories owned `PUID:PGID` with mode `2775` (setgid + group-writable). The installer does this.
- If using NFS, export with `no_root_squash` is **not** needed — ARM never writes as root. Export with a squash that maps to `PUID` is fine.
- If using SMB/CIFS from a NAS, mount with `uid=$PUID,gid=$PGID,forceuid,forcegid`. This works identically on Linux and Windows hosts (WSL2).
- For Windows hosts running the UI/transcoder stack: use a WSL2-native filesystem path, a named Docker volume, or an SMB mount. NTFS bind mounts from `C:\...` are unsupported — the translation layer ignores `chown`/`chmod` and PUID becomes cosmetic.

**Mismatched owners across `/raw` and `/media`:** common when `/raw` is local disk and `/media` is a NAS share — the underlying storage may belong to a different account on each host. The stack has one `PUID:PGID` for everything, so reconcile at the mount layer rather than asking the container to span two identities: SMB/CIFS with `uid=$PUID,gid=$PGID,forceuid,forcegid` rewrites every write to PUID on the wire regardless of the server-side account; NFS with idmapd (or a squash that maps to PUID) does the same. After that the container only ever sees PUID:PGID on both volumes and the asymmetry disappears. If you skip reconciliation, the startup ownership precondition fails fast on whichever volume doesn't match — by design, since v3 will not `chown -R` a user-mounted volume.

**Optical-drive device access:**

The ripper containers also need `group_add: ["${CDROM_GID}"]` so the PUID-dropped process can read `/dev/sr*`. `CDROM_GID` is the host's optical group GID (typically `44` for Debian/Ubuntu `cdrom`, sometimes `19` for Arch `optical`). The installer detects it via `stat -c %g /dev/sr0`. **No optical groups are hardcoded at image-build time** — a common v2 failure mode where the image's `cdrom` group had a different GID from the host's and the container couldn't read the drive.

## Privilege matrix

| Container | Privileged? | Socket / Devices | Notes |
|---|---|---|---|
| `arm-db` | no | — | Standard Postgres image. |
| `arm-backend` | no | `/var/run/docker.sock` | Root-equivalent on the host. Acceptable; documented. |
| `arm-ui` | no | — | Stateless. |
| `arm-ripper-*` | no | `/dev/sr*` | Drive exposed via compose `devices:` (no `--privileged`, no manual cgroup rules). Host's optical GID passed via `group_add: ["${CDROM_GID}"]` so the PUID-dropped process can read the device node. Nothing is hardcoded at image-build time. |
| `arm-transcode-*` | no | optionally `/dev/dri`, NVIDIA runtime | Transient. |

No `privileged: true` anywhere. If a ripper ever needs it for a weird host, we document that as an escape hatch but do not ship it on.

## Install

A single command bootstraps the whole stack:

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/v3/install.sh | bash
```

(Or `bash -c "$(curl -fsSL ...)"` for users who want a TTY; `install.sh --prefix /srv/arm` to override the default path.)

**What the installer does, in order:**

1. **Prereq check.** `docker` ≥ 24, `docker compose` v2, `openssl` ≥ 1.1.1, `bash` ≥ 4. User is in the `docker` group (or `sudo` usable), and in the host's optical group. Fails fast with a clear message if anything is missing.
2. **Create the install prefix** (`~/arm/` by default) with the layout shown above. Correct permissions on `certs/` (0700), `.env` (0600), and `raw`/`media` (2775 setgid). Run as the invoking user — no `sudo` needed if `~/arm/` is writable.
3. **Generate the internal CA** at `~/arm/certs/arm-ca.{key,crt}` (EC P-384, 10-year expiry, CN = "ARM v3 Local CA"). The key is `0400`, stays on the host, and is never mounted into any container.
4. **Probe for optical drives** via `ls /dev/sr* 2>/dev/null`; for each, generate a leaf cert (`arm-ripper-srN.{key,crt}`) signed by the CA. Also generate leaves for `arm-backend`, `arm-ui`, and `arm-db`. All leaves have a 10-year expiry. Leaf keys are written `0400` owned by the invoking user; the `arm-db` container re-permissions its leaf at startup via an entrypoint wrapper (see the compose block above) because Postgres refuses to read an SSL key not owned by the `postgres` user.
5. **Seed `~/arm/.env`** from a bundled template: `ARM_SERVICE_TOKEN` (`openssl rand -hex 32`), `POSTGRES_PASSWORD` (`openssl rand -hex 24`), `PUID=$(id -u)`, `PGID=$(id -g)`, `CDROM_GID=$(stat -c %g /dev/sr0)` (falls back to `44` if no drive is present). Third-party API keys are left blank for the user to fill via the UI later.
6. **Generate `~/arm/docker-compose.yml`** from a bundled template, emitting one `arm-ripper-srN` service block per detected drive (with the corresponding cert mounts). If no drives are detected, the stack still installs — only the ripper services are omitted — and a warning is printed.
7. **Print next steps.** Install location, `cd ~/arm && docker compose up -d`, where to find the admin password once Backend boots (`docker compose logs arm-backend | grep "admin password"`), and how to import `arm-ca.crt` into a browser/OS trust store to clear cert warnings on the LAN.

`install.sh --start` runs `docker compose up -d` at the end; the default is "show me the commands" so the user can inspect the generated files before starting anything.

**Idempotent rerun.** Re-running `install.sh` is safe and recommended when adding drives, upgrading across major versions, or recovering from local edits:

- Existing `.env` is preserved. Only `PUID`/`PGID`/`CDROM_GID` are re-derived from the host and overwritten if they drifted.
- Existing CA is preserved. `install.sh --rotate-ca` is a separate, explicit subcommand that regenerates the CA + all leaves (with a confirmation prompt — every client on the LAN needs to re-import the new `arm-ca.crt`).
- Newly-detected drives pick up new leaf certs and new service blocks appended to the compose file.
- Previously-removed drives leave their service blocks intact (inert when the device is absent) — the user explicitly deletes them if they want.

**First-boot sequence** (after `docker compose up -d`):

1. Backend starts, waits for Postgres, runs `alembic upgrade head`, seeds the `admin` user with a random password written to `/logs/first-boot.log` and printed to stdout.
2. User navigates to `https://host:8081`, accepts the internal-CA cert warning on first visit (or imports `~/arm/certs/arm-ca.crt` into the OS/browser trust store once to clear it for every device on the LAN — see [05-cross-cutting.md § Transport (TLS)](05-cross-cutting.md#transport-tls)), logs in as `admin` with the printed password, is forced to change it.
3. User enters third-party API keys in the UI → stored in `config`.
4. Rippers register themselves with Backend, appear in UI.
5. User inserts a disc; flow proceeds as documented in [02-job-lifecycle.md](02-job-lifecycle.md).

Post-cutover (when v2 is retired), the port moves back to 8080. Until then, 8081 avoids the v2 UI collision.

## Update / upgrade

- v3 images are tagged `docker.io/automaticrippingmachine/arm-<service>:v3.<x>.<y>`. Keeping the registry and namespace path from v2 so existing users don't have to follow a new identity.
- Upgrade a minor version = `cd ~/arm && docker compose pull && docker compose up -d`. Backend runs migrations; DB schema moves forward.
- Upgrade a major version = rerun `install.sh` to pick up any new service blocks or cert SANs the release requires, then `docker compose pull && docker compose up -d`.
- **No rollback of DB schema.** Alembic `downgrade` is not supported past minor versions — back up the DB if paranoid.

## Uninstall

```bash
cd ~/arm && docker compose down
rm -rf ~/arm
```

That's it. No systemd units, no distro integration, no state anywhere else on the host.

## Backup

Four things to back up, in priority order:

1. **`~/arm/certs/arm-ca.key`.** Unique-per-install and unrecoverable. If lost, the user has to rotate the CA and re-import on every LAN client — recoverable but annoying.
2. **Postgres dump.** `pg_dump` from a cron against the `armv3-db` container; ARM doesn't manage this. Contains plaintext secrets — store the dump somewhere you'd trust with a password export.
3. **`~/arm/.env`.** Useful for reproducing a deployment quickly; losing it just means regenerating `ARM_SERVICE_TOKEN` and the DB password (which then requires restoring the Postgres dump with matching credentials, or renaming the DB user).
4. **`~/arm/raw` and `~/arm/media`.** User's responsibility; these are large and the user knows their own backup strategy.

`~/arm/docker-compose.yml` is regeneratable by rerunning `install.sh` against the same `.env` and `certs/`, so it doesn't strictly need a backup.

## Platform-specific notes

- **Unraid**: Users can define the compose stack via the Compose Manager plugin. Drive pass-through works via device mappings. Put `arm_raw` / `arm_media` on the array; `arm_db_data` on an SSD cache.
- **Synology**: Use Container Manager / Portainer.
- **Bare-metal**: The reference path. All docs default to this.
