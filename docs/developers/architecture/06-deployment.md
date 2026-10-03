# 06 — Deployment

Docker Compose is the one and only supported deploy target for v3.

## Supported targets

- Any Linux host running Docker Engine ≥ 24 and Compose v2 ≥ 2.20 (Ubuntu, Debian, Fedora, Arch, …). This is the **one and only** supported target for v3.0; container deployment is distro-agnostic.

## Explicitly NOT supported

- Unraid, Synology DSM, QNAP, and other NAS-appliance container GUIs. They run stock Docker, so the generic Linux + Compose path may happen to work, but it is **untested and unsupported** for v3.0 — deploy via the documented `install.sh` + `docker compose` path or not at all. (Dropped 2026-06-05.)
- TrueNAS / iX Systems. Not a goal. Do not file bugs against it.
- Kubernetes / Helm.
- Docker Desktop on macOS/Windows **for ripping**. Internal SATA optical drives cannot be passed to the WSL2/macOS VM; USB drives via `usbipd-win` may work but are not tested. Windows and macOS users can still run the UI + transcoder stack as a library-management frontend (PUID/PGID works correctly on WSL2-native paths, named volumes, and SMB mounts — see "File ownership" below). NTFS bind mounts from `C:\...` are unsupported: the translation layer fakes ownership and ignores `chown`, so PUID becomes cosmetic.
- Podman (may work by accident; not tested).

## Install prefix and layout

The installer (see [§ Installer](#installer)) puts everything under a single folder, **`~/arm/` by default**. The user never clones the repo, never runs a build, never reads source. The stack is entirely image-based.

```
~/arm/
├── armctl                          # launcher (see § Installer)
├── .armctl/
│   ├── .env                        # 0600 — generated; user edits optional fields
│   ├── host-overlay.yml            # generated: storage locations, offload settings
│   ├── lock                        # held while an armctl command runs
│   ├── releases/<tag>/             # the unpacked release bundle (compose template, overlay, scripts)
│   └── current -> releases/<tag>
├── certs/                          # 0700
│   ├── arm-ca.key                  # 0400 — CA private key; NEVER mounted into a container
│   ├── arm-ca.crt                  # 0444 — mounted read-only into every service
│   ├── arm-backend.{key,crt}       # leaf for Backend
│   └── arm-ui.{key,crt}            # leaf for UI nginx
├── db/                             # Postgres data (bind-mount)
├── logs/                           # shared logs (PUID:PGID)
├── backups/                        # database backups from armctl up / upgrade (newest five kept)
├── scripts/                        # notification scripts, mounted read-only into the backend
├── iso-library/                    # disc images for Rip from ISO
├── ssh/                            # offload profile only
├── raw/                            # rip output (PUID:PGID, 2775 setgid)
└── media/                          # transcoded library (PUID:PGID, 2775 setgid)
```

The user runs the stack with `armctl up`. The template's bind-mounts are written as `./arm/...` and `armctl` runs Compose from the folder that contains `arm`; `--prefix /srv` gives `/srv/arm`. Nothing is hard-coded to `$HOME`.

## Build chain

v3 images are built fresh on upstream bases. They do **not** derive from the v2 `arm-dependencies` image, do **not** pull from the `arm-dependencies` submodule, and do **not** inherit `phusion/baseimage`.

- **No `arm-dependencies`.** That image existed to bake HandBrake / MakeMKV / libdvd-pkg on top of a shared phusion base for the v2 all-in-one container. v3 splits those workloads across separate images (only `arm-ripper` and `arm-transcode` need MakeMKV/HandBrake), so the shared dependency layer isn't shared enough to justify a submodule. The `arm-dependencies` submodule stays in the repo untouched through v3 development and is deleted in the cutover PR — see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md).
- **No `phusion/baseimage`.** phusion was adopted in v2 to get multi-service supervision (`/sbin/my_init` + `/etc/service/` runit) inside one container. v3's topology is one long-running process per container (UI = nginx, Backend = uvicorn, Ripper = the drive poller, Transcode = HandBrake — all PID-1-appropriate), so the entire reason phusion was chosen no longer applies. Dropping it removes a stack of v2 friction: the UID-unsettable limitation and its UID/GID remap dance, the `start_udev.sh` "job control turned off" noise in every bug report, the ~1 GB base-image bloat, and the two-repo version-bump tax that the submodule coupling created. Replacement bases are per service:
  - `arm-ui` → `nginx:alpine` (built from `services/ui-neu/`), PID 1 = the nginx master (handles signals natively, no grandchild forks).
  - `arm-backend` → `python:3.14-slim-bookworm`, PID 1 = `tini` → `uvicorn`.
  - `arm-ripper` → `python:3.14-slim-bookworm`, PID 1 = `tini` → poller.
  - `arm-transcode` → `python:3.14-slim-trixie` (Debian 13, for Intel Arc Battlemage QSV support), PID 1 = `tini` → HandBrake/ffmpeg wrapper. Its `services/transcode/Dockerfile` builds three targets from one common base: `base` (CPU encoders plus NVENC, which needs nothing baked in beyond the HandBrake build), `intel` (adds the Intel VAAPI/oneVPL packages for QSV), and `amd` (adds Mesa's VAAPI driver for the ffmpeg AMD path). The compose file builds and tags all three (`arm-transcode`, `arm-transcode-intel`, `arm-transcode-amd`, all `deploy.replicas: 0`); the Backend picks the variant matching a claimed GPU's vendor by tag suffix (`-intel` / `-amd`), pulling it on demand if missing, and falls back to `base` when a variant can't be found or pulled. See [Hardware Transcoding § Image variants](../../user/Hardware-Transcoding.md#image-variants) for the naming convention and overrides.

  `tini` is baked into the Python images rather than relying on `docker run --init`, since not every Docker UI or orchestrator consistently surfaces that flag. It reaps the zombie `makemkvcon` / `HandBrakeCLI` / `ffmpeg` subprocesses the ripper and transcode containers fork. The UI spawns no grandchildren, so nginx as PID 1 is sufficient. The common PUID-remap + CA-merge + privilege-drop logic is a ~25-line `docker-entrypoint.sh` stored at `services/_common/docker-entrypoint.sh` and `COPY`ed into each Python image — a shared script, deliberately not a shared base image (a shared base was the `arm-dependencies` coupling we left behind). Hardened vendor bases (Chainguard, distroless, Bitnami Secure, Red Hat UBI Micro) were considered and rejected: paid tiers introduce a gated supply chain at odds with anonymous `docker pull` distribution; free/distroless tiers have no shell, which breaks the runtime CA merge + PUID remap + `gosu` pattern; and the threat model (LAN-only, internal CA, no internet-exposed services) doesn't justify the tradeoff. Supply-chain hygiene is added on top of the minimal bases instead (see the next bullet).
- **Supply-chain hygiene.** Minimal bases without vendor hardening means hardening is done at publish time with free open-source tooling:
  - **Pin bases by digest.** Dockerfiles reference `FROM python:3.14-slim-bookworm@sha256:...`, not floating tags. Renovate (or Dependabot) opens a PR when the upstream digest for the pinned tag changes.
  - **SBOM per image.** `syft` generates an SPDX SBOM at build time; `cosign attach sbom` publishes it alongside the image in the registry.
  - **Cosign-signed images.** Every published image is signed via Sigstore's keyless flow (OIDC from the GitHub Actions runner → short-lived Fulcio cert → Rekor transparency log). Users can verify with `cosign verify docker.io/automaticrippingmachine/arm-<service>:v3.x.y --certificate-identity=... --certificate-oidc-issuer=https://token.actions.githubusercontent.com`. No long-lived signing keys to manage.
  - **Weekly base rebuild.** A scheduled CI job rebuilds each image weekly on its current tag so Debian's security updates land without waiting for the next ARM release.
- **Each service has its own Dockerfile under `services/<service>/Dockerfile`.** Shared Python code (schemas, clients) lives in `packages/arm_common/` and is installed into each image by the build, not mounted at runtime — there is no v2-style `PYTHONPATH=/opt/arm` shim.
- **Nothing compiles on the host.** The installer (see [§ Installer](#installer)) only pulls pinned images from `docker.io/automaticrippingmachine/`. Contributors building locally use `docker compose -f docker-compose.yml build`; end users never do.

## Compose topology

In production the stack is `docker-compose.yml.example` layered with the release overlay, which names pinned images from `docker.io/automaticrippingmachine/`; the template bind-mounts paths under the install folder. Nothing is built or compiled on the host.

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
      - "8081:443"   # UI over TLS
    volumes:
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ui.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ui.key:/etc/ssl/arm/tls.key:ro

  arm-ripper:
    image: ${ARM_RIPPER_IMAGE:-docker.io/automaticrippingmachine/arm-ripper:v3.0.0}
    build:
      context: .
      dockerfile: services/ripper/Dockerfile
    deploy:
      replicas: 0   # built by `docker compose up -d --build`; never started here
```

The `armv3-` prefix on container names and `name: armv3` project namespace guarantee zero collision with v2 containers (which use `arm-` names) so `docker compose ls`, `docker compose down`, and `docker volume ls` all show v3 and v2 as distinct projects. One exception: containers the backend creates for enrolled drives (see below) are named `arm-ripper-<serial>` without the `armv3-` prefix — they're created over the docker socket, not by compose, so they sit outside the `armv3` compose project namespace.

### Rippers are created by the backend, not by compose

There is no per-drive compose service. `docker compose up -d --build` builds the
`arm-ripper` image (the service has `deploy.replicas: 0`, like `arm-transcode`)
and starts nothing from it. On boot the backend scans `/sys/class/block/sr*` +
`/dev/disk/by-id` (mounted read-only at `/host-disk`) and lists every optical
drive on the **Drives** page as *detected*. Enrolling a drive there makes the
backend create one durable container `arm-ripper-<serial>` for it over the
docker socket:

- label `arm.drive_id=<id>` (the tracking key), `restart: unless-stopped`;
- `device_cgroup_rules: ["b 11:* rmw", "c 21:* rmw"]` — the ripper's entrypoint
  pre-creates `/dev/sr0..7` and `/dev/sg0..15` itself, so there is no `devices:`
  bind and the container survives unplug/replug and renumbering;
- env `ARM_DRIVE_ID`, `ARM_DRIVE_BY_ID` (the udev by-id link it follows),
  `ARM_DRIVE_DEV` (current node — a hint), backend URL + service token,
  `PUID/PGID/CDROM_GID`, and any `ARM_RIPPER_*` tunables from `.env`;
- mounts the `ARM_HOST_RAW_PATH` / `ARM_HOST_LOGS_PATH` host paths (which the
  install layout resolves to `./arm/raw`, `./arm/logs`), `arm-ca.crt:ro`,
  `/dev/disk:/host-disk:ro`.

Unenroll stops and removes the container. On every backend boot the `drives`
table is reconciled against the labelled containers: missing → created, exited
→ started, orphan → removed, and a container running an image that no longer
matches `ARM_RIPPER_IMAGE` is recreated when the drive is idle. These
containers are **outside the compose project** — `docker compose down` leaves
them (`armctl down` removes them); `bash devtools/ripper-containers.sh {list|stop|remove}` manages them.

Each service container, on startup, copies the mounted `/etc/ssl/arm/arm-ca.crt` into `/usr/local/share/ca-certificates/` and runs `update-ca-certificates`. This merges the per-install internal CA with the base image's Mozilla root bundle, so outbound HTTPS (TMDB, OMDB, Apprise) verifies against public roots and inbound/intra-compose HTTPS verifies against the internal CA — all via the default system trust store, no per-client `verify=` plumbing in application code. See [05-cross-cutting.md § Transport (TLS)](05-cross-cutting.md#transport-tls) for the full cert layout and rationale.

Note that v2 may be simultaneously bound to `/dev/sr0`. If you want to run a real v3 rip, stop v2 first — the kernel permits multiple containers to map the same device but MakeMKV won't play nicely with the disc being used by two processes. This is the one unavoidable resource conflict and it only matters during the transition period.

Transcode services are NOT declared in compose — they are spawned dynamically by the Backend via Docker socket.

### SCSI-generic pairing

Each ripper container needs **both** the block device (`/dev/srN`) **and** its matching SCSI-generic node (`/dev/sgM`). MakeMKV enumerates drives via SG ioctls, not by opening the block device — without the sg node, `makemkvcon info` returns `Unknown device - '/dev/srN'` and zero titles. The ripper's scan dispatcher silently falls through to the data-disc fallback in that case, so the failure mode is "every disc looks unidentifiable" rather than a clean error.

The pairing isn't lexicographic — `sr0` does **not** automatically pair with `sg0`. Find the matching node from the kernel device tree:

```sh
ls /sys/class/block/sr0/device/scsi_generic/   # → e.g. "sg5"
```

Rippers no longer need this pairing done for them: the `arm-ripper-<serial>` container's entrypoint pre-creates `/dev/sr0..7` and `/dev/sg0..15` itself (via `device_cgroup_rules`, not per-node `devices:` binds), so it can follow the kernel's own `sr`↔`sg` pairing at runtime instead of a compose author working it out at install time — see [§ Rippers are created by the backend, not by compose](#rippers-are-created-by-the-backend-not-by-compose) above.

### Host-side auto-mount must be disabled

Desktop hosts (any with a GNOME / KDE / XFCE session) run `udisks2` + `gvfs` to auto-mount removable media as soon as the kernel sees a new disc. That host-side mount holds `/dev/srN` exclusively — the ripper container can scan and rip (`makemkvcon` opens the SCSI generic node, not the block device), but **post-rip `eject` fails with "Device or resource busy"** because the container can't reach the host's mount namespace to unmount first. The ripper logs `eject /dev/srN failed after 4 attempts; check host auto-mount config` and the disc stays in the drive until the user manually ejects.

Server / headless installs do not have this problem (no `udisks2` running, no `gvfs`). Desktop hosts need a one-time host config change to disable auto-mount for optical drives (non-optical media untouched; other optical drives stay visible and manually mountable). The canonical udisks2 knob for this is `UDISKS_AUTO=0` ([udisks(8)](https://manpages.debian.org/trixie/udisks2/udisks.8.en.html)) — the drive stays visible in Files / Nautilus and the user can still mount it on demand, but the desktop's auto-mounter skips it on insert.

The rule is host-wide rather than scoped to a specific drive by `ID_PATH`/`ID_SERIAL`, because drives are hot-plugged and enrolled from the UI *after* install — there is no fixed drive list at install time to scope the rule to. ARM owns the optical drives on its host, so the installer (and `devtools/setup-dev.sh` for contributors) writes one rule that covers every `sr*` node:

```sh
# /etc/udev/rules.d/99-arm-no-automount.rules
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"
```

Reload with `sudo udevadm control --reload-rules && sudo udevadm trigger`. After this, eject from inside the ripper container succeeds normally.

Why `UDISKS_AUTO=0` and not `UDISKS_IGNORE=1`: the latter hides the drive from the udisks2 device tree entirely (no entry in Files, no `udisksctl status` row), which is friendlier to set-it-and-forget-it server installs but breaks the desktop user's expectation that they can still browse the disc manually. `UDISKS_AUTO=0` is the documented per-device "skip auto-mount" toggle. Why a host-side rule instead of bind-mounting the host's DBus into the container: DBus passthrough adds a runtime dependency that fails open on headless hosts (no `udisks2` running) and ties container behaviour to the host's session bus — fragile across distros and reboots. Why not raw SCSI eject through `/dev/sgM`: `udisks2` sets PREVENT MEDIUM REMOVAL on mount, the drive firmware refuses STOP UNIT until ALLOW is sent, and even on success the host's `/media/<label>/` mountpoint stays stale and races the next disc insertion. Multiple containerized rip projects ([jlesage/docker-makemkv #84](https://github.com/jlesage/docker-makemkv/issues/84), [#138](https://github.com/jlesage/docker-makemkv/issues/138), [ARM v2 #1558](https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues/1558)) hit this same wall and none of them solve it in-container — the host-udev approach is the converged industry pattern.

## Why one ripper container per drive

One drive is one process is one crash domain: a failing ripper doesn't take down its siblings, and each container holds its own MakeMKV SCSI handle on its own device rather than multiplexing several drives through one process. Logs stay per-drive too — one JSONL stream per container, not an interleaved shared one. Each ripper watches its own drive via a 2s `ioctl(CDROM_DRIVE_STATUS)` poll.

The container itself isn't declared in compose, though — it's created by the backend when a drive is enrolled, not hand-written per drive. See [§ Rippers are created by the backend, not by compose](#rippers-are-created-by-the-backend-not-by-compose) above.

## Environment file

`~/arm/.armctl/.env` holds bootstrap values. The installer generates it with sensible defaults; the user edits only the optional fields (API keys, non-default ports) — and even those are primarily set via the UI, not the env file.

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

`~/arm/.armctl/.env`, the release bundle under `~/arm/.armctl/releases/` and the generated host overlay are all a running install depends on. Running `armctl install` again on an existing install keeps the secrets and the CA, takes the earlier answers as defaults, and refreshes detected host facts such as `PUID`/`PGID`/`CDROM_GID` and the GPUs. Upgrades come from `armctl upgrade`, which moves the pinned image tag, not from editing `.env`.

## File ownership

v3 uses the linuxserver.io-style `PUID`/`PGID` pattern to keep files on `/raw` and `/media` owned by a UID/GID the user controls — typically matching their media server (Plex/Jellyfin) so downstream consumers can read the files without any post-hoc `chown`.

**How it works:**

- Each service's entrypoint starts as root, creates (or adjusts) an internal user to match `PUID:PGID` from the environment, then `gosu`/`s6-setuidgid` drops privileges before any filesystem write. Every byte ARM writes is owned by `PUID:PGID`.
- Ripper and transcoder share `PGID` so group-writable handoff on `/raw` works (transcoder reads + deletes intermediate files written by ripper). They also share `PUID` for simplicity; Backend and UI use the same PUID/PGID but never write to user-facing volumes — DB state lives in the Postgres-managed volume, which doesn't need to match.
- The writing process runs with `umask 002` and the output roots (`/raw`, `/media`) have the `setgid` bit (`chmod g+s`) set on first boot, so every subdirectory ARM creates inherits the parent group and is group-writable. This is what fixes the "directories ARM creates are owned by root" failure mode.
- **v3 never `chown -R` a user-mounted volume.** If ownership is wrong at startup, the container logs a clear diagnostic and exits; it does not mutate the mount. This is the single biggest lesson from v2: recursive chown at startup clobbered user-owned Plex libraries (issue #1147), broke NFS mounts (#1186), and generated a long string of "fix permissions AGAIN" commits. v3 treats bind-mount ownership as user-owned state, not something the container manages. ARM-owned Docker named volumes are different: the `arm-data` volume (backend `/data`: TheDiscDB snapshot, poster cache) holds only state ARM created, so the one-shot `arm-data-init` compose service re-owns it to `PUID:PGID` as root before `arm-backend` starts (only when the top-level owner differs), while every user bind mount stays verify-only.

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

## Installer

Production runs `docker-compose.yml.example` exactly as committed, layered with `deploy/docker-compose.release.yml` and a generated host overlay; nothing translates the template.

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
```

### The pieces and where they live

| Path | Role |
|---|---|
| `install.sh` (root) | Bootstrap only. Run from a checkout, it packs a bundle from that checkout (`deploy/build-bundle.sh`, tagged `v<VERSION>` unless `--version` says otherwise) instead of downloading one. Run from curl, it picks the release and downloads that release's bundle. Either way it unpacks the bundle into the install folder, writes the `armctl` launcher and hands over to `armctl install`. |
| `deploy/armctl.sh` | The release's command: `install`, `up`, `down`, `upgrade`, `compose ...`. |
| `deploy/lib/` | Shared by dev and production: host detection, certificates, the udev rule and the lifecycle safety steps. `devtools/setup-dev.sh` loads the same files. |
| `deploy/install/` | Production-only: Docker and NVIDIA setup, prompts, storage locations, offload walkthrough, PATH link. |
| `deploy/docker-compose.release.yml` | The overlay naming release images for the services dev builds from source. |
| `docker-compose.yml.example`, `.env.example` | Shipped unchanged. Copied into the bundle as they are. |
| `.github/workflows/release.yml` | A job packs the bundle (`deploy/build-bundle.sh`) and attaches it to the GitHub release. |

**The bundle** is `armctl.sh`, `deploy/lib/`, `deploy/install/`, the release overlay, the two unchanged template files and a version marker, packed as one archive with a checksum file beside it. Nothing in it is generated except the version marker.

**Host layout:**

```
~/arm/
  armctl                      small launcher that runs .armctl/current/armctl.sh; also linked onto the PATH
  certs/ db/ raw/ media/ logs/ backups/ scripts/ iso-library/
  ssh/                        offload profile only
  .armctl/
    .env                      secrets, pins, profile, detected values
    host-overlay.yml          generated: storage locations, offload settings
    lock                      held while an armctl command runs
    releases/<tag>/           one unpacked bundle per installed release
    current -> releases/<tag>
```

The folder must be named `arm`, because the template writes its paths as `./arm/...` and `armctl` runs Compose from the folder that contains `arm`. The location option therefore names where the `arm` folder goes: the default gives `~/arm`, and `--prefix /srv` gives `/srv/arm`.

Folder permissions: `certs` and `.armctl` are 0700; `logs` is 2775 (setgid, group-writable). `raw` and `media` are created by the storage step and get 2775 only when they sit inside the `arm` folder; a location the user points at elsewhere keeps its own mode.

### The compose stack in production

`armctl` always runs Compose with three files, in this order:

1. `docker-compose.yml.example` from the bundle, byte-identical to the committed file.
2. `docker-compose.release.yml`: adds `image:` for the services the template only builds (`arm-backend`, `arm-data-init`, `arm-ui`), using `ARM_IMAGE_PREFIX` and `ARM_IMAGE_TAG`.
3. `host-overlay.yml`: generated per install.

It also passes the project directory (the folder containing `arm`) and the `.env` path, and uses `up --no-build`.

The ripper and transcode images are already variables in the template (`ARM_RIPPER_IMAGE`, `ARM_TRANSCODE_IMAGE`, `ARM_TRANSCODE_IMAGE_QSV`, `ARM_TRANSCODE_IMAGE_VAAPI`, `ARM_TRANSCODE_IMAGE_NVENC`). The installer writes them to `.env` from the prefix and tag. Variant tags follow `release.yml`: `arm-transcode:<tag>`, `arm-transcode:<tag>-intel`, `arm-transcode:<tag>-amd`.

**Why this needs no translation.** A new environment variable, mount or setting added to the template reaches production on the next release with no further work, because production runs the template itself. One residual case: a brand-new service that dev builds from source needs one `image:` line in the release overlay. `deploy/tests/test-stack-contract.sh` fails if any service in the layered production config has no release image.

**The host overlay** is generated by `armctl install` from the saved answers. It holds only:

- **Storage locations**: the `/raw` and `/media` mounts on `arm-backend`, always written with the chosen locations (the defaults sit inside the install folder). The matching `ARM_HOST_RAW_PATH` and `ARM_HOST_MEDIA_PATH` go into `.env` so spawned containers mount the same places.
- **Offload** (offload profile only): the published callback port for `arm-backend` (container port 8443) and the read-only mount of `~/arm/ssh` at `/home/arm/.ssh`.

**`.env` values that are always explicit.** The template defaults `ARM_HOST_RAW_PATH`, `ARM_HOST_MEDIA_PATH`, `ARM_HOST_LOGS_PATH` and `ARM_HOST_CERTS_PATH` from `${PWD}`, which is the directory Compose was invoked from. `armctl` can be run from anywhere, so the installer always writes absolute values for these. The template sets `name: armv3`, so the project name and the default network (`armv3_default`) do not depend on the folder Compose runs from.

### Install flow

**Bootstrap (`install.sh`).**

1. Refuses to run as root, and checks that `curl`, `tar` and `sha256sum` exist.
2. Reads the location and release options and passes every other flag through.
3. Works out the `arm` folder: `--prefix` names the folder it goes in (`--prefix /srv` gives `/srv/arm`; a prefix that already ends in `arm` is taken to be the folder itself), and the default is `~/arm`. It refuses an existing folder that has files in it but no `.armctl` folder, because ARM v3 installs fresh and does not convert an ARM v2 folder or an install made by the old v3 installer.
4. Picks the release. From a checkout it packs a bundle from the checkout instead (see above). Otherwise it uses the named version, or the latest stable on the v3 line. A `--version` tag must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.
5. Fetches the bundle and its checksum into a staging folder, verifies the checksum, rejects an archive with unsafe paths, and only then unpacks it under `.armctl/releases/<tag>/`, sets `current` and writes `armctl`. A failed bootstrap leaves the target location exactly as it was.
6. Hands over to `armctl install` with the terminal attached (it reads `/dev/tty` when stdin is the script), so prompts work under a curl pipe.

`--bundle <file>` (with `--version`; the `.sha256` file must sit beside it) uses a local bundle instead of a download. That is what the install drill uses.

**`armctl install`, in eight stages**, in the order `deploy/install/flow.sh` runs them:

1. **Profile**: full box, ripper-only or remote offload. It comes first because the answer is known before a possible restart of the command under the `docker` group (stage 2), and is carried across that restart so the question is not asked twice.
2. **Host**: checks Docker (installed, version 24 or newer, compose plugin, running daemon, group membership) and fixes what it can with consent; it automates only Debian and Ubuntu. Also takes the lock, checks for `openssl` and creates the folder layout.
3. **Storage**: asks for the raw and media locations, creates them, checks they are writable.
4. **Remote transcode offload**: runs the offload walkthrough (`deploy/install/offload.sh`) for the offload profile; for any other profile it prints "not used by the <profile> profile".
5. **Certificates**: the CA once, then backend, database and UI leaves. The backend's leaf carries the offload address when relevant.
6. **Configuration**: writes `.env` (secrets generated once, ids and GPUs detected, release pinned, profile recorded, `ARM_TRANSCODE_CAPABLE` set from the profile) and the host overlay. Offers the NVIDIA toolkit on the full profile when an NVIDIA GPU is found, offers the udev rule, and offers the PATH link (`~/.local/bin` when it is on the PATH, otherwise `/usr/local/bin` with sudo).
7. **Start**: runs the same path as `armctl up`, including the health wait. On by default; `--no-start` skips it.
8. **Finish**: the offload verification table when relevant, then the summary: the URL (`https://localhost:8081`), the first-login command, the certificate-trust hint, the everyday commands and any steps that were skipped.

**Re-running `armctl install`.** Secrets and the CA are kept. Earlier answers become the defaults, and a run with no terminal keeps them. Detected values (GPUs, group ids) are refreshed. The profile is remembered. This differs from dev, where `--ripper-only` applies per run, and the difference is deliberate: a non-developer should not have to repeat it on every command.

**Flags.** `armctl install --help` lists them: `--profile`, `--raw-path`, `--media-path`, `--yes`, `--no-host-changes`, `--no-start`, `--rotate-ca`, `--image-prefix`, `--release-repo`, and the offload inputs. The bootstrap adds `--prefix`, `--version`, `--release-repo` and `--bundle` and passes the rest through. An unattended offload install can supply the inputs, but the commands pasted on the remote host stay manual. The run verifies each step and reports what is missing.

### Lifecycle commands

**`armctl up`** follows the same order as `setup-dev.sh up`, with pulling in place of building:

1. **Pull** the images this host needs: the base transcode image unless the profile is ripper-only, the Intel or AMD variants only when that GPU is present, and no variants when transcodes are offloaded (`--no-pull` skips the pull). A failed pull stops here with the running stack untouched. A check that every needed image is present on the host follows, and stops the same way.
2. **Guard**: refuses while a rip or transcode is active, unless `--force`.
3. **Refresh** the detected GPUs in `.env`.
4. **Back up** the database into `~/arm/backups/`, keeping the newest five. `--no-backup` skips it.
5. **Remove** the spawned rippers and transcoders, and containers of retired services.
6. **Start** from the pulled images, and recreate rippers if the backend kept running.
7. **Wait** up to 90 seconds for the backend's health check, then print the URL.

**`armctl upgrade [--version <tag>]`:**

1. Picks the target: the latest stable v3, or the named version. If the install is already on it, it says so and stops. If `.env` and the `current` link name different releases (an upgrade stopped during the switch), it says what it found and runs the upgrade again to finish it, reusing the bundle that is already unpacked.
2. Downloads, verifies and unpacks the new bundle beside the current one. Nothing live has changed yet.
3. Hands over to the new release's `armctl`, which pulls the new images, runs the guard and takes the backup. Still nothing live has changed.
4. Switches: first points `current` at the new release in one step (a new link renamed over the old one), then replaces `.env` with the candidate that records the new version and any new settings with their defaults. If `.env` cannot be replaced, `current` is put back and the install stays on the old release.
5. Removes spawned containers, starts, recreates rippers, waits for health.

The previous release's folder is kept for a manual rollback. Older ones are pruned after a successful upgrade.

**`armctl down`** refuses while a rip or transcode is active, unless `--force`. Then it removes the spawned rippers and transcoders and stops the stack.

**`armctl compose ...`** passes any Compose command through with the right files, `.env` and project directory. `armctl compose ps` and `armctl compose logs arm-backend` replace the bare `docker compose` forms, since typing `docker compose` in the install folder does not find the files.

**Failure behavior.**

- **Before the switch**, any failure (network, registry, checksum, active work, backup) leaves the running install exactly as it was, and the message says so.
- **After the switch**, a failed start or health check is reported with the release the install is now on, a statement that it was not rolled back, the database backup taken in that run (or that none was taken), the folder where the previous release is kept, the command that shows the backend log, and that `armctl up` tries the start again once the cause is fixed. There is no automatic rollback, because database migrations cannot be reversed. See [the user Upgrading page](../../user/Upgrading.md#rolling-back).
- **One at a time.** A lock in `.armctl/` stops two `armctl` runs overlapping. Without `flock` on the host, `armctl` warns and carries on unguarded.
- **No terminal** never blocks on a prompt and reads nothing from stdin: defaults are taken, every yes/no question is answered "no", host changes are skipped unless `--yes` is given, and skipped steps are listed. An offload install with `--offload-host` and `--offload-backend-url` checks each walkthrough step once without waiting, and a step that fails is reported in the completion table. When `--yes` is given but `sudo` cannot run without a password, the udev rule is written to `.armctl/99-arm-no-automount.rules` with the three commands that install it, and the step is listed as skipped.

The install drill, `devtools/install-drill.sh`, runs this path end to end against images built from a checkout. It is manual and refuses to run on a host that already has an ARM v3 stack.

**First-boot sequence** (after `armctl up`):

1. Backend starts, waits for Postgres, runs `alembic upgrade head`, seeds the `admin` user with a random password written to `/logs/first-boot.log` and printed to stdout.
2. User navigates to `https://host:8081`, accepts the internal-CA cert warning on first visit (or imports `~/arm/certs/arm-ca.crt` into the OS/browser trust store once to clear it for every device on the LAN — see [05-cross-cutting.md § Transport (TLS)](05-cross-cutting.md#transport-tls)), logs in as `admin` with the printed password, is forced to change it.
3. User enters third-party API keys in the UI → stored in `config`.
4. Rippers register themselves with Backend, appear in UI.
5. User inserts a disc; flow proceeds as documented in [02-job-lifecycle.md](02-job-lifecycle.md).

## Update / upgrade

- v3 images are tagged `docker.io/automaticrippingmachine/arm-<service>:v3.<x>.<y>`. Keeping the registry and namespace path from v2 so existing users don't have to follow a new identity.
- Upgrade = `armctl upgrade` (see [§ Installer](#installer)). It pulls the new images, backs up the database and restarts the stack; the Backend runs migrations and the DB schema moves forward. A new service or setting reaches production through the template the release ships, so no separate major-version step exists.
- **No rollback of DB schema.** Alembic `downgrade` is not supported past minor versions — back up the DB if paranoid.

## Uninstall

```bash
armctl down
rm -rf ~/arm
docker volume rm armv3_arm-data
```

The database folder may need `sudo` to remove. If a PATH link was made, remove `~/.local/bin/armctl` or `/usr/local/bin/armctl`. No systemd units and no distro integration; the optional udev rule is the only host-wide file, and `docs/user/Uninstall.md` says how to remove it.

## Backup

Four things to back up, in priority order:

1. **`~/arm/certs/arm-ca.key`.** Unique-per-install and unrecoverable. If lost, the user has to rotate the CA and re-import on every LAN client — recoverable but annoying.
2. **Postgres dump.** `pg_dump` from a cron against the `armv3-db` container; ARM doesn't manage this. Contains plaintext secrets — store the dump somewhere you'd trust with a password export.
3. **`~/arm/.armctl/.env`.** Useful for reproducing a deployment quickly; losing it just means regenerating `ARM_SERVICE_TOKEN` and the DB password (which then requires restoring the Postgres dump with matching credentials, or renaming the DB user).
4. **`~/arm/raw` and `~/arm/media`.** User's responsibility; these are large and the user knows their own backup strategy.

The release bundle and the host overlay under `~/arm/.armctl/` are regenerated by `armctl install` and `armctl upgrade`, so they don't strictly need a backup. `armctl up` and `armctl upgrade` also leave database backups in `~/arm/backups/`.

## Platform-specific notes

- **Bare-metal Docker on Linux**: the one supported path. Install via `install.sh` and run `armctl up`; all docs default to this. NAS-appliance GUIs (Unraid/Synology) are out of scope for v3.0 — see "Explicitly NOT supported" above.
