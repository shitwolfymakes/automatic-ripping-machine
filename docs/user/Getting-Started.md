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
7. [The setup walkthrough](#the-setup-walkthrough)
8. [Trust the certificate (optional but recommended)](#trust-the-certificate)
9. [Your first rip](#your-first-rip)
10. [Next steps](#next-steps)

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

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
```

Run it as your normal user, not as root and not with `sudo`. It asks for
`sudo` only for the steps that need it.

Prefer to read it first?

```bash
curl -fsSLo install.sh https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh
less install.sh
bash install.sh
```

The installer asks a few questions:

- **How the host is used.** Full box (rip and transcode here), ripper-only, or
  rip here and transcode on another machine.
- **Where raw rips and finished media go.** The default is inside `~/arm`;
  point them at a NAS mount or a second disk if you have one.
- **Host changes, one at a time.** Installing Docker (Debian and Ubuntu only),
  the NVIDIA container toolkit if you have an NVIDIA GPU, and a udev rule that
  stops a desktop session auto-mounting discs. You can decline any of them.

On a distro other than Debian or Ubuntu, install Docker Engine 24 or newer with
the Compose plugin yourself first
([Docker's instructions](https://docs.docker.com/engine/install/)); the
installer then does everything else.

To install somewhere other than your home folder, add `--prefix /srv`, which
gives `/srv/arm`. For an unattended install, every question has a flag:

```bash
bash install.sh --profile ripper-only --raw-path /mnt/rips --media-path /mnt/media --yes
```

## What the installer creates

Everything lives in one folder, `~/arm`:

| Path | What it is |
|---|---|
| `armctl` | The command you use to start, stop and upgrade ARM. |
| `raw/`, `media/` | Raw rips and finished media, unless you chose other folders. |
| `logs/` | Job and service logs. |
| `certs/` | ARM's own certificate authority and the service certificates. |
| `db/` | The database. |
| `backups/` | Database backups taken before each restart and upgrade. |
| `scripts/` | Your notification scripts. |
| `iso-library/` | Disc images for "Rip from ISO". |
| `.armctl/` | Configuration: `.env` (secrets, settings) and the installed release. |

## Start the stack

The installer starts ARM for you. Afterwards:

```bash
armctl up        # start, or restart after a change
armctl down      # stop
armctl upgrade   # move to the latest release
armctl compose ps                  # any docker compose command
armctl compose logs arm-backend
```

`armctl up` and `armctl down` refuse to run while a rip or transcode is in
progress, so they cannot kill a job by accident; add `--force` to override.
If `armctl` is not found, use `~/arm/armctl`.

> **Alpha note:** during early v3 development the published registry images may
> not yet exist for every tag, and the image pull can 404. To run today,
> build the images locally from a checkout — see
> [Local development in the README](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/README.md#local-development).

## First login

On first boot the backend waits for Postgres, runs its database migrations, and
seeds an `admin` account with a **default password of `admin`**. The sign-in
page reminds you where it is written down:

```bash
docker exec armv3-backend cat /logs/first-boot.log
```

Open **`https://localhost:8081`** (or `https://<host-ip>:8081` from another
device) and sign in as `admin` / `admin`. ARM opens the
[setup walkthrough](Setup-Walkthrough).

## The setup walkthrough

The walkthrough takes you from "containers are running" to "insert a disc and
it works". Each step saves when you press Continue, so you can close the tab and
pick up where you left off.

1. **Secure your account.** Set your own admin password (the rest of ARM stays
   locked until you do) and choose whether guests on your network can look
   around without signing in.
2. **System check.** ARM checks the folders and services it was installed with.
   A folder it can't write to comes with the exact `chown` command to run.
3. **Drives.** Enroll each optical drive you want to rip with, and ignore the
   rest. No drive? You can rip ISO image files instead.
4. **MakeMKV.** Use the free monthly beta key or your purchased key. A drive
   checks the key for you.
5. **Find titles** (optional). Add a free [TMDb](https://www.themoviedb.org/settings/api)
   and/or [OMDb](https://www.omdbapi.com/apikey.aspx) key and test it in place.
   TV episodes and music CDs work without one.
6. **Disc handling.** Fully automatic, review the title first, or manual.
7. **Transcoding** (optional). Test your graphics card's encoders.
8. **Notifications** (optional). Get a phone or chat message when a rip
   finishes, needs you, or fails.
9. **Finish.** Insert a disc and watch it start.

Anything you skip stays on a checklist on the dashboard. To go through it again,
use **Settings, System, Run setup again**.

## Trust the certificate

The stack serves HTTPS using its own internal CA, so the first visit shows a
browser certificate warning. You can click through it, but to silence it for
good on every device on your LAN, import the CA once. The Finish step has a
**Download certificate** button, or use the file directly:

- The CA file is `~/arm/certs/arm-ca.crt`.
- Import it into your browser or OS trust store as a trusted **root**
  certificate authority.

This is a one-time action per device. The per-service leaf certs are
regenerated whenever you rerun the installer, but they're all signed by this CA,
so trusting the CA is enough: you never re-import after a leaf changes.

## Your first rip

1. **Insert a disc.** The ripper polls the drive every couple of seconds (no
   udev events needed) and a new job appears on the dashboard within a few
   seconds of the drive spinning up.
2. **Watch it work.** ARM identifies the disc, rips it with MakeMKV (video) or
   abcde (audio CD), and streams live progress to the browser. Video then
   transcodes with HandBrake into `~/arm/media/`.
3. **Eject.** ARM ejects automatically when the rip finishes.

If the disc isn't identified and you've set `block_on_miss` (the default), ARM
pauses and asks you to confirm or search for the title before ripping. You can
also start a rip by hand from the drive's **Start rip** button when a disc is
already in the tray.

## Next steps

- **[Configuration](Configuring-ARM)** — every `.env` tunable and UI setting.
- **[Web UI](Web-UI)** — what each page does.
- **[Hardware Transcoding](Hardware-Transcoding)** — turn on GPU transcoding.
- **[MakeMKV](MakeMKV)** — supply a permanent key instead of the rotating beta.
- **[Troubleshooting](Troubleshooting)** — when a disc isn't detected, won't
  eject, or files land with the wrong owner.
