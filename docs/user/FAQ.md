# FAQ

## Is there a native (non-Docker) install?

No. ARM v3 runs only as a Docker Compose stack. The legacy `apt`/native install
belonged to v2, which is frozen and no longer developed. See
[Getting Started](Getting-Started).

## Can I upgrade my ARM v2 install to v3?

There's no in-place migration — v3 shares no code, database, or config with v2.
Install v3 fresh; it can run side by side with v2 (containers/volumes are
namespaced `armv3-*` vs `arm-*`). See [Upgrading](Upgrading).

## Do I need API keys?

No, but they help. ARM tries the community CRC64 database first (no key), then
TMDb and OMDb (keys improve naming hit rates a lot), and MusicBrainz for audio
CDs (no key). Add TMDb/OMDb keys on the Settings page — see
[Configuration](Configuring-ARM#metadata--identification).

## Can I rip on Windows or macOS?

You can run the UI + transcoder as a library frontend, but you **cannot rip** —
Docker Desktop can't pass an internal optical drive into its Linux VM. Ripping
needs a Linux host. See [Known Issues](Status-Known-Issues).

## How do I rip without HandBrake transcoding?

Apply a rip-only session/preset (e.g. the ISO-dump or a passthrough rip preset)
instead of a transcoding session, or leave **Auto-transcode on idle** off and
don't queue a transcode. The raw MakeMKV output lands in
`~/arm/raw/<job-id>/`. See [Web UI § Sessions and presets](Web-UI#sessions-and-presets).

## Where do my files end up?

- **`~/arm/raw/<job-id>/`** — the intermediate MakeMKV/abcde output.
- **`~/arm/media/`** — the finished, Plex/Jellyfin-friendly library after
  transcoding.

## My disc didn't get identified — what now?

By default (**Block on identification miss** = on) ARM pauses and asks you to
confirm or search for the title before ripping; resolve it from the job in the
UI. Turn the setting off to rip immediately and sort identity out later. See
[Configuration](Configuring-ARM#rip--transcode-behaviour).

## How do I get notified when a rip finishes?

Enable notifications on the Settings page and add one or more Apprise URLs
(Discord, Slack, Telegram, Gotify, e-mail, …). ARM notifies on rip and session
completion/failure. See [Configuration § Notifications](Configuring-ARM#notifications).

## Do I have to pay for MakeMKV?

Not while it's in beta — ARM uses the free monthly beta key automatically. You
can supply a purchased permanent key via `MAKEMKV_KEY` to skip the monthly
rotation. DVDs don't need a key at all; Blu-ray/UHD do. See [MakeMKV](MakeMKV).

## How do I turn on GPU transcoding?

Enable the GPU overlay (and, on NVIDIA, install the Container Toolkit). See
[Hardware Transcoding](Hardware-Transcoding).

## Can I rip from an `.iso` file instead of a disc?

Not yet as a user feature — that's designed but not built. ARM *can* produce an
`.iso` **from** a physical disc (the ISO-dump preset). See
[Roadmap](Status-Roadmap).

## How do I read the logs?

`docker compose logs <service>` from `~/arm`, or browse `~/arm/logs/`. Set
`ARM_LOG_LEVEL=debug` in `.env` first for detail. More in
[Troubleshooting](Troubleshooting).

## How do I back up my install?

In priority order: `certs/arm-ca.key` (unique, unrecoverable), a Postgres dump
(`docker exec armv3-db pg_dump -U arm arm`), `.env`, and your `media/` library.
See [Uninstall](Uninstall) and [Upgrading](Upgrading).
