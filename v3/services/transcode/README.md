# arm-transcode

Ephemeral, single-task transcoder container. The Backend's
`TranscodeDispatcher` spawns one container per `transcode_tasks` row via
the Docker socket; each container claims its task, runs HandBrake or
ffmpeg against the raw input, writes the output through the
`*.arm-inprogress` atomic-rename flow, and exits.

## Image contents

`python:3.14-slim-bookworm` plus:

- `tini` — PID 1; reaps the encoder subprocess.
- `gosu` — drops to PUID/PGID before exec.
- `ca-certificates` — base trust store; the entrypoint merges the
  install's internal CA at boot so HTTPS verifies against the Backend's
  internal cert.
- `handbrake-cli` — primary video encoder.
- `ffmpeg`, `flac` — audio re-encoder for music sessions.
- `arm_transcode` (this package) — claim/heartbeat client + encoder
  wrappers.

`abcde` is **not** in the transcode image — that's a ripping tool, used
by `arm-ripper` to pull a CD into `track_NN.wav` files. The transcoder
re-encodes those WAVs to FLAC/MP3 via ffmpeg.

## Environment variables (set by the dispatcher at spawn time)

- `ARM_TRANSCODE_TASK_ID` — ULID of the row to register/claim/run.
- `ARM_BACKEND_URL` — e.g. `https://arm-backend:8443`.
- `ARM_SERVICE_TOKEN` — REST `Authorization: Bearer` and WS auth.
- `ARM_LOG_LEVEL` — JSON-line logger level.
- `PUID` / `PGID` — entrypoint drops privileges to this UID/GID before
  the encoder runs, so files in `/media` land owned by the user (the
  same pattern as the ripper container).
- `HOSTNAME` — set by docker via `--hostname`; the transcoder echoes it
  on register so the Backend can stamp `claimed_by`.

## Volumes

- `/raw:ro` — the rip-stage outputs (`title_tNN.mkv`, `track_NN.wav`,
  `dump.iso`).
- `/media:rw` — final library destination. The transcoder writes
  `<final>.arm-inprogress`, fsyncs the parent dir, then `rename(2)` to
  `<final>` on success. On crash or kill, partial files stay for the
  Backend startup sweep.
- `/etc/ssl/arm/arm-ca.crt:ro` — internal CA, merged into the system
  trust store by the entrypoint.
- `/logs:rw` — shared with the Backend; reserved for per-task log capture
  in Phase 12.

## Dev rebuild

The image is not declared as a runtime compose service — the dispatcher
spawns it on demand. To build it locally:

```sh
docker compose --profile build-transcode build arm-transcode-builder
```

The dispatcher picks the image up by name (`arm-transcode:dev` by
default, override via `ARM_TRANSCODE_IMAGE` in `.env`).

## Lifecycle (single task per container)

```text
 spawn (Backend)
      │
      ▼
 register     POST /api/transcoder/register   (verifies task is still expected)
      │
      ▼
 claim        POST /api/transcoder/tasks/{id}/claim
      │       (atomic queued → in_progress; emits session.started + task.started)
      ▼
 encode       HandBrakeCLI / ffmpeg / passthrough
      │       (heartbeat REST every 30s; transcode.progress.* WS every ~1s)
      ▼
 complete     PATCH /api/transcoder/tasks/{id}/complete
              (or /fail on error / cancel)
      │
      ▼
 exit (auto_remove=True)
```

Cancellation: the dispatcher emits `task.cancel` on
`transcoder.commands.{task_id}` over WS; the transcoder's main loop
catches it via the WS subscription and SIGTERMs the encoder. After a
10s grace, the dispatcher falls back to `docker stop`.
