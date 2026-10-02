# 10 - Rip from ISO (ISO-source ripping)

**Status: built.** This doc describes what shipped, superseding the earlier
"proposed design" draft and the rip-tasks/dispatcher sketch it contained.

## What this is, and the name clash to avoid up front

"ISO" means two unrelated things in v3, pointing in opposite directions:

- **ISO as _output_**: `rip_presets.output_mode = 'iso'` produces a full-disc
  `.iso` image *from a physical disc* instead of per-title MKVs (see
  [04-data-model.md](04-data-model.md)). Unrelated to this feature.
- **ISO as _source_**: rip *from* an existing `.iso` file as input, through the
  normal scan, identify, rip and transcode pipeline, with no physical disc
  involved. **This document is exclusively about this one.** It is always
  called *ISO-source ripping* or *"Rip from ISO"*, never just "ISO ripping".

## The shape, in one sentence

An operator picks an `.iso` from a read-only library folder on the server.
The backend creates a **virtual drive** for it and spawns a dedicated,
one-shot ripper container, which runs the ISO through the same scan, identify,
review, rip and transcode pipeline a physical disc uses. When the rip ends,
the container exits and the backend retires the virtual drive. No physical
drive's state is touched, and several ISO rips can run at once, up to an
operator setting.

## Virtual drives

Each ISO rip is a temporary row in `drives`, not a new table. Three columns
added by migration `0041_virtual_drives`:

| Column | Type | Notes |
|---|---|---|
| `kind` | VARCHAR, not null, default `optical` | `optical` or `virtual`. App-layer validated, never a Postgres `CREATE TYPE` enum. |
| `source_kind` | VARCHAR, nullable | `iso` today (a later `folder` kind is planned, not built). Set only for `virtual` drives. |
| `source_path` | VARCHAR, nullable | The ISO's path **relative to the ISO library**, never absolute or client-chosen. Set only for `virtual` drives. |

`DriveLifecycle` gained a `retired` value. A virtual drive is created
`enrolled`, so the existing register, heartbeat and reconcile paths treat it
as a live drive with no special-casing, and becomes `retired` once its rip
ends. Retired rows are kept, not deleted, so `Job.drive_id` and the job's
history stay intact; `GET /api/drives` hides them unless
`include_retired=true` is passed. A virtual drive's `hostname` is
`iso-<last 12 chars of its id>`; `serial` and `by_id_name` stay null.

`source_path`, `kind` and `source_kind` round-trip through `GET /api/drives`
and the UI's drive types.

### Optical-only endpoints

The drive scanner, prune, enroll, unenroll, ignore, unignore, rescan and
delete all apply to `optical` drives only: each returns 409 for a virtual
drive (`services/backend/arm_backend/routers/drives.py`). Settings > Drives
keeps listing optical drives only; the dashboard header's drive count also
counts `kind == optical` rows (the "N ripping" count still includes ISO
rips).

### Container spec

`ripper_manager.container_spec` branches on `drive.kind`
(`services/backend/arm_backend/ripper_manager.py`). A virtual drive's
container differs from an optical one in exactly what it needs to:

- **Mount:** only the chosen ISO, read-only, at `/source/<file name>`
  (`drive.device_path`). No `/dev/disk` bind, no device cgroup rules, no
  CDROM group.
- **Env:** `ARM_DRIVE_ID`, `ARM_SOURCE_PATH=/source/<file name>`,
  `ARM_SOURCE_KIND` (`iso`), and `ARM_SOURCE_SESSION_ID` when the operator
  picked a session at create time. No `ARM_DRIVE_DEV` or `ARM_DRIVE_BY_ID`.
- **Labels:** `arm.drive_id` (the usual one) plus `arm.virtual=1`.
- **Restart policy:** `no`. A one-shot container is meant to exit; the
  backend watchdog (below) does the cleanup, not Docker's restart logic.
- **Unchanged:** image, `/raw`, `/logs`, the CA cert, the service token,
  `PUID`/`PGID`.

Startup `reconcile` handles virtual drives the same way as optical ones,
after the watchdog's boot pass has already retired anything already finished
(see [Startup ordering](#startup-ordering)): an `enrolled` virtual drive whose
container is still alive and whose job is unfinished is respawned, so a rip
interrupted by a host crash restarts from scratch.

## The watchdog

Virtual-drive cleanup is a backend-owned watchdog, not something the ripper
or a per-handler hook does
(`services/backend/arm_backend/iso_rips.py::sweep_virtual_drives`). The
backend has no heartbeat timeout and no shared job-terminal hook, so one
sweep owns the whole lifecycle instead of threading cleanup through every
rip-complete, rip-failed and abandon path.

**The pass.** `sweep_virtual_drives` runs every 30 seconds as a lifespan task,
and once at startup, **before** `reconcile_enrolled_rippers` loads the
enrolled list. For each `enrolled` virtual drive, it reads the container's
Docker state through `ripper_manager.container_statuses`:

- **Running** (or any other live/transitional state, or `unknown` meaning
  Docker itself is unreachable): nothing happens. A Docker blip must never
  fail a live rip.
- **Exited, dead, or missing, with a terminal job or no job at all:** the
  drive is retired and its container removed.
- **Exited, dead, or missing, with a job that isn't terminal:** the job is
  marked `failed` (`ripped_at` set, a `rip.failed` event with reason
  `"ISO ripper stopped unexpectedly"`), then the drive is retired and the
  container removed.

Before it acts on a drive, the pass re-reads the drive and its latest job
`FOR UPDATE`. A drive that is no longer `enrolled` (a cancel retired it after
the listing) is skipped, and a job that has gone terminal is never failed.
Every retire commits first and removes the container after, so a slow
`docker stop` never holds the row lock.

A freshly created drive's container can briefly read as "missing" between the
`POST /api/iso/rips` row commit and the container actually starting, so a
120-second spawn grace (`SPAWN_GRACE_SECONDS`) means only a drive older than
that gets retired on "missing". A drive still inside its grace window is left
alone even if the container isn't up yet.

**Cancel.** `DELETE /api/iso/rips/{drive_id}` abandons the job through the
same transition `routers/jobs.py`'s manual abandon uses (both now call the
shared `job_abandon.abandon_job_transition` helper), which tells the ripper to
clean up over WebSocket. It then retires the drive immediately, without
waiting for the watchdog's next tick. Cancel locks the drive row first and
commits the abandon and the retire together **before** it removes the
container, so a watchdog pass that runs while the container is stopping sees
the drive retired and cannot turn the abandoned job into a failed one.

**Spawn failure.** If `ensure_running` fails in `POST /api/iso/rips`, the
drive is retired at once and the request answers 500 with the reason. A
virtual drive never sits `enrolled` with no container behind it.

### Startup ordering

The boot-time watchdog pass runs inside `reconcile_enrolled_rippers`, before
it loads the enrolled list. Otherwise reconcile would recreate the container
of an ISO rip that already finished while the backend was down, and rip it
again.

## Source mode (the ripper)

The ripper's `ARM_MANUAL_TRIGGER_ISO` test hook is gone. In its place:

- **`ARM_SOURCE_PATH`** (the in-container ISO path) and **`ARM_SOURCE_KIND`**
  (`iso`) select source mode. `ARM_DRIVE_DEV` becomes optional when
  `ARM_SOURCE_PATH` is set; `ARM_DRIVE_ID` is still required either way.
- **`ARM_SOURCE_SESSION_ID`** carries the session the operator picked at
  create time, if any. When unset, the usual automatic session selection
  applies.
- The drive handle is `DriveHandle.fixed(ARM_SOURCE_PATH)`; the heartbeat
  reports `LOADED`. Device readiness, eject, and the seated-disc guard keep
  their existing ISO branches (unchanged from before this feature).
- On start, the ripper registers, then runs the pipeline exactly once through
  `handle_manual_trigger(session_id=...)`, the same `_run_pipeline` a disc
  insert runs, except it does **not** check `auto_rip_on_insert`: the operator
  starting an ISO rip from the picker already is the explicit trigger
  (`services/ripper/arm_ripper/main.py::run_source_mode`).
- `JobController`'s review/identify wait (`resolution_timeout`) is `None` in
  source mode, so the ripper waits indefinitely at a review or identify gate
  instead of timing out after the usual 30 minutes. A parked ISO rip holds
  its slot until the operator resolves it or cancels.
- The ripper exits (code 0) whenever its one pipeline run ends: rip complete,
  rip failed, abandoned (cancellation), or an early end such as a scan
  failure or a rejected identify. Its restart policy is `no`; the backend
  watchdog does the rest.

### Images MakeMKV cannot open: the extract fallback

MakeMKV normally reads the image directly (`iso:<file>`). Some images crash
its image reader before it lists a title (seen with DVDFab UDF 2.50 Blu-ray
backups: `makemkvcon info iso:` exits with SIGSEGV), although MakeMKV reads
the same disc fine from a folder. Mounting the image is not an option: it
needs `CAP_SYS_ADMIN`, loop devices and an AppArmor exception, and the ripper
runs unprivileged.

So when the direct scan of an ISO yields no titles, the scan dispatcher
(`arm_ripper/scan/dispatcher.py::_scan_extracted`) unpacks the image with
7-Zip's UDF reader (`arm_ripper/iso_extract.py`, `7z x -tudf`) into
`/raw/.iso-extract/<drive_id>/<image name>/` and scans again. Once an
extraction exists, `source.makemkv_source_url` answers `file:<folder>` for the
image, so the rescan and the later rip both read the folder: the job shows the
disc's titles and rips them like a disc (one `makemkvcon mkv … all`). The
image's own volume label (blkid) replaces the folder name MakeMKV reports.

- The fallback needs free space under `/raw` of at least the image size; it is
  skipped (logged) otherwise. It also refuses an image with no `BDMV` or
  `VIDEO_TS` folder at its root.
- The ripper removes the extraction when its pipeline ends
  (`run_source_mode`); `retire_virtual_drive` removes
  `<RAW_ROOT>/.iso-extract/<drive_id>` too, for a ripper stopped first.
- If the extracted folder has no titles either, the extraction is dropped:
  `scan_data` classifies the image by its directory names (so it can still be
  identified), and rip-start **fails** the job with "MakeMKV found no titles in
  this ISO, even after unpacking it" (a `rip.failed` event carrying that
  reason, then 422), like a disc with no titles. It is never switched to the
  "ISO: Full-disc dump" session automatically: that once filed the `.iso`
  where a movie was expected. An operator who wants the raw copy picks that
  session deliberately, and rip-start honours it whatever the scan found.

### Incomplete images are refused up front

A copy or download that stopped partway leaves an image shorter than its own
file system (seen on hifi: a 13.8 GB file of a 32 GB BD-50, which made
MakeMKV crash and 7-Zip find 104 of 114 streams unreadable after a 17-minute
unpack). `POST /api/iso/rips` reads the ISO 9660 volume size and the UDF
partition descriptors (`arm_backend/iso_image.py`; milliseconds, stdlib
only) and refuses a file more than 64 MB short of its declared end with a
422: "This ISO is incomplete: 13.8 GB of 32.0 GB is present ...". Layouts it
can't read are not judged. When an unpack is still rejected, the ripper logs
every unreadable file and 7-Zip's archive-level errors in full.

### Preparing: before the job exists

An ISO rip has no job until identify, and the scan before it can be long
(MakeMKV opening a Blu-ray image, or the extract fallback unpacking 25-50 GB
over a network share). So the ripper reports a **preparing** phase instead:

- `arm_ripper/prepare.py`, configured only in source mode, posts
  `POST /api/ripper/iso-prepare` (`IsoPrepareReport`: `scanning`, or
  `extracting` with the percent and current file parsed from 7-Zip's `-bsp1`
  output). Phase changes go out at once, progress at most every 3 s, and the
  current phase is re-sent every 15 s as a keepalive. Failures are logged and
  ignored.
- The backend keeps the latest report per drive **in memory**
  (`arm_backend/iso_prepare.py`; no migration, the backend is one process)
  and emits a non-persisted `ripper.events` / `iso.preparing` event, which
  wakes the dashboard's refresh. A status not refreshed for 60 s ages out;
  identify (the job exists) and retire (the rip is over) clear it.
- `GET /api/iso/rips/preparing` lists them; the dashboard shows a
  **PREPARING** section (`IsoPreparingRow`) for every live virtual drive that
  has no active job yet, with the phase, progress, current file and Cancel.

## The API

All routes under `/api/iso` require writer (admin) access, except the `GET`,
which only requires login (`services/backend/arm_backend/routers/iso.py`).

- **`GET /api/iso/library?subpath=`**: `IsoLibraryListing { host_path,
  subpath, parent_subpath, entries: [{ name, kind: "folder"|"iso",
  size_bytes?, modified_at?, ripping }] }`. It reuses the Files browser's
  `(root, subpath)` resolution (`file_browser.resolve("ISO", ...)`), so `..`
  and symlinks that escape the library root are rejected (400). It lists
  folders before `.iso` files, lowercase only, and hides anything else.
  Answers 503 `{detail}` when the library isn't configured (the env var
  unset, or the read-only mount missing).
- **`POST /api/iso/rips`**: body `IsoRipRequest { path, session_id? }`,
  `path` relative to the library. Returns `201 IsoRipCreated { drive_id }`.
  Errors:
  - 400: not a `.iso`, or the path escapes the library;
  - 404: missing file, or unknown `session_id`;
  - 409: ripping is paused with the review hold off
    (`"ripping is paused; no new jobs accepted"`; paused with the hold on,
    as the UI Pause toggle sets it, starts the rip and parks it for review
    like a disc in a drive), the `max_parallel_iso_rips` cap is full
    (the message names the cap), or that ISO is already ripping;
  - 503: not configured;
  - 500: spawn failed; the drive is retired before the response goes out.

  Create is serialized by an in-process lock (`iso_rips._create_lock`) so two
  concurrent requests can't both pass the cap/duplicate checks before either
  commits its row. Inside the lock it runs one watchdog pass first, so a rip
  that finished since the last tick no longer counts against the cap.
- **`DELETE /api/iso/rips/{drive_id}`**: cancels the rip. It abandons its job
  if one exists and isn't already terminal, retires the drive, commits, and
  then removes the container. Returns 409 for an optical drive, or one that's already
  retired or not an active ISO rip.

Ripper `register` accepts an `enrolled` virtual drive matched by id alone;
optical drives keep the existing `by_id_name` check. The OpenAPI snapshot and
generated TypeScript types cover all three routes.

## The UI

- The gear menu's "Rip from ISO" item opens the `IsoPicker` slide-over (the
  old Import wizard, `ImportWizard.svelte` / `IngressBrowser.svelte`, and the
  `import-jobs.ts` client are all deleted). The picker lists the library via
  `GET /api/iso/library`, lets the operator navigate folders and pick an
  `.iso`, optionally choose a session, and calls `POST /api/iso/rips`.
- An ISO rip reuses the existing disc dashboard card, states and buttons. Its
  drive chip is replaced by a source chip (file name, middle-truncated), and
  drive-only actions (eject, enroll, manual trigger) are absent; Cancel
  calls `DELETE /api/iso/rips/{id}`. When the job ends, the card leaves the
  dashboard, and the job itself stays in All jobs.
- Settings > Ripping has **"Max parallel ISO rips"** (1 to 8, default 1).
  Settings > Drives and the setup wizard's drive scan list optical drives
  only; in-flight ISO rips never appear there.
- The dashboard's drive-name map is built from `GET /api/drives?include_retired=true`,
  so a finished ISO job still shows the file name, not a raw drive id.
- The gear item and the picker are shown to writers and admins only.
- The Files root "ISO library" (`services/backend/arm_backend/file_browser.py`)
  is read-only.

## Configuration

- **`ARM_HOST_ISO_LIBRARY_PATH`** (`.env`, host path). When set, the compose
  template mounts it read-only into the backend at `ISO_INGRESS_ROOT`
  (`/ingress`), and the backend also gets it as an env var so it can build
  spawn mounts (`<host library>/<relative path>`) and show the operator the
  host path. It must be an absolute path (a relative one would make Docker
  read the bind source as a named volume). When unset or relative,
  `GET /api/iso/library` and `POST /api/iso/rips` both answer 503, and the UI shows a short setup note. See
  [Configuring ARM, the `.env` file](../../user/Configuring-ARM.md).
- **`config.max_parallel_iso_rips`** (Settings > Ripping; an int, default 1,
  range 1 to 8). Counts `enrolled` virtual drives, independent of any
  physical-drive concurrency.
- `devtools/setup-dev.sh up` creates `arm/iso-library` so a dev stack has
  somewhere to drop fixture ISOs.

## Limits

These are deliberate non-goals of this feature, not oversights:

- **Only `.iso` files.** Extracted disc folders (`BDMV` / `VIDEO_TS`) are a
  planned next `source_kind` (`folder`, using MakeMKV's `file:` source) but
  are not built.
- **No queueing.** When the `max_parallel_iso_rips` cap is full, or the same
  ISO is already ripping, `POST /api/iso/rips` is refused with 409. There is
  no queue to land in and retry automatically.
- **No browser upload.** The library is a server-side, read-only folder the
  operator populates themselves (or via a NAS mount); there is no UI upload
  path.
- **Duplicate-disc reuse doesn't apply.** `disc_dedupe.find_reusable_job_for_disc`
  only matches unfinished jobs on the same drive, and each ISO rip gets a
  fresh virtual drive, so re-ripping the same ISO always creates a new job
  and never reuses a previous one.

## Testing

`devtools/iso-smoke.sh` drives the full pipeline end to end, with no physical
disc involved: it stages a fixture ISO into the library, calls
`POST /api/iso/rips`, follows the job to `ripped`, then applies and polls a
transcode session. It no longer borrows or pauses a real drive's ripper. See
[Real-disc smoke, ISO fixture](../contributing/real-disc-smoke.md#run-the-test-iso-fixture--no-physical-disc-needed).
The backend-side tier-1 suite covers the drive-kind rules, the library
listing, every `POST`/`DELETE /api/iso/rips` error path, the virtual
container spec, every watchdog branch, startup ordering, and the
migration's upgrade/downgrade, at 100% statement coverage.

## References

- [01-architecture.md](01-architecture.md): service topology.
- [02-job-lifecycle.md](02-job-lifecycle.md): the pipeline an ISO rip reuses verbatim downstream of scan.
- [04-data-model.md](04-data-model.md): `Drive`/`Job`, and the unrelated `output_mode='iso'` name clash.
- [09-testing.md](09-testing.md): the tier-1/e2e test split this feature's suite follows.
- `services/backend/arm_backend/iso_library.py`, `iso_rips.py`, `job_abandon.py`, `routers/iso.py`: the backend implementation.
- `services/backend/migrations/versions/0041_virtual_drives.py`: the schema change.
- `services/ripper/arm_ripper/main.py` (`run_source_mode`, `amain`): the ripper's source mode.
- [devtools/iso-smoke.sh](../../../devtools/iso-smoke.sh): the end-to-end smoke test.
