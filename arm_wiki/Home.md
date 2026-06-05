# Automatic Ripping Machine (ARM) v3

Insert a Blu-ray, DVD, or CD and ARM identifies it, rips it, and (for video)
transcodes it into a Plex/Jellyfin-friendly library — headless, driven from a
web UI, one job per optical drive in parallel.

This is the wiki for **ARM v3**, a greenfield rebuild. It shares nothing with
the legacy v2 codebase: v3 is a multi-service Docker stack — a FastAPI backend,
a Vue UI, Postgres, one ripper container per optical drive, and an ephemeral
transcoder spawned per job. There are **no native (non-Docker) installs** in v3
and **no `arm.yaml`** — you install with a one-line script and configure from
the UI.

> ARM v2 is frozen and preserved forever at the **`v2-final`** git tag. If you
> are running a native/`apt` install or editing `arm.yaml`, you are on v2 — its
> documentation lives in that tag's history, not here.

## New here? Start with [Getting Started](Getting-Started)

The short version:

```bash
curl -fsSL https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/install.sh | bash
cd ~/arm && docker compose up -d
```

Then open **`https://localhost:8081`** and log in as `admin` / `admin` (you'll
be forced to set a real password immediately). The full walkthrough — prereqs,
what the installer generates, trusting the TLS certificate, and your first rip —
is in [Getting Started](Getting-Started).

## Requirements at a glance

- A Linux host with **Docker Engine ≥ 24** and the **`docker compose` v2** plugin.
- One or more optical drives passed through to the host (`/dev/sr*`).
- Enough CPU/RAM for HandBrake transcoding, and disk for `raw` + `media`.
  See [Getting Started § Hardware](Getting-Started#hardware).

Windows and macOS can run the UI + transcoder as a library frontend, but
**cannot rip** — internal optical drives don't pass into the Docker VM. See
[Status & Known Issues](Status-Known-Issues).

## What v3 does

- Detects disc insertion by polling the drive (no host udev rules required).
- Identifies video discs against the ARM community DB (CRC64), then TMDb and
  OMDb; identifies audio CDs via MusicBrainz.
- Rips video with **MakeMKV** and audio CDs with **abcde**.
- Transcodes video with **HandBrake**, optionally on an Intel/AMD/NVIDIA GPU.
- Streams live job progress to the browser over WebSockets.
- Notifies you on completion/failure through **Apprise** (Discord, Slack,
  Telegram, Gotify, and many more).

## Wiki map

- **[Getting Started](Getting-Started)** — install and run your first rip.
- **[Configuration](Configuring-ARM)** — the `.env` file and the UI Settings page.
- **[Web UI](Web-UI)** — a tour of the dashboard, jobs, drives, sessions, and presets.
- **[MakeMKV](MakeMKV)** — registration key handling and the beta-key rotation.
- **[Hardware Transcoding](Hardware-Transcoding)** — enabling Intel QSV / AMD VAAPI / NVIDIA NVENC.
- **[Upgrading](Upgrading)** and **[Uninstall](Uninstall)**.
- **[Troubleshooting](Troubleshooting)** · **[FAQ](FAQ)** · **[Known Issues](Status-Known-Issues)**.
- **[Roadmap](Status-Roadmap)** · **[Contributing](Contribute)** · **[Contributing to the Wiki](Contribute-Wiki)**.

For the architecture and design rationale behind v3, read the in-repo docs
starting at
[`docs/arch/README.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/arch/README.md).
