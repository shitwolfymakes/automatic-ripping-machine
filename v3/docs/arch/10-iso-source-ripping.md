# 10 — ISO-Source Ripping

**Status: proposed (design only).** Nothing here is built yet. This doc is the
design we agreed to write before touching code, so the shape can be reviewed
first. Open decisions are collected in [§ Decisions needed](#decisions-needed).

## What this is — and the name clash to avoid up front

"ISO" means two unrelated things in v3, pointing in opposite directions:

- **ISO as _output_** — `rip_presets.output_mode = 'iso'` produces a full-disc
  `.iso` image *from a physical disc* instead of per-title MKVs (see
  [04-data-model.md](04-data-model.md)). Already in the data model.
- **ISO as _source_** — rip *from* an existing `.iso` file as input, through the
  normal scan → identify → rip (→ transcode) pipeline, no physical disc involved.

**This document is exclusively about the second one.** It's always called
*ISO-source ripping* or *ISO ingestion*, never just "ISO ripping".

## The shape, in one sentence

An ISO-source ripper is an **ephemeral, backend-spawned worker container** — the
**transcode-container lifecycle**, not a long-running service: the backend
spawns one per ISO on demand, it runs the rip, reports, and **exits**
(`auto_remove`). It is *not* a persistent `arm-ripper-iso` daemon, and the
backend never hand-rolls `docker run` plumbing in a script.

> **Design directive (owner):** ISO rippers must be spawned on demand like the
> GPU/transcode containers, not run long. The eventual front door is **UI file
> upload → spawn an ephemeral ISO ripper per upload**; the upload half is
> deferred, the ephemeral-spawn architecture is what we lock in now.

## Why now / what's wrong with today

ISO-source ripping already half-exists, but only as a **test hook**:

- The ripper takes `ARM_MANUAL_TRIGGER_ISO=/path/to.iso`
  ([main.py:121-161](../../services/ripper/arm_ripper/main.py#L121-L161)): treats
  the ISO as its bound "device", rips **once** on startup, then **idles forever**
  so an operator can poke at it — the exact opposite of ephemeral.
- No API, no UI, no spawn mechanism. You hand-launch a privileged container per
  ISO, which is why [devtools/iso-smoke.sh](../../devtools/iso-smoke.sh) grew
  into a ~580-line orchestrator (fixture fetch, key scrape, `docker run`
  assembly, live-ripper stop/restart, transcode trigger, polling, teardown).

The good news: **the backend already spawns ephemeral workers exactly this way
for transcoding.** ISO ingestion is the same mechanism pointed at a different
image — almost no new orchestration primitives.

## Design principle: reuse two things verbatim

1. **The disc pipeline.** An ISO is a source the scan layer already understands —
   [source.py](../../services/ripper/arm_ripper/source.py) routes
   `makemkv_source_url()` to `iso:<path>` vs `dev:<path>`, and scan loop-mounts a
   file ([disc_probe.py](../../services/ripper/arm_ripper/scan/disc_probe.py)).
   Everything downstream of scan — identify, track selection, rip-start,
   `PATCH /tracks`, rip-complete, session auto-apply, transcode — is
   **source-blind and untouched.**
2. **The transcode dispatcher.** The backend's
   [transcode_dispatcher.py](../../services/backend/arm_backend/transcode_dispatcher.py)
   is the template: a task table, a dispatcher tick that spawns
   `containers.run(..., detach=True, auto_remove=True)`
   ([:392-403](../../services/backend/arm_backend/transcode_dispatcher.py#L392-L403)),
   a worker that claims its task and exits, a concurrency cap, a stale-claim
   sweep. ISO ingestion clones this with a `rip_tasks` table and the ripper image.

So this feature is **not** a new rip path and **not** a new orchestration
pattern. It is: a task table + dispatcher (cloned from transcode), an enqueue
endpoint, and a small "run one task then exit" mode in the ripper.

## Target architecture (mirror of the transcode dispatcher)

```
 UI / smoke         Backend                              ephemeral arm-ripper-iso
  │  pick ISO+sess     │                                  (spawned per task, --rm)
  ├─POST /api/iso/rips▶│ validate ISO under library root          │
  │  {iso, session}    │ INSERT rip_tasks (QUEUED) ─┐             │
  │◀── {task_id} ──────┤                            │             │
  │                    │  ── rip dispatcher tick ──◀┘             │
  │                    │  slots = MAX_PARALLEL_ISO_RIPS - in_prog │
  │                    │  docker containers.run(ARM_ISO_RIPPER_IMAGE,
  │                    │      env ARM_RIP_TASK_ID, --rm) ────────▶│ starts
  │                    │◀─ POST /ripper/iso-tasks/{id}/claim ─────┤ claim (CAS)
  │                    │   → {drive_id, /isos/<name>, session}    │
  │                    │◀─ POST /ripper/identify (creates Job) ───┤ scan→identify
  │                    │◀─ rip-start, PATCH /tracks, rip-complete ┤ rip (pipeline)
  │◀─ job in /api/jobs │   session auto-applies → transcode       │ exits, auto-removed
```

### The rip-task table + dispatcher

A `rip_tasks` table mirroring `transcode_tasks`: `status`
(QUEUED|IN_PROGRESS|DONE|FAILED), `claimed_by`, `claim_heartbeat_at`, `attempts`,
plus `source_ref` (library-relative ISO name) and `session_id`. A **rip
dispatcher** background loop — a near-copy of `spawn_pending()`
([transcode_dispatcher.py:229-299](../../services/backend/arm_backend/transcode_dispatcher.py#L229-L299))
— each tick:

1. counts live `rip_tasks` IN_PROGRESS, computes free slots vs
   `MAX_PARALLEL_ISO_RIPS`,
2. dequeues QUEUED rows FIFO with `FOR UPDATE SKIP LOCKED`,
3. spawns one ephemeral ripper per task via the existing docker-py client
   ([main.py:98-108](../../services/backend/arm_backend/main.py#L98-L108)) with
   `auto_remove=True`, a unique hostname `arm-ripper-iso-{task_id[-12:]}`, and a
   `{label: task_id}` for cancel/force-stop,
4. a **stale-claim sweep** (reusing the 90 s threshold pattern,
   [config.py:63](../../services/backend/arm_backend/config.py#L63)) requeues or
   fails tasks whose worker died mid-rip — this *is* the crash-recovery story for
   ISO jobs, replacing the physical ripper's boot-probe.

### The worker: a "run one task, then exit" ripper mode

The ripper gains a third entry mode beside "poll a physical drive" and the
legacy one-shot env var. Given `ARM_RIP_TASK_ID`, it:

1. `POST /api/ripper/iso-tasks/{id}/claim` (atomic CAS to IN_PROGRESS, owner =
   hostname) — the same handshake transcoders use
   ([routers/transcoder.py register/claim](../../services/backend/arm_backend/routers/transcoder.py)),
   and gets back `{drive_id, container_iso_path, session_id}`,
2. runs `_run_pipeline(container_iso_path, pending_session_id=session_id)` — the
   **existing** pipeline
   ([job_controller.py:175](../../services/ripper/arm_ripper/job_controller.py#L175)),
3. on rip-complete (or failure) marks the task terminal and **exits** — no
   idle-forever, no WS command loop. The container is auto-removed.

There's **no `iso.rip` WS command** in this model (my first draft had one); the
dispatcher-spawn handshake replaces it, matching how transcoders are dispatched.
WS stays only for in-flight **cancel**, which mirrors transcode cancel: the
backend force-stops the labeled container.

## Drive identity — the one genuine new wrinkle

Transcoders don't create jobs, so they need no drive. ISO rippers **do** — and
`Job.drive_id` is a non-null FK
([job.py](../../packages/arm_common/arm_common/models/job.py)). Two options:

- **(A) Per-spawn ephemeral drive (recommended for v1).** The backend creates a
  `Drive` row when it spawns the worker (hostname `arm-ripper-iso-{suffix}`,
  `device_path` = the ISO ref) and hands its `drive_id` back at claim. The job
  attaches to it; the row persists as provenance ("ripped by ephemeral ISO worker
  X"). Add a `kind` discriminator (`optical` | `iso`) so the UI's live-drive list
  hides them. **Pipeline and owner-auth stay byte-identical** — biggest win.
- **(B) Decouple — nullable `Job.drive_id` + `Job.source`.** Cleaner long-term,
  but `drive_id` is load-bearing in drive-owner auth, `get_in_flight_job`, and
  rip-start/track/complete; relaxing it touches the whole rip path. Bigger, later.

Recommend **(A)** now, revisit **(B)** if ephemeral drive rows become noise.

## The ISO source: library now, uploads later

- **v1 (today): a server-side library directory.** A host path (e.g.
  `./iso-library`, NAS mount, etc.) bind-mounted **into the spawned worker** at
  `/isos` (read-only). Because the backend spawns via the host Docker daemon, the
  mount uses a **host path** the same way transcode mounts do
  (`ARM_HOST_RAW_PATH`/`ARM_HOST_MEDIA_PATH`,
  [config.py:78-80](../../services/backend/arm_backend/config.py#L78-L80)) — add
  `ARM_HOST_ISO_LIBRARY_PATH`. `GET /api/iso/library` lists what's available for
  the picker; the backend also mounts it read-only so it can enumerate + validate.
- **Future (deferred): UI upload.** A browser upload writes the `.iso` into the
  same library/staging dir, then enqueues an identical `rip_tasks` row. **The
  ephemeral-spawn core does not change** — uploads are just a new way to populate
  the library. Multi-GB resumable upload, staging storage, and GC are the real
  work and are out of scope for v1.

## Backend changes

- **`POST /api/iso/rips`** (JWT): body `{ iso, session_id }`. **Enforce path
  containment** — `iso` names a file *relative to the library root*; resolve with
  `realpath` and reject anything escaping it, the same barrier just added for
  `job_id` path sinks (commits `144d063d`, `6443d24b`). **Never accept an
  absolute/arbitrary client path** — this is the feature's #1 security property.
  Inserts a QUEUED `rip_tasks` row; returns `task_id`.
- **`GET /api/iso/library`** (JWT): enumerate the mounted library for the picker.
- **`POST /api/ripper/iso-tasks/{id}/claim`** + heartbeat (service token): the
  worker handshake, cloned from the transcoder claim
  ([routers/transcoder.py:134](../../services/backend/arm_backend/routers/transcoder.py#L134)).
- **Rip dispatcher + `rip_tasks` migration**, cloned from transcode.
- **Cancel**: force-stop the labeled container, mirroring transcode cancel.

The Docker socket is **already** mounted into the backend for transcode spawns
([docker-compose.yml:68-70](../../docker-compose.yml#L68-L70)) — no new privilege
is taken on; the root-equivalent risk is already accepted in
[06-deployment.md](06-deployment.md).

## Ripper changes

- **Task-mode entrypoint** keyed off `ARM_RIP_TASK_ID`: claim → `_run_pipeline`
  → exit. No poll loop, no idle.
- **Auth model = transcoder, not physical ripper.** Transcoders mount only the CA
  cert and auth with `ARM_SERVICE_TOKEN`; they have no per-container leaf cert.
  Ephemeral ISO rippers should do the same — which sidesteps the "issue a stable
  `arm-ripper-iso` leaf cert" problem entirely (an ephemeral worker can't have a
  stable cert). *Confirm* whether the ripper REST/WS surface currently mandates a
  client leaf cert; if so, relax it to token-only for task-mode workers.
- **Log identity from an explicit name, not the device.** Today the log file is
  derived from `ARM_DRIVE_DEV`
  ([main.py:33](../../services/ripper/arm_ripper/main.py#L33)); the transcoder
  instead takes an explicit `ARM_SERVICE_NAME`. Adopt the same so each worker
  logs to `arm-ripper-iso-{suffix}.log` — unique per spawn, zero collision.

## What disappears

- The **"stop the live ripper"** dance in the smoke script — ephemeral workers
  have unique hostnames + unique log names and never touch `/dev/sr0`, so there's
  no interaction with `arm-ripper-sr0` at all. (The script's "same drive_id"
  rationale was already inaccurate — different hostnames, different drive_ids.)
- The **idle-forever** container and the bespoke **`docker run`** block.
- The original **compose-overlay** idea from our discussion. An ephemeral worker
  isn't a compose service, so there's no `docker-compose.iso.yml` — exactly like
  there's no `docker-compose.transcode.yml`. The GPU-overlay analogy dissolves;
  the correct analogy is the transcoder, which ships as an **image + backend
  settings**, not a service.

## Deployment

No long-running service. Just:

- Build the **`arm-ripper-iso` image** (likely the existing ripper image with the
  task-mode entrypoint; possibly the same image, different command).
- Backend settings, mirroring the transcode ones
  ([config.py:53-86](../../services/backend/arm_backend/config.py#L53-L86)):
  `ARM_ISO_RIPPER_IMAGE`, `MAX_PARALLEL_ISO_RIPS`, `ARM_HOST_ISO_LIBRARY_PATH`,
  reusing `ARM_DOCKER_NETWORK` and the existing host-path settings.
- GPU is irrelevant to ripping (it's a MakeMKV/file op); the spawn omits the GPU
  kwargs entirely.

## Concurrency

Falls out of the dispatcher for free: natural parallelism, one container per
task, capped by `MAX_PARALLEL_ISO_RIPS` (default 1, like transcodes), queued FIFO
in `rip_tasks`. No 409-when-busy, no manual serialization — the queue handles it,
and it's the first real consumer of the deferred "queue mechanism" in
[07-open-questions.md](07-open-questions.md).

## Migration: the smoke test becomes a thin client

[devtools/iso-smoke.sh](../../devtools/iso-smoke.sh) collapses to: drop the
fixture in the library → `POST /api/iso/rips` → wait for the job → (optional)
existing transcode assertions. The fixture-fetch and key-resolution helpers stay
(genuine test scaffolding); the `docker run` block, the live-ripper stop/restart,
and the idle container all go away. `ARM_MANUAL_TRIGGER_ISO` is retired unless we
still want a no-backend single-container smoke.

## Decisions needed

1. **Drive identity** — per-spawn ephemeral drive + `kind` discriminator
   (recommended) vs decouple `Job.drive_id` (cleaner, bigger).
2. **Same image or a dedicated `arm-ripper-iso` image** — reuse the ripper image
   with a task-mode command (recommended) vs a separate build.
3. **`rip_tasks` shared with `transcode_tasks` patterns** — clone the table/sweep
   (recommended) vs a generalized `worker_tasks` abstraction over both.
4. **Library catalog** — backend enumerates a mounted dir (recommended) vs the
   worker reports inventory.
5. **Cancel semantics** — label force-stop like transcode (recommended) vs a WS
   abandon command.
6. **`MAX_PARALLEL_ISO_RIPS` default** — 1 (match transcode) vs higher (ripping is
   I/O-bound, not GPU-bound, so concurrency is cheaper).

## References

- [01-architecture.md](01-architecture.md) — the transcode-container topology this clones.
- [02-job-lifecycle.md](02-job-lifecycle.md) — the pipeline ISO ingestion reuses verbatim.
- [04-data-model.md](04-data-model.md) — `Drive`/`Job`/`transcode_tasks`; note the `output_mode='iso'` name clash.
- [06-deployment.md](06-deployment.md) — Docker-socket access already accepted for transcode spawns.
- [07-open-questions.md](07-open-questions.md) — the deferred queue mechanism this first exercises.
- [transcode_dispatcher.py](../../services/backend/arm_backend/transcode_dispatcher.py) — the spawn/dispatch/sweep template to clone.
- [Phase 15 in MASTER_IMPLEMENTATION_PLAN.md](../plans/MASTER_IMPLEMENTATION_PLAN.md) — where ISO-as-source is currently parked.
- [contributors/real-disc-smoke.md](../contributors/real-disc-smoke.md) — current `ARM_MANUAL_TRIGGER_ISO` smoke procedure.
