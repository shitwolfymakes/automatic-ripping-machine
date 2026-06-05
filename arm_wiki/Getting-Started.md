# Getting Started

This page takes you from a bare Linux host to your first finished rip. ARM v3
runs **only** as a Docker Compose stack — there is no native install. If you are
looking for `apt install` instructions or an `arm.yaml`, you are thinking of ARM
v2, which is frozen and no longer developed.

## Contents

1. [Hardware](#hardware)
2. [Prerequisites](#prerequisites)
3. [Install](#install)
4. [What the installer creates](#what-the-installer-creates)
5. [Start the stack](#start-the-stack)
6. [First login](#first-login)
7. [Trust the certificate (optional but recommended)](#trust-the-certificate)
8. [Your first rip](#your-first-rip)
9. [Next steps](#next-steps)

## Hardware

ARM is happy on modest hardware, but transcoding video is the heavy part. Use
HandBrake's [system requirements](https://handbrake.fr/docs/en/latest/technical/system-requirements.html)
as the baseline.

- **CPU:** anything reasonably modern. A 6th-gen-or-newer Intel Core / Xeon, or
  an AMD Ryzen/Threadripper/Epyc, transcodes comfortably. A GPU is optional and
  only speeds up transcoding — see [Hardware Transcoding](Hardware-Transcoding).
- **Memory:** roughly 1 GB for SD, 2–8 GB for HD (720p/1080p), and 6–16 GB+ for
  4K transcodes, on top of what the rest of the stack uses.
- **Optical drive(s):** one or more, each exposed to the host as `/dev/sr*`. ARM
  runs one ripper container per drive, in parallel.
- **Storage:** ripping is disk-hungry. Budget ~10–20 GB free per in-flight
  Blu-ray for the intermediate `raw` files, plus space for the finished `media`
  library. Audio CDs are well under 1 GB each.

> ⚠️ **Windows / macOS:** Docker Desktop cannot pass an internal SATA optical
> drive into its Linux VM, so you **cannot rip** from Windows or macOS. You can
> still run the UI + transcoder as a library frontend over an SMB/WSL2 path. See
> [Known Issues](Status-Known-Issues).

## Prerequisites

The host must have, and the installer checks for:

| Tool | Minimum | Notes |
|---|---|---|
| Docker Engine | **24** | <https://docs.docker.com/engine/install/> |
| `docker compose` | **v2 plugin** | Ships with current Docker; `docker compose version` must work. |
| `openssl` | 1.1.1 | Present on any modern Linux. Used to generate the internal CA. |
| `bash` | 4 | The installer uses bash-4 features. |

Your user must be able to reach the Docker daemon — either a member of the
`docker` group or able to `sudo`:

```bash
sudo usermod -aG docker "$USER" && newgrp docker
```

You do **not** need to be in the host's optical group; the ripper container is
granted access to the drive via `group_add` automatically.

## Install

One command bootstraps everything:

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
```

Prefer to read the script first, or want a TTY for the prompts? Use either of:

```bash
# Download, read, run
curl -fsSLo install.sh https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh
less install.sh && bash install.sh

# Or run with a real TTY attached
bash -c "$(curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh)"
```

Useful flags (`install.sh --help` lists them all):

| Flag | Effect |
|---|---|
| `--prefix <path>` | Install somewhere other than `~/arm` (e.g. `/srv/arm`, `/mnt/tank/arm`). |
| `--start` | Run `docker compose up -d` at the end instead of just printing the command. |
| `--rotate-ca` | Regenerate the internal CA **and every leaf cert** (you'll need to re-trust it on every device — only for suspected key compromise). |

The installer is **idempotent** — rerun it any time you attach a new drive or
upgrade across a major version. It preserves your `.env` secrets and your CA,
and only *adds* service blocks for newly-detected drives.

## What the installer creates

Everything lands under the prefix (`~/arm` by default). You never clone the repo
and nothing compiles on the host — the stack is entirely image-based.

```text
~/arm/
├── .env                     # generated secrets + tunables (mode 0600)
├── docker-compose.yml       # generated; one arm-ripper-srN block per drive
├── docker-compose.gpu.yml   # GPU transcoding overlay (opt-in)
├── certs/                   # internal CA + per-service TLS leaf certs
├── db/                      # Postgres data
├── raw/                     # intermediate rip output
├── media/                   # finished, Plex/Jellyfin-friendly library
└── logs/                    # per-service JSONL logs
```

In order, the installer:

1. **Checks prerequisites** (above) and fails fast with a clear message.
2. **Generates an internal CA** (`certs/arm-ca.{key,crt}`, EC P-384, 10-year).
   The CA key stays on the host and is never mounted into a container.
3. **Detects optical drives** by scanning `/dev/sr*`, pairing each with its
   SCSI-generic node (`/dev/sg*` — MakeMKV needs both), and issues a TLS leaf
   cert per drive plus leaves for the backend, UI, and database.
4. **Seeds `.env`** with a random `POSTGRES_PASSWORD` and `ARM_SERVICE_TOKEN`,
   your `PUID`/`PGID` (`id -u`/`id -g`), and the host's optical group GID
   (`CDROM_GID`). Third-party API keys are left blank — you set those in the UI.
5. **Generates `docker-compose.yml`** with one `arm-ripper-srN` service per
   detected drive. With no drives detected the stack still installs (UI +
   backend + transcoder); only the ripper services are omitted.
6. **On a desktop host, disables auto-mount** for the ARM drive(s) only, by
   writing a scoped udev rule (`/etc/udev/rules.d/99-arm-no-automount.rules`).
   This is required so the ripper can eject after a rip — see
   [Troubleshooting § Disc won't eject](Troubleshooting#disc-wont-eject-after-a-rip).

## Start the stack

```bash
cd ~/arm
docker compose pull      # fetch the published images
docker compose up -d
```

Check that everything is healthy:

```bash
docker compose ps
docker compose logs -f arm-backend
```

> **Alpha note:** during early v3 development the published registry images may
> not yet exist for every tag, and `docker compose pull` can 404. To run today,
> build the images locally from a checkout — see
> [Local development in the README](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/README.md#local-development).

## First login

On first boot the backend waits for Postgres, runs its database migrations, and
seeds an `admin` account with a **default password of `admin`**:

```text
username: admin
password: admin
```

These are also written to `logs/first-boot.log`:

```bash
docker exec armv3-backend cat /logs/first-boot.log
```

Open **`https://localhost:8081`** (or `https://<host-ip>:8081` from another
device), log in as `admin` / `admin`, and you'll be **forced to set a new
password immediately** — the rest of the API stays locked (HTTP 403) until you
do.

## Trust the certificate

The stack serves HTTPS using its own internal CA, so the first visit shows a
browser certificate warning. You can click through it, but to silence it for
good — on every device on your LAN — import the CA once:

- The CA file is `~/arm/certs/arm-ca.crt`.
- Import it into your browser or OS trust store as a trusted **root**
  certificate authority.

This is a one-time action per device. The per-service leaf certs are
regenerated whenever you rerun the installer, but they're all signed by this CA,
so trusting the CA is enough — you never re-import after a leaf changes.

## Your first rip

1. **Configure metadata lookups (recommended).** In the UI, open **Settings**
   and add a [TMDb](https://www.themoviedb.org/settings/api) and/or
   [OMDb](https://www.omdbapi.com/apikey.aspx) API key so ARM can name your
   discs. ARM also tries the community CRC64 database first (no key needed), and
   audio CDs use MusicBrainz (no key needed). See [Configuration](Configuring-ARM).
2. **Insert a disc.** The ripper polls the drive every couple of seconds — no
   udev events needed — and a new job appears on the dashboard within a few
   seconds of the drive spinning up.
3. **Watch it work.** ARM identifies the disc, rips it with MakeMKV (video) or
   abcde (audio CD), and streams live progress to the browser. Video then
   transcodes with HandBrake into `~/arm/media/`.
4. **Eject.** ARM ejects automatically when the rip finishes.

If the disc isn't identified and you've set `block_on_miss` (the default), ARM
pauses and asks you to confirm or search for the title before ripping. You can
also start a rip by hand from **Jobs → Manual** when a disc is already in the
tray.

## Next steps

- **[Configuration](Configuring-ARM)** — every `.env` tunable and UI setting.
- **[Web UI](Web-UI)** — what each page does.
- **[Hardware Transcoding](Hardware-Transcoding)** — turn on GPU transcoding.
- **[MakeMKV](MakeMKV)** — supply a permanent key instead of the rotating beta.
- **[Troubleshooting](Troubleshooting)** — when a disc isn't detected, won't
  eject, or files land with the wrong owner.
