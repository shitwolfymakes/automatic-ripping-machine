# Web UI

The v3 UI is a Vue 3 single-page app served over HTTPS by nginx at
**`https://<host>:8081`**. It talks to the backend over REST and a WebSocket, so
job progress and drive state update live without refreshing.

> The v2 Flask UI and its screenshots no longer apply — v3 is a different
> application. This page describes the pages and what they do; the exact layout
> evolves through the alpha, so treat names as a map, not a pixel reference.

## Logging in

- **`/login`** — sign in. The seeded account is `admin` / `admin` on a fresh
  install.
- **`/change-password`** — you're sent here automatically on first login and
  cannot use the rest of the app until you set a new password (the backend
  returns 403 on every other endpoint until you do).

## Dashboard

**`/dashboard`** is the landing page after login: an at-a-glance view of your
drives, in-flight jobs, and recent activity, updated live over the WebSocket.

## Jobs

- **`/jobs`** — the list of rip/transcode jobs, past and present, with status
  and progress.
- **`/jobs/:id`** — one job in detail: the disc that was identified, its tracks,
  per-track rip progress, and any transcode sessions applied to it. From here
  you can act on a job (e.g. resolve an unidentified disc, or abandon it).
- **`/jobs/manual`** — start a rip by hand against a drive that already has a
  disc in the tray. This is how you rip when **Auto-rip on insert** is off, or
  when you want to pick a specific session for this disc.

## Drives

**`/drives`** lists the optical drives ARM knows about — one per
`arm-ripper-srN` container — with their current state (idle, reading, ripping,
tray open) and the job each is working. Each drive is enrolled when its ripper
container registers with the backend at startup; you add a drive by attaching it
and rerunning `install.sh`, then `docker compose up -d`.

## Sessions and presets

These pages let you control *how* discs are ripped and transcoded. Built-in
presets are seeded on first boot, so you can ignore all of this until you want
to customize output.

- **`/sessions`**, **`/sessions/new`**, **`/sessions/:id/edit`** — **sessions**
  are named bundles of transcode work you apply to a job. A drive can have a
  default session so finished rips transcode automatically.
- **`/rip-presets`** (+ new/edit) — **rip presets** control how titles are
  pulled off the disc (which MakeMKV behaviour, or a full-disc ISO dump).
- **`/transcode-presets`** (+ new/edit) — **transcode presets** are the
  HandBrake/abcde profiles (e.g. *H.265 1080p*, *music → FLAC*, *music → MP3*).

## Settings

**`/config`** is the Settings page — API keys, rip/transcode behaviour
(auto-rip, block-on-miss, auto-transcode, retention), and notifications. Every
field is documented in [Configuration § The UI Settings page](Configuring-ARM#the-ui-settings-page).

## Diagnostics

**`/diagnostics`** surfaces health and log information for support — service
status and recent log output, useful when filing a bug. For deeper digging,
`docker compose logs <service>` on the host is still the authoritative source
(set `ARM_LOG_LEVEL=debug` first).
