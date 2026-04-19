# 01 — System Architecture Overview

## Container topology

```
                              ┌───────────────────────┐
                              │   Browser (admin)     │
                              └──────────┬────────────┘
                                         │  HTTPS (reverse proxy recommended, not required)
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │                    arm-ui                            │
              │   nginx serving Vite-built SPA (Vue or React)        │
              │   /api → proxy to arm-backend:8000                   │
              │   /ws  → proxy to arm-backend:8000 (WebSocket)       │
              └──────────────────────────┬──────────────────────────┘
                                         │  REST + WS
                                         │
    ┌────────────────────────────────────▼────────────────────────────────────┐
    │                               arm-backend                                │
    │   FastAPI + Pydantic + Uvicorn                                           │
    │                                                                          │
    │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
    │   │ /api (REST)  │  │ /ws (hub)    │  │ state machine│  │ adapters    ││
    │   │   users,     │  │  live        │  │   rip, meta, │  │  TMDB/OMDB  ││
    │   │   jobs,      │  │  progress,   │  │   session,   │  │  MB         ││
    │   │   sessions,  │  │  events      │  │   transcode  │  │  Notify ◇   ││
    │   │   config     │  │              │  │              │  │             ││
    │   └──────────────┘  └──────────────┘  └──────┬───────┘  └─────────────┘│
    │                                              │                          │
    │                                     docker-py ▼ /var/run/docker.sock    │
    │                                     spawns arm-transcode                │
    └──────┬────────────────────────┬────────────────────────┬────────────────┘
           │                        │                        │
           │                        │                        │ (ephemeral)
           │ REST + WS              │ REST + WS              ▼
    ┌──────▼─────────┐       ┌──────▼─────────┐       ┌──────────────────┐
    │ arm-ripper-sr0 │       │ arm-ripper-sr1 │       │ arm-transcode-*  │
    │  Python        │       │  Python        │       │  Python wrapper  │
    │  MakeMKV       │       │  MakeMKV       │       │  around HandBrake│
    │  /dev/sr0      │       │  /dev/sr1      │       │  (GPU optional)  │
    └──────┬─────────┘       └──────┬─────────┘       └──────┬───────────┘
           │                        │                        │
           │        writes raw      │                        │ reads raw, writes transcoded
           ▼                        ▼                        ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                 /raw   (shared volume, flat tree)                    │
    │                 /media (shared volume, Plex-friendly tree)           │
    │                 /logs  (shared volume, JSONL per service)            │
    └─────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────┐
    │ arm-db   Postgres 16, at-rest enc.   │◀── all services read/write here
    └──────────────────────────────────────┘

  ◇ Notifications: typed events emit from Backend; dispatched via Apprise with native pass-through config (see 05-cross-cutting.md "Notifications").
```

## Services at a glance

### `arm-ui`
- **Image:** custom, `nginx:alpine` + built SPA bundle.
- **Replicas:** 1.
- **Inputs:** browser traffic.
- **Outputs:** proxied calls to Backend.
- **State:** none. Fully stateless.
- **Notes:** SPA can be rebuilt and redeployed without touching Backend. Framework TBD between Vue and React — decide when the UI track starts.

### `arm-backend`
- **Image:** custom, Python 3.12 + FastAPI + Uvicorn + docker-py.
- **Replicas:** 1. (Not horizontally scalable in v3.0 — it owns the WS hub and the state machine.)
- **Inputs:** REST + WS from UI and rippers; Docker socket for spawning transcoders.
- **Outputs:** Postgres writes; container spawns; outbound HTTPS to TMDB/OMDB/MB/notifications.
- **State:** all durable state is in Postgres. The WS hub's connection table is in-memory and rebuilt on reconnect.
- **Notes:** Requires `/var/run/docker.sock` mounted to spawn `arm-transcode` containers.

### `arm-ripper-<drive>`
- **Image:** custom, Python 3.12 + MakeMKV + libdvdcss + abcde.
- **Replicas:** one per optical drive. Declared explicitly as separate services in `docker-compose.yml` — e.g. `arm-ripper-sr0`, `arm-ripper-sr1`.
- **Inputs:** polled `ioctl(CDROM_DRIVE_STATUS)` on passed-through `/dev/sr*`; REST/WS config from Backend.
- **Outputs:** raw media files under `/raw/<job-id>/`; REST status updates + WS progress to Backend.
- **State:** ephemeral. All persistent state is pushed to Backend.
- **Notes:** Reads `ARM_DRIVE_DEV` env var on boot (e.g. `/dev/sr0`) and registers with Backend at startup. Never talks to the internet.

### `arm-transcode-<uuid>`
- **Image:** custom, Python 3.12 + HandBrakeCLI + ffmpeg + optional VAAPI/NVENC/QSV drivers.
- **Replicas:** zero at rest. Backend spawns one container per transcode job; the container exits when the job completes.
- **Inputs:** transcode job spec via env / mounted config; raw files from `/raw` (read-only).
- **Outputs:** transcoded files to `/media`; REST status + WS progress to Backend.
- **State:** none. Job spec comes from Backend at container creation.
- **Notes:** Auto-detects available hardware encoders and advertises them to Backend on handshake. Backend flag `ARM_AUTO_TRANSCODE` toggles "spawn when idle" vs. "user must initiate."

### `arm-db`
- **Image:** `postgres:16`. At-rest encryption is optional and user-owned (LUKS or ZFS native — not required by ARM).
- **Replicas:** 1.
- **Notes:** Bootstrap credentials come from env vars; all other config (TMDB key, Apprise URLs, etc.) lives in DB rows written through the UI, stored plaintext.

## Data flow: disc insertion to finished file

1. **Disc insertion.** Ripper detects via polling `ioctl(CDROM_DRIVE_STATUS)` on its bound `/dev/sr*` every 2s. No udev rules on host or in container.
2. **Identify.** Ripper reads disc type (DVD/BD/CD/data) and performs a MakeMKV scan on DVD/BD to extract track layout and disc-native metadata (~30-90s latency floor, surfaced in the UI as "Analyzing disc…"). CDs use MusicBrainz Disc ID.
3. **Lookup.** Ripper calls `POST /api/ripper/identify` on Backend with the scan result. Backend queries TMDB/OMDB/MB. Ripper blocks on this call.
   - On hit: Backend returns title + year + artwork URL + suggested track layout. A `Job` row is created in state `identified`.
   - On miss: behavior depends on `config.block_on_miss`. Default (`true`): Backend returns `status: "needs_user_input"`, UI shows a prompt, ripper waits for resolution — disc stays in drive, rip does not start. Opt-in (`false`): ripper begins ripping immediately to `/raw/<job_id>/` (raw paths key on `job_id`, which is assigned pre-identify and never changes). Transcode is gated on identity: queued `session_applications` remain in `waiting_identify` until the user resolves identity, then fan out against the resolved title. No files are ever renamed or moved — the only path that could encode identity is the `/media` path, and nothing is written there until identity exists. A rip is **never** cancelled by miss-handling.
4. **Rip.** Ripper creates one `Track` row per title and begins ripping. Each track's state transitions `queued → in_progress → done|failed`. Progress streams over WS.
5. **Rip complete.** Ripper emits `rip.completed` event, ejects disc, returns to idle.
6. **Auto-session (if configured).** If the Backend is configured with auto-sessions, it queues a transcode for each assigned default session.
7. **Transcode spawn.** Backend dequeues a transcode job and spawns `arm-transcode-<uuid>` via Docker socket. Container mounts `/raw` read-only and `/media` read-write, receives job spec via env.
8. **Transcode.** Worker runs HandBrake, streams progress over WS, writes output to `/media/<layout>/<title>`.
9. **Transcode complete.** Worker emits `session.completed` event, container exits, Backend updates state, notifications fire.
10. **Done.** Raw is retained by default (no auto-prune). User can queue additional sessions from UI at any time.

## Shared volumes

| Volume | Mount path | Writers | Readers | Notes |
|---|---|---|---|---|
| `arm_raw` | `/raw` | Rippers | Transcoders (ro) | Flat tree: `/raw/<job_id>/<track>.mkv`. No auto-prune. |
| `arm_media` | `/media` | Transcoders | (user's media server) | Plex/Jellyfin-friendly layout by default; session templates can override. |
| `arm_logs` | `/logs` | All services | Backend (for UI log view) | JSONL per service; lines include `job_id` for correlation. |
| `arm_config` | `/config` | Backend | All services | App-level config written via UI. |

## Privilege & security model

- **Backend mounts the Docker socket.** Standard homelab pattern (Traefik, Watchtower). Treat `arm-backend` as host-root-equivalent.
- **Ripper gets device access.** `--device /dev/sr0:/dev/sr0` with whatever cgroup rules MakeMKV needs.
- **Transcode may get GPU device access.** `--device /dev/dri` or nvidia runtime, conditionally.
- **UI and DB are unprivileged.**

## What's NOT in this diagram

- **Queue / broker.** We considered DB-as-queue, Redis, NATS. The decision is deferred — the state machine is designed so the queue can be swapped in without reshaping services. See [07-open-questions.md](07-open-questions.md).
- **Metadata worker.** Currently Backend does lookups inline. If this proves too slow or flaky it becomes a separate worker in a later version.
