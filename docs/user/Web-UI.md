# Web UI

The v3 UI is a SvelteKit (Svelte 5) single-page app served over HTTPS by nginx at
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

**`/`** is the landing page after login: your drives, in-flight rips and
transcodes, and the job list (card or table view, filterable by status and
type), updated live over the WebSocket. Each drive card shows its state (idle,
reading, ripping, tray open), toggles the drive between **Auto** and **Manual**
rip mode, and has a **Start rip** button for a disc already in the tray (how you
rip when auto-rip is off, optionally pinning a session for that disc).

## Jobs

**`/jobs/:id`** is one job in detail: the disc that was identified, its tracks,
per-track rip progress, and any transcode sessions applied to it. From here you
can act on a job (e.g. resolve an unidentified disc, or abandon it).
**`/logs`** and **`/logs/:job_id`** show the structured logs; **`/files`**,
**`/notifications`** and **`/transcoder`** cover the file browser, the
notification history and the transcode queue.

## Settings

**`/settings`** is the Settings page, split into tabs:

- **Metadata** and **Ripping**: API keys and rip behaviour. Every field is documented in
  [Configuration § The UI Settings page](Configuring-ARM#the-ui-settings-page).
- **Sessions**: **sessions** are named bundles of transcode work you apply to a
  job (a drive can have a default session so finished rips transcode
  automatically), plus the **rip presets** (how titles are pulled off the disc:
  which MakeMKV behaviour, or a full-disc ISO dump) and **transcode presets**
  (the HandBrake/abcde profiles, e.g. *H.265 1080p*, *music → FLAC*). Built-in
  presets are seeded on first boot, so you can ignore all of this until you want
  to customize output.
- **Drives**: the optical drives ARM knows about. Enroll a drive here to give
  it an `arm-ripper-<serial>` container.
- **Transcoding**, **Notifications**, **Interface**, **Themes**, **Users** and
  **System**.

### Output path tokens

A session's output path is a template such as
`{title} ({year?})/{title} ({year?}) - Track {track} - {transcode_slug}.{ext}`.
Each `{token}` is filled from the job; the token chips under the field list the
ones allowed for the session's media type.

A token written with a trailing `?`, like `{year?}`, is **optional**. When the
job has no value for it, ARM drops the token together with brackets that wrap
only it and the space before it, so `Title ({year?})` becomes `Title`. A plain
`{year}` is required: applying the session to a job without a year fails and
asks you to add one. `{ext}` and `{transcode_slug}` can't be optional because
they always have a value.

The built-in sessions use `{year?}`. A session you cloned from a built-in
before this change keeps `{year}`; edit its output path to add the `?`.

## Diagnostics

**Settings → System** includes a read-only diagnostics section (service status
and log levels), useful when filing a bug. For deeper digging,
`docker compose logs <service>` on the host is still the authoritative source
(set `ARM_LOG_LEVEL=debug` first).
