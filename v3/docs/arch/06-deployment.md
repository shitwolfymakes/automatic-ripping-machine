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

## Compose topology

All v3 assets live under `v3/`. Users bring up the stack with:

```bash
docker compose -f v3/docker-compose.yml --env-file v3/.env up -d
```

During development, v2 continues to run from the root `docker-compose.yml` on port 8080; v3 runs from `v3/docker-compose.yml` on port 8081. They share a host but not volumes, container names, project names, or any other compose-level resource (see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) for how collisions are avoided).

The file `v3/docker-compose.yml` declares all v3 services. Users edit it to add ripper services for each drive they have.

```yaml
name: armv3   # compose project name; keeps container/volume names distinct from v2

services:
  arm-db:
    image: postgres:18
    container_name: armv3-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - armv3_db_data:/var/lib/postgresql/data

  arm-backend:
    build: ./services/backend
    container_name: armv3-backend
    restart: unless-stopped
    depends_on: [arm-db]
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@arm-db:5432/${POSTGRES_DB}
      ARM_SERVICE_TOKEN: ${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: ${ARM_LOG_LEVEL:-info}
      PUID: ${PUID:-1000}
      PGID: ${PGID:-1000}
    volumes:
      - armv3_raw:/raw
      - armv3_media:/media
      - armv3_logs:/logs
      - /var/run/docker.sock:/var/run/docker.sock   # for spawning arm-transcode

  arm-ui:
    build: ./services/ui
    container_name: armv3-ui
    restart: unless-stopped
    depends_on: [arm-backend]
    ports:
      - "8081:80"   # v3 on 8081; v2 stays on 8080 during co-existence

  arm-ripper-sr0:
    build: ./services/ripper
    container_name: armv3-ripper-sr0
    restart: unless-stopped
    depends_on: [arm-backend]
    devices:
      - "/dev/sr0:/dev/sr0"
    group_add:
      - "${CDROM_GID:-44}"   # host's optical group GID so PUID-dropped process can read /dev/sr0
    environment:
      ARM_DRIVE_DEV: /dev/sr0
      ARM_BACKEND_URL: http://arm-backend:8000
      ARM_SERVICE_TOKEN: ${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: ${ARM_LOG_LEVEL:-info}
      PUID: ${PUID:-1000}
      PGID: ${PGID:-1000}
    volumes:
      - armv3_raw:/raw
      - armv3_logs:/logs

  # Users copy-paste this block for each additional drive, changing :sr0 → :sr1 etc.
  # arm-ripper-sr1:
  #   …

volumes:
  armv3_db_data:
    driver: local
    driver_opts:
      type: none
      device: /arm/db/postgres_v3   # path on host
      o: bind
  armv3_raw:
  armv3_media:
  armv3_logs:
```

The `armv3_` prefix on volumes and `armv3-` prefix on container names guarantee zero collision with v2 containers (which use `arm_`/`arm-` names). The compose `name: armv3` sets the project namespace so `docker compose ls`, `docker compose down`, and `docker volume ls` all show v3 and v2 as distinct projects.

Note that v2 may be simultaneously bound to `/dev/sr0`. If you want to run a real v3 rip, stop v2 first — the kernel permits multiple containers to map the same device but MakeMKV won't play nicely with the disc being used by two processes. This is the one unavoidable resource conflict and it only matters during the transition period.

Transcode services are NOT declared in compose — they are spawned dynamically by the Backend via Docker socket.

## Why one ripper service per drive

Ripper-per-drive is explicit and declarative: users see which drives they have by reading compose, device pass-through is one line per service, and a failing ripper doesn't take down its siblings. Each ripper watches its own drive via a 2s `ioctl(CDROM_DRIVE_STATUS)` poll — no udev rules on host or in container, no distro-specific wiring. This is the trade-off we accepted vs. dynamic ripper spawning — one line of config per drive is a small price for "it's all visible in one file."

If a user has drives `sr0` and `sr1` they duplicate the ripper block twice. There is no "cluster of interchangeable rippers" — each ripper owns one physical device.

## Environment file

`v3/.env` (next to `v3/docker-compose.yml`) holds the bootstrap values. Users don't hand-edit during normal install; an install script generates sensible defaults:

```bash
POSTGRES_USER=arm
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=arm
ARM_SERVICE_TOKEN=<generated: openssl rand -hex 32>
PUID=1000          # UID that owns files written to /raw and /media
PGID=1000          # GID shared by ripper and transcoder
CDROM_GID=44       # host's optical group GID; installer detects via `stat -c %g /dev/sr0`
```

The compose file composes `DATABASE_URL` from these for the Backend:

```yaml
environment:
  DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@arm-db:5432/${POSTGRES_DB}
  ARM_SERVICE_TOKEN: ${ARM_SERVICE_TOKEN}
```

`v3/.env` is gitignored (a dedicated entry is added to the root `.gitignore` — see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) for the exact additive rule). `v3/devtools/arm-init` generates a fresh one on a clean host. A `v3/.env.example` is committed to the repo as a template for users who prefer to hand-initialize.

`.env` plus the committed `v3/docker-compose.yml` is the **only** thing that changes between deployments. Updates ship by pulling new images and running `docker compose up -d`; the compose file changes with the release and the user's `.env` is untouched.

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

## First-boot sequence

1. User clones repo, runs `v3/devtools/arm-init` → generates `v3/.env` and a ripper service per detected `/dev/sr*` in `v3/docker-compose.yml`.
2. User runs `docker compose -f v3/docker-compose.yml up -d`.
3. Backend starts, waits for Postgres, runs `alembic upgrade head`, seeds `admin` user with a random password that is printed to stdout + written to `/logs/first-boot.log`.
4. User navigates to `http://host:8081`, logs in as `admin` with the printed password, is forced to change it.
5. User enters third-party API keys in UI → stored in `config`.
6. Rippers register themselves with Backend, appear in UI.
7. User inserts a disc; flow proceeds as documented in [02-job-lifecycle.md](02-job-lifecycle.md).

Post-cutover (when v2 is retired), the port moves back to 8080 and the `-f v3/docker-compose.yml` path goes away. Until then, 8081 avoids the v2 UI collision.

## Update / upgrade

- v3 images are tagged `ghcr.io/automatic-ripping-machine/arm-<service>:v3.<x>.<y>`.
- Upgrade = pull new images, `docker compose up -d`. Backend runs migrations; DB schema moves forward.
- **No rollback of DB schema.** Alembic `downgrade` is not supported past minor versions — back up the DB if paranoid.

## Backup

Three things to back up, in priority order:

1. **Postgres dump.** `pg_dump` from a cron; ARM doesn't manage this, user does. Contains plaintext secrets — store the dump somewhere you'd trust with a password export.
2. **`.env`.** Useful for reproducing a deployment quickly; losing it just means regenerating `ARM_SERVICE_TOKEN` and the DB password (which then requires restoring the Postgres dump with matching credentials, or renaming the DB user).
3. **`/raw` and `/media`.** User's responsibility; these are large and the user knows their own backup strategy.

Compose-level metadata (compose file itself) is in-repo, no backup required beyond standard git.

## Platform-specific notes

- **Unraid**: Users can define the compose stack via the Compose Manager plugin. Drive pass-through works via device mappings. Put `arm_raw` / `arm_media` on the array; `arm_db_data` on an SSD cache.
- **Synology**: Use Container Manager / Portainer.
- **Bare-metal**: The reference path. All docs default to this.
