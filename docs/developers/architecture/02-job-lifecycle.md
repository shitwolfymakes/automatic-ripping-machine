# 02 — Job Lifecycle & Crash Recovery

Crash-safe batch ripping is a top-three reason v3 exists. This document spells out exactly what state a job can be in, what triggers a transition, and how the system recovers after an unclean shutdown.

## Entities

Four long-lived entities drive the lifecycle, plus one reusable template:

- **Job** — one disc insertion. Created when a ripper identifies an inserted disc. Owns the overall rip outcome.
- **Track** — one logical piece of a disc (one title on a DVD/BD, one song on a CD, one dump on a data disc). Created per track once identification succeeds. This is the **unit of checkpointing**.
- **Session Application** — the durable record of "apply session S to job J." Created when a user (or `drives.default_session_id` auto-apply) queues a session against a rip. Carries its own state machine and owns the fan-out into **Transcode Tasks**.
- **Transcode Task** — the unit of work a single `arm-transcode` container executes. One session application fans out to N tasks, one per track being transcoded.

**Session** is not itself a lifecycle entity. It is a named, reusable bundle of (rip preset, transcode preset, output path template) scoped to a media type. Users pick a session to apply to a rip; applying creates a Session Application. Full definition in [§ Session model details](#session-model-details).

## Job state machine

```
     (disc inserted)
           │
           ▼
       ┌─────────┐   identify fails       ┌──────────────────┐
       │ created │ ─────────────────────▶ │ awaiting_user_id │
       └────┬────┘                        └────────┬─────────┘
            │ identify OK                          │ user resolves in UI
            ▼                                      ▼
       ┌────────────┐  ◀─────────────────────────  │
       │ identified │                              │
       └─────┬──────┘                              │
             │ first track begins                  │
             ▼                                     │
       ┌────────────┐   one or more tracks fail, others succeed
       │  ripping   │ ─────────────────────┐
       └─────┬──────┘                      │
             │ all tracks done             │
             ▼                             ▼
       ┌────────────┐                ┌─────────────────┐
       │  ripped    │                │ ripped_partial  │
       └─────┬──────┘                └────────┬────────┘
             │                                │
             └──────────────┬─────────────────┘
                            ▼
                    (disc ejected, ripper idle)
                    (downstream session applications may queue)
```

Terminal states for a `Job`: `ripped`, `ripped_partial`, `abandoned` (user gave up in UI), `failed` (identification failed catastrophically). Abandoning also ejects the disc: the ripper's `job.abandoned` WS handler pops the tray when the abandoned job owns the drive's pipeline (ripping or parked) or when the drive sits idle with the disc still seated — a stale abandon while a different job's rip owns the drive never touches the tray.

Not drawn: `awaiting_review` sits between `created` and `identified`/`ripping` for the timed review gate (`hold_for_review`), a previously-ripped hold, and a suggestion hold (next section); `ripped_awaiting_identify` is a placeholder rip waiting for a title.

### A disc that was ripped before

Identify first reuses a pre-rip job on the same drive with a matching fingerprint (a re-scan of the same disc; `disc_dedupe.find_reusable_job_for_disc`). Failing that, it looks for an **earlier rip** of the disc: any job on any drive in `POST_RIP_JOB_STATUSES` (`ripped`, `ripped_partial`, `ripped_awaiting_identify`) sharing any `(algo, value)` fingerprint (`find_previous_rips`; the newest is the one named). `failed` and `abandoned` never count, and deleting a job deletes its fingerprints. `config.on_previously_ripped` then decides:

- **`hold`** (default): the new job runs identify as usual, then parks in `awaiting_review` with `metadata_json.previously_ripped = {job_id}` and **no** `wait_start_time`, so the ripper's review wait never auto-starts it, a ripper restart re-parks it (`held-job` reports it paused), and un-pausing does not start a countdown. The review card shows the earlier rip (`JobDetailView.previous_rip`: date, status, whether its finished outputs are still on disk) with **Rip again** (`rip-start-review`) and **Discard** (abandon).
- **Suggestion hold** (not a duplicate-disc policy; it follows an identify hit): each media type has an auto-apply switch (`movie_auto_apply`, `episode_auto_apply` for TV, `music_auto_apply`; `auto_apply_for(cfg, kind)`). With the switch on, a hit is applied as identify always did. With it off, the job keeps the miss title (BDMT name, else the TheDiscDB release title, else the raw label), gets `flags.unidentified = true` and `metadata_json.identity_suggestion` (provider, title, year, kind, poster URL, external ids, overview, payload, `suggested_at`), and parks in `awaiting_review` with **no** `wait_start_time`; its review tracks are persisted and `rip.awaiting_review` is emitted. The TheDiscDB exact-id and release-metadata results go through the same gate, and a previously-ripped hold still wins. Like the previously-ripped hold, it has no countdown anywhere: un-pausing skips it, `POST /jobs/{id}/review-pause` answers 409, and the ripper's `held-job` probe reports it paused so a ripper restart re-parks it. Three ways out:
  - **Accept** (`POST /jobs/{id}/identity/accept`): applies the stored hit exactly as identify would have and removes the section, through the shared resolve path (provenance, fan-out, `identify.resolved`, episode-stage trigger). With the review gate on the job stays `awaiting_review` and the countdown starts now (none while `ripping_paused`); with the gate off it becomes `identified` and the parked ripper proceeds, unless `ripping_paused`, in which case it stays held until un-pause stamps a countdown. A `ripped_awaiting_identify` placeholder follows resolve's promote rule (to `ripped`). On a job also held as previously ripped, accept applies the identity but leaves that hold as it is (still `awaiting_review`, no countdown); Rip again or Discard end it as before. 409 when there is no suggestion or the status is not resolvable.
  - **Resolve** (`POST /jobs/{id}/resolve`): the operator identified the disc another way, so the suggestion is cleared and the held disc waits for Start as any held disc does.
  - **Start without either**: rips a placeholder that parks at `ripped_awaiting_identify`, where accept still works.
- **`reject`**: no job. Identify records `rip.duplicate_rejected` against the earlier job (inbox by default), sets `drives.notice`, and answers 409 `{"reason": "previously_ripped", "job_id"}`; the ripper ejects on that. The notice clears on the drive's next identify, or when a heartbeat goes from `tray_open` to `no_disc` (the tray closed empty). A slot-loading drive reports `no_disc` straight after the eject, so its notice stays until the next identify.
- **`rip`**: no check.

`POST /api/jobs/{id}/rip-again` on any earlier rip starts a held copy of the disc if one is waiting (a previously-ripped hold sharing a fingerprint with it, whichever earlier rip the hold names), else sets `flags.rerip_allowed`. The next identify that matches any flagged earlier rip skips the check once and clears the flag on every match. ISO and folder sources go through the same identify, so the same rule applies.

### How identify decides

`POST /api/ripper/identify` (`routers/ripper.py`) runs these steps in order. Every online call goes through the source registry (`metadata/sources.py`, accessors in `identity/sources/registry.py`); `dispatcher.*` below is `metadata/dispatcher.py`; `sources_for(cfg, media_type, registry)` decides the ranked online walks; `fingerprint_sources`, `lookup_sources` and the fixed hint order (`enabled_hint_sources`) decide the rest.

| Step | Code | Settings |
|---|---|---|
| Fingerprints stored; a re-scan reuses the pre-rip job; an earlier rip of the disc follows the duplicate policy | `identify`, `disc_dedupe.find_reusable_job_for_disc`, `find_previous_rips` | `on_previously_ripped` |
| Disc hints (Blu-ray disc title metadata, volume label) → claims plus a cleaned search title | `identity/pipeline.run_disc_hints(sources=enabled_hint_sources(cfg))` | `disc_hint_sources` (a set; the order is fixed, `bd_title` before `label`) |
| TheDiscDB content-hash match → track claims | the `thediscdb` store lookup, `thediscdb.build_claims` | `thediscdb_enabled` |
| TheDiscDB IMDb id → the ranked sources for the release's kind (`lookup_imdb`); with no capable source the release itself names the disc (provider `thediscdb`) | `dispatcher.has_imdb_lookup`, `dispatcher.identify_from_imdb`, `thediscdb.release_result` | `movie_sources` / `episode_sources` and their keys |
| CD: disc-id walk | `dispatcher._identify_cd` → `sources_for(cfg, "music", ...)` → `lookup_disc_id` (on an exact disc-ID miss MusicBrainz is asked by TOC, `scan.cd_toc`; several fitting releases are held as a suggestion, not applied) | `music_sources` |
| Video: CRC64 fingerprint (DVD) | `fingerprint_sources(cfg, ...)` → `lookup_fingerprint` | `crc64service_enabled` |
| Video: title candidates (the hint title; the volume label only while `label` is enabled) searched per kind in the order the disc's shape suggests | `dispatcher._identify_video`, `_search_kind` → `search_title` | `movie_sources`, `episode_sources`, `disc_hint_sources` |
| External ids filled in (a TMDb hit gets its IMDb and TVDB ids; a non-TMDb hit with an IMDb id gets its TMDb id) | `dispatcher.fill_external_ids` | TMDb key |
| Hit: applied, or held as a suggestion when the kind's switch is off; miss: held for identification or ripped as a placeholder | `registry.auto_apply_for`, `identity.apply.apply_identity_result`, `suggest_identity`; `hold_for_review` branch; miss title = BDMT name (only while `bd_title` is enabled) → release title → raw label | `movie_auto_apply`, `episode_auto_apply`, `music_auto_apply`, `hold_for_review`, `block_on_miss`, `disc_hint_sources` |
| Resolver: claim precedence manual > TheDiscDB > episode match > hints > preset | `pipeline.resolve_job` → `resolve(claims_of(job), tiers=SOURCE_TIERS, ranks=source_ranks(cfg), disabled=disabled_source_ids(cfg))` | `episode_sources` (rank order; unticked sources dropped), `disc_hint_sources` (enablement), job pin |
| Episode stage (TV jobs; scheduled after the commit, runs in the background and re-resolves through `resolve_job`) | `identity/stage_runner.py`, `identity/episode_stage.py` | `episode_sources`, `episode_match_tolerance_seconds`, `episode_auto_apply`, job pin |

The interactive routes read the same registry. `GET /api/metadata/search` takes an optional `provider`: a named one must be a registered source that searches the requested `type` and has its key; without it the route uses `search_source(cfg, type, registry)`, the operator's `search_provider_<type>` choice, which falls back to the first usable listed source when the chosen one is not usable. `GET /api/metadata/lookup` takes `imdb_id` or `crc64`: an IMDb id walks `lookup_sources(cfg, "movie", ...)` (the movie list, chosen search provider first) and a `crc64` goes through `fingerprint_sources`. Of the music routes only `/music/search` uses `search_source`; `/music/{release_id}` calls the MusicBrainz client directly. `PATCH /api/config` validates ranked lists and selects against the field metadata's enum values (a test pins them to the registry) and rejects a select whose source key is not saved (`<key>: <label> needs its API key`).

## Track state machine

Every track is a row with a status column. Within a single rip, tracks move through this machine sequentially as the ripper works:

```
    ┌────────┐                           ┌─────────────┐
    │ queued │ ────────────────────────▶ │ in_progress │
    └────────┘                           └──────┬──────┘
                                                │
                                ┌───────────────┴───────────────┐
                                ▼                               ▼
                            ┌──────┐                        ┌──────┐
                            │ done │                        │failed│
                            └──────┘                        └──────┘
```

There is no `stale` state and no per-track claim. With one ripper container per drive (see [01-architecture.md](01-architecture.md)), the ripper that creates the tracks is the only writer for the lifetime of the disc — no other process can race for them.

A `Track` carries these fields relevant to recovery:
- `status` — one of the states above.
- `attempts` — how many times this track has been tried (incremented on a job-level reset; see below).

## Crash recovery: restart the rip from scratch

A rip is interrupted only by something that takes the whole ripper process down — overwhelmingly that means a power outage or a host reboot. Backend-only restarts don't interrupt rips (the ripper keeps working and replays its state-transition REST calls when Backend comes back); ripper-only crashes are rare in practice (single-purpose container, Docker restart policy brings it back in seconds).

When an interruption does happen, **the entire rip restarts from scratch**: every track for that job is reset to `queued`, the `/raw/<job_id>/` folder is wiped, the ripper re-runs MakeMKV against the disc, and previously-"done" tracks are re-ripped. There is no per-track resume.

Why no resume of done tracks? Three reasons:

1. **MakeMKV can't resume a partial title** — that boundary already forced re-ripping the in-progress one.
2. **Filesystem durability is not guaranteed track-by-track.** A "done" file recorded in the DB may not have hit disk before the power cut (no per-track `fsync`). Trusting it would risk silent corruption in the library.
3. **The cost is small in practice.** Interruptions are rare. Re-ripping a few done tracks on a once-in-a-blue-moon power cut is cheaper than carrying the durability machinery to make partial state trustworthy.

Two recovery paths trigger the reset:

- **Backend-startup sweep (one-shot, no timeout).** On boot, before serving traffic, Backend finds every job with `status='ripping'` — by definition all such jobs were interrupted, since Backend was just down — sets `resumed_from_crash=true`, resets every track for those jobs to `queued`, increments each track's `attempts`, and instructs the relevant rippers to wipe `/raw/<job_id>/` before re-rip.
- **Ripper-startup probe.** When a ripper container starts, it polls its drive (`ioctl(CDROM_DRIVE_STATUS)`); if a disc is present and Backend reports an in-flight job for the drive in `status='ripping'`, the ripper calls `POST /api/ripper/jobs/{job_id}/resume`. Backend performs the same reset (mark resumed, requeue all tracks, increment attempts) and the ripper wipes `/raw/<job_id>/` and starts over.

Both paths converge on the same DB transition; the difference is who initiates it (Backend on its own boot, or the ripper on its boot when Backend was up the whole time).

The UI marks a job "resumed from crash" until its next terminal state.

### What this buys us

- **Power cut mid-batch.** Every interrupted job is found by the Backend-startup sweep and restarted from scratch. No per-track timeouts to wait out, no orphan claims to clean up.
- **Ripper container crashes alone.** Docker restart brings it back; the ripper-startup probe handles the reset. Backend was never down so its in-memory WS subscribers reconnect naturally.
- **Backend crashes, rippers keep ripping.** Nothing to recover. Rippers buffer state-transition REST calls (`complete`, `fail`, `job-complete`) with exponential backoff (1s, 2s, 4s, 8s, 30s cap) until Backend is back. WS progress messages dropped during the outage are simply not delivered; the next message replaces them. The DB row is still source of truth.

### What this does NOT do

- **Resume mid-track or mid-job.** Interruption means full restart of the rip — every track, including ones the DB says were `done`. Accepted by design (see reasons above).
- **Detect a hung-but-not-crashed ripper.** If MakeMKV wedges without the container exiting, no automatic detection. The user sees flat progress in the UI and restarts the ripper container manually, which triggers the ripper-startup probe.

## A drive that drops off the bus mid-rip

A USB enclosure reset takes the drive away and brings it back moments later, usually under a new node (`sr0` -> `sr1`). The ripper process keeps running, so this is not the crash-recovery path above; the running rip handles it itself (`JobController._execute_rip`, DVD/BD `mkv all` rips only):

- **Stop.** A watcher reads the shared `DriveHandle` (the poll loop moves it) and sets a stop event as soon as the drive leaves the node the rip started on; `rip_disc` kills `makemkvcon` on it instead of letting it fail every remaining title against a dead node. The poll loop can be slower than makemkvcon, which fails the title the drive dropped under and moves on to the next (a `PRGC:5017` transition). So the dispatcher also asks `drive_lost` (handle moved, or the node answers ENXIO/ENODEV/ENOENT) as each title finishes, before finalising it. A drive gone at that point sets the stop event, and the title stays unfinished instead of going `done` with a cut-short file. The same probe runs on a title failure, and once more if makemkvcon exits cleanly after the drop. Unfinished titles are held back, not PATCHed `failed`.
- **Wait.** Up to `DEVICE_RETURN_WAIT_SECONDS` (180 s) for the handle to name a node that reports `DISC_OK`. No eject meanwhile: the disc has to stay in for the resume. The reattach handler skips its boot probe while the pipeline is active.
- **Resume.** Delete every `.mkv` no finished title owns (the half-written title), then run one more `mkv all` on the new node into `/raw/<job_id>/resume-N/`, passing the settled tracks as `skip_track_ids`. `mkv all` rips every eligible title again, so the output positions still line up; the settled titles get no callbacks and their duplicate files are deleted. This keeps the one-makemkvcon-per-disc rule: a resume is one more `mkv all`, never per-title calls.
- **Give up.** If the drive does not return in time, or after `MAX_DEVICE_RESUMES` (3) resumes, the held tracks fail with `last_error` saying the drive disconnected, and rip-complete classifies the job as `ripped_partial` as usual. Eject happens once, after the last pass, at whatever node the drive is on.

Unlike crash recovery, finished titles are kept: the process that wrote and hashed them never went away, so there is no durability question about them.

## Session Application & Transcode Task lifecycle

Session Applications are the runtime record of "apply this session to this job"; Transcode Tasks are the execution units that fan out from an application. They have separate lifecycles. (The Session itself is a template and has no runtime state — see [§ Session model details](#session-model-details).)

### Session Application state machine

```
  ┌─────────┐    user queues or auto-queued    ┌────────────────────┐
  │ drafted │ ───────────────────────────────▶ │ waiting_identify   │  (only if job is
  └─────────┘                                  └─────────┬──────────┘   awaiting_user_id
                                                         │              under a deferred_
                                                         │ identity     placeholder rip
                                                         │ resolves     preset)
                                                         ▼
  ┌─────────┐    user queues or auto-queued    ┌──────────┐
  │ drafted │ ───────────────────────────────▶ │  queued  │  (normal path: job already
  └─────────┘                                  └────┬─────┘   identified at apply time)
                                                    │ first task starts
                                                    ▼
                                              ┌───────────┐
                                              │ running   │
                                              └────┬──────┘
                                                   │
                               ┌───────────────────┼───────────────────┐
                               ▼                   ▼                   ▼
                          ┌─────────┐        ┌─────────────┐      ┌─────────┐
                          │  done   │        │done_partial │      │ failed  │
                          └─────────┘        └─────────────┘      └─────────┘
```

`waiting_identify` is the durable "this session application is parked until there is something to fan out" state: until the disc is identified, and until the rip has persisted its Track rows (the ripper writes them at rip-start, so a session applied or resolved before that has no tracks yet). Resolve and rip-complete both drain parked applications; whichever runs once tracks exist promotes them to `queued`. See [§ Unidentified and placeholder rips](#unidentified-and-placeholder-rips) for the transitions around it.

### Transcode task state machine

`queued → in_progress → (done | failed | stale)`, with per-task claims and heartbeats — see `transcode_tasks.claimed_by` / `claim_heartbeat_at` in [04-data-model.md](04-data-model.md#transcode_tasks). Unlike the rip side, multiple ephemeral transcoder containers really do compete for queued tasks, so the claim mechanism is load-bearing here. The stale-claim sweep applies; HandBrake can't resume mid-transcode either, so `stale → queued` means "re-transcode that file from scratch" — but already-`done` sibling tasks in the same session application keep their output.

### Transcode capability and the disabled state

Whether encode work can happen at all is a **two-layer switch**:

- **Tier 1 — `ARM_TRANSCODE_CAPABLE` (env, deployment fact).** Default `true`. A ripper-only install (`devtools/setup-dev.sh --ripper-only` in dev; `armctl install --profile ripper-only` in production) writes `false` — this box cannot run a transcode container, full stop. A configured `ARM_TRANSCODE_DOCKER_HOST` implies capability regardless of the flag (you cannot be incapable of something you've wired a remote docker host for); the contradictory combo (`ARM_TRANSCODE_CAPABLE=false` with `ARM_TRANSCODE_DOCKER_HOST` set) logs a startup warning rather than failing to boot. See [05-cross-cutting.md § Configuration strategy](05-cross-cutting.md#configuration-strategy).
- **Tier 2 — `config.transcode_enabled` (DB, runtime toggle).** The Settings → Transcoding switch. Enabling it is refused with `422` when the deployment isn't capable (Tier 1 gates Tier 2, not the other way round). A `NULL` column (rows that predate migration `0037_transcode_enabled`) reads as *enabled* — the seeder backfills it on next boot, so upgrading changes nothing for an existing install.

**Disabled gates ENCODE work only — passthrough is unaffected.** A session with no transcode preset, or a preset whose `tool` is `TranscodeTool.NONE`, is a file move, not an encode, and always runs regardless of either switch. Concretely, when transcode is not enabled (not capable, or capable-but-toggled-off):

- **Manual apply** of a session that resolves to an encode preset is refused with `422 transcoding is disabled (Settings > Transcoding); only passthrough sessions can be applied`.
- **Auto-apply and identity-resolve fan-out** skip the same way, with `skipped_reason="transcode_disabled"` on the outcome, instead of erroring — a `drives.default_session_id` auto-queue against an encode session on a disabled deployment just doesn't fan out, rather than raising.
- **Already-queued encode tasks are held**, not cancelled or dropped: `spawn_pending` (the dispatcher tick) leaves them in `queued` and re-checks every tick, so re-enabling `config.transcode_enabled` resumes them where the FIFO left off. A **running** container is left alone — it finishes; disabling doesn't kill in-flight work.

**Passthrough always executes in-process in the Backend dispatcher, never in a container.** `spawn_pending` classifies each queued task by its preset (`is_passthrough_preset`) before checking either capability switch: passthrough tasks skip both gates entirely and are not counted against `config.max_parallel_transcodes` — a ripper-only box with `ARM_TRANSCODE_CAPABLE=false` and no docker client still drains its passthrough queue every tick. The claim (task → `in_progress`, `claimed_by="backend-inprocess"`) is committed *before* the file move runs, so the `SELECT ... FOR UPDATE SKIP LOCKED` row locks from the batch select are released before any blocking, possibly cross-mount I/O — a slow passthrough move can't stall a freshly spawned encode container's `/claim` call. The move itself uses the same move-or-copy as the retired passthrough container (`transcode_none`): an `os.rename` into `/media` at the path `compute_outputs` resolved, which is atomic when `/raw` and `/media` share a filesystem. Across mounts (`EXDEV`, the shipped compose layout) it falls back to a chunked copy into `<final>.arm-inprogress`, renamed into place when complete, then unlinks the source, so a library scanner never sees a partially-copied file. Cancelling the task (`cancel_running`) sets the copy's cancel event, since there is no container to stop: the copy stops at its next chunk, removes the partial file, keeps the `/raw` source, and fails the task as `cancelled`. While it copies, the executor writes `progress_pct` (and `claim_heartbeat_at`) to the row every 2 s and publishes `transcode.progress.{task_id}`, as a container transcoder does; when the copy fires although `/raw` and `/media` share a filesystem, it logs a hint that one parent mount would make the move an instant rename. The transcodes UI sees the same task lifecycle either way.

**NFS / ownership note.** Because passthrough finalize runs inside the Backend process rather than a spawned container, it writes as the **Backend container's own uid** — the operator's `PUID` must have write access to `/media` (not just the transcoder's). `ARM_TRANSCODE_PUID` still governs the uid a *remote or encode* transcode container drops to, and is applied best-effort as a `chown` after an in-process move completes (a harmless no-op against a root-squashed export).

### Encoder claim and apply-time refusal

A transcode preset names one catalog **encoder** (`arm_common.encoders`), not
a codec plus a hardware preference. The dispatcher's `_claim_gpu_for_task`
resolves what to spawn from that id:

- `preset` and `cpu_<codec>` never touch a GPU: they spawn immediately.
- `any_<codec>` picks the best-ranked eligible device (NVENC, then QSV, then
  VAAPI, then device path) that is free. If eligible devices exist but are
  all busy, the task stays `queued`. **If no eligible device exists on this
  host at all, the task runs the CPU encoder for that codec** instead of
  waiting, so a built-in preset defaulting to `any_h265` keeps working on a
  CPU-only install.
- `<vendor>_<codec>` (a specific `qsv_*` / `nvenc_*` / `vaapi_*` id) only
  ever claims a device of that vendor. All busy: queue. **None eligible at
  apply time**: the apply is refused with `skipped_reason="encoder_unavailable"`,
  mapped to `422` for manual apply (auto-apply and the waiting-identify
  promotion skip the same way instead of erroring). **None eligible while a
  task is already queued** (the device was disabled, removed, or re-probed
  without that codec after the apply): the task fails with
  `last_error = "no enabled device has verified <encoder id>; re-probe or
  enable it in Settings > GPUs"`, retryable through the normal retry path.
  `any_*`, `cpu_*` and `preset` are never refused on availability.
- A device is **eligible** for a codec only when it is `enabled`, has been
  probed at least once (`probed_at IS NOT NULL`), and that probe's verified
  list includes the codec (`arm_common.encoders.gpu_is_eligible`). A device
  that is mid-probe right now is skipped by the claim exactly like a busy
  one, so a task queues rather than falling back to CPU while a probe is in
  flight.
- **Awaiting a first probe.** When no device is eligible but an enabled,
  never-probed device that could serve the encoder is awaiting its probe
  (`TranscodeDispatcher.awaiting_probe`: reserved by the boot pass in
  `pending_probe_gpu_ids`, running in `probing_gpu_ids`, or the boot pass has
  not listed its rows yet), the claim returns `queue` with reason
  `waiting for GPU probe` for `any_*` and vendor-pinned encoders alike, and
  the apply-time gate does not refuse a vendor-pinned encoder. A never-probed
  device with no probe scheduled keeps the fallback bounded: `any_*` runs on
  CPU and a vendor-pinned encoder fails as above.
- A preset whose stored `encoder` id is no longer in the catalog (a stale
  row from a removed encoder) fails at apply with `422` and at dispatch with
  `last_error = "preset <preset id> has unknown encoder '<value>'"`, failing
  only that task, not its session siblings.

See [Hardware Transcoding](../../user/Hardware-Transcoding.md) for the
per-device probe that populates eligibility and the vendor image variants
the dispatcher spawns.

## Why rip-level restart but task-level checkpointing for transcode

Two different cost models drove two different choices.

**Rip side: whole-job restart on interruption.** Crash recovery for a rip means re-running MakeMKV against the disc and overwriting `/raw/<job_id>/`. We accept re-ripping done tracks because (a) MakeMKV has no mid-title resume, so the in-progress track is already a re-rip; (b) "done" in the DB doesn't guarantee the file is durable on disk without a per-track `fsync` we don't issue; and (c) interruptions are rare — a power outage every few months that costs an extra 30 minutes of re-ripping is cheaper than the machinery to make per-track resume safe.

**Transcode side: per-task checkpointing.** A session application can fan out into many transcode tasks (one per ripped track), and a 4-hour batch transcode losing all progress on a Backend restart is a different cost than a 45-minute rip losing progress on a power cut. Transcode tasks have stable inputs (the raw files in `/raw/`, which don't change), no spinning physical media to babysit, and run in ephemeral containers that come and go anyway — so they're a natural fit for claim-and-heartbeat with per-task retry. Done tasks are kept; only the interrupted ones re-run.

## Session model details

A **Session** is a named composition of (rip preset, transcode preset, output path convention) that can be applied to any rip of the matching media type. Sessions are what users pick in the UI; the two preset tables under them hold the reusable rip-strategy and encoding building blocks.

- **Three tables, one user-facing concept.** `rip_presets` govern ripper behavior (track selection, identification mode, output mode — tracks vs ISO vs data copy). `transcode_presets` govern encoding (HandBrake preset reference, abcde profile, container, hardware preference). `sessions` compose one of each plus an `output_path_template`. Full field lists in [04-data-model.md](04-data-model.md#rip_presets). When `rip_preset.track_selection = custom`, `rip_preset.track_filters_json` carries the declarative filter (`min_duration_seconds`, `max_duration_seconds`, `title_indices` allowlist, `title_indices_exclude` blocklist — all conditions ANDed). The schema is owned by [`arm_common.schemas.TrackFilters`](../../../packages/arm_common/arm_common/schemas/sessions.py); the rip pipeline applies it via [`select_tracks`](../../../services/backend/arm_backend/track_selection.py).
- **Built-ins ship locked.** ARM seeds a set of built-in rip presets, transcode presets, and sessions on first boot, all with `is_builtin = true`. Built-ins are not editable through the API. The UI "New Session" wizard can pre-fill its form from any built-in, but saves a new row with `is_builtin = false`; no parent link is stored.
- **Sessions are scoped to a single media type** (`movie` | `tv` | `music` | `data` | `iso`). Any session can be applied to any rip *of the matching media type*. The UI filters the session picker by the rip's identified media type so the user can only pick a compatible session. `session.media_type` must equal the referenced rip preset's `media_type`, and (if a transcode preset is attached) the transcode preset's `media_type`.
- **Transcode preset is nullable.** ISO and data-copy sessions skip transcode entirely; their `transcode_preset_id` is null and no transcode task fans out.
- **Sessions are re-runnable.** A user can queue a session against a rip made six months ago. Re-running against a retired raw (if the user pruned it) is a clear error in the UI.

Concrete session fields (summary — full in [04-data-model.md](04-data-model.md#sessions)):

- `name` — unique per user (UI picker requirement; not used in filenames — `{transcode_slug}` handles that).
- `media_type` (enum: `movie` | `tv` | `music` | `data` | `iso`)
- `is_builtin` (bool)
- `rip_preset_id` (FK → `rip_presets`)
- `transcode_preset_id` (FK → `transcode_presets`, nullable)
- `output_path_template` — relative to the media-type library root; see "Output paths and naming" below.
- `overrides_json` — per-session tweaks layered on top of the referenced presets.
- `created_by_user_id`, `created_at`, `updated_at`

### Why the three-table split

v2 bundled rip strategy + transcode settings + output convention into a single "session" concept. That works for simple cases but doesn't cleanly express things the community has been asking for: home-movie rips (no identification), ISO dumps (no transcode), multiple output formats from the same source (MP3 + FLAC from the same CD), per-disc-type encoding differences (DVD vs Blu-ray vs 4K UHD). Decomposing rip behavior and transcode behavior into independently-reusable presets, then recomposing them at the session layer, keeps the user-facing story ("pick a session") while making the parts separately extensible. See GitHub discussion [#815](https://github.com/automatic-ripping-machine/automatic-ripping-machine/discussions/815) for the design origin.

## Output paths and naming

### `/raw` — intermediate storage

Rippers write to `/raw/{job_id}/`, one directory per disc insertion. Filenames inside follow MakeMKV's native output convention (`title_tNN.mkv`) plus any sidecars MakeMKV emits. This directory is internal to the pipeline and is never exposed to media scanners; users don't browse `/raw`.

Cleanup: when every transcode task derived from a job reaches a terminal state and retention policy allows, the whole `/raw/{job_id}/` directory is removed. Retention is user-configurable; the default is `keep_forever` — the data-hoarder profile from [00-vision.md](00-vision.md) is the dominant user, so the safe default is to keep raw bits until the operator explicitly opts out (set `default_retention_policy=prune_after_session` in the Config singleton, or per-job).

### `/media` — user-facing library

The top-level library shape mirrors the Plex/Jellyfin convention — both scanners agree at this granularity, so "Plex-friendly" and "Jellyfin-friendly" are the same thing:

```
/media/
  Movies/
    {Title} ({Year})/
      {Title} ({Year}) - {transcode_slug}.mkv
  TV Shows/
    {Show} ({Year})/
      Season {NN}/
        {Show} - S{NN}D{DD}T{NN} ({HH}h{MM}m) - {transcode_slug}.mkv
  Music/
    {Artist}/
      {Album}/
        {NN} - {Track} - {transcode_slug}.flac
```

The three top-level folder names (`Movies`, `TV Shows`, `Music`) are configurable per install (env vars, default to the above). The subtree shape is fixed by media type — changing it would break scanner matching, which is the whole point of picking a convention.

**Why `{transcode_slug}` is in the default filename.** The same raw rip is commonly transcoded in multiple encodings (1080p H.265, 4K HDR, phone-friendly). Including the transcode preset name as a suffix in the same folder is the native Plex/Jellyfin idiom for "versions of the same title" — both scanners group sibling files matching `{Title} ({Year}) - *.ext` as alternate versions, and the version selector on the movie page then shows `1080p-h265` vs `4k-hdr` as meaningful labels the user actually picked. Without this suffix, two transcodes of the same source would collide on one filename. `{transcode_slug}` is unavailable for ISO and data-copy sessions (no transcode preset); their default templates don't include it. See "Concurrent write safety" below for the handling when two sessions legitimately resolve to the same slug (e.g. same transcode preset, different rip preset).

### Filename templates: honest mechanical names

**Templates apply at transcode time, not rip time.** The rip step itself produces only `/raw/{job_id}/title_tNN.mkv` (MakeMKV's native naming) — see "/raw" above. Identity-derived filenames are an artifact of the transcoder writing into `/media/`, expanded against whatever identity has been applied to the job by then. Everything in this section describes the *transcode-output* names a user eventually sees in their library; nothing here runs during the rip.

The core design principle: **don't pretend to know what we don't know.** MakeMKV surfaces only a track layout (per-title durations, stream info) and the disc's volume label — no episode titles, no season or disc numbers, no "this is the main feature" signal; per-track names come back as generic `title_nn`. Title and year are resolved by the TMDB/OMDB lookup at identify time. Season, disc number and disc total are proposed from the Blu-ray disc title (BDMT) and the volume label when they encode them, and the operator's entry always wins; values carry their source in `identity_provenance`. Per-title season and episode come from TheDiscDB and operator edits, resolved with provenance tracking, and the `{season}` naming token prefers the title's own season over the disc's. TV box sets are the routine case where identify lands in `awaiting_user_id` waiting for the user to supply missing identity. Defaults therefore generate mechanical names the user can rename in `/media` after transcode completes, for scanner-perfect matching.

**Movies** — relative path, prefixed by `Movies/` at write time:

- Longest feature-length track → `{Title} ({Year})/{Title} ({Year}) - {transcode_slug}.{ext}`
- Other feature-length tracks (≥ 80 min) → `{Title} ({Year})/{Title} ({Year}) - Track {NN} ({HH}h{MM}m) - {transcode_slug}.{ext}`
- User renames to `{Title} ({Year}) {edition-Director's Cut} - {transcode_slug}.{ext}` etc. when they know which alternate cut is which.

Multi-feature discs (extended editions, alternate endings) produce multiple feature-length tracks with *different* file sizes — the ripper surfaces these in the UI at rip-selection time so the user can pick which to rip. Alternate-angle tracks behave the same way at our layer: an "angle" is a DVD/Blu-ray feature where a single playlist encodes multiple time-synchronized video streams the player hot-swaps between via the remote's angle button (concert footage from different cameras is the canonical legitimate use; adult content is where it shows up most often in the wild). The disc-spec mechanism is in-title branching, but MakeMKV flattens that and enumerates each angle as its own title — so they appear in the selection UI as several long tracks of near-identical duration, indistinguishable from any other multi-feature case, and the user picks. No special handling. Whether these surfacing rules fire automatically is governed by the `rip_preset.track_filters_json` — the `main_feature` rip preset enables "flag multi-feature," `archive` disables it, `custom` lets the user wire their own rules.

**TV** — relative path, prefixed by `TV Shows/` at write time:

- All tracks → `{Show} ({Year})/Season {NN}/{Show} - S{NN}D{DD}T{NN} ({HH}h{MM}m) - {transcode_slug}.{ext}`

Season + disc + track + duration + session in a predictable, greppable pattern. **No guessed `SNNEMM` from disc order:** disc order is not always episode order, and silently guessing wrong is worse than shipping honest names. Episode numbers come only from [episode matching](#episode-matching), and a template uses them through the `{episode}` token. When a template includes `{episode}`, the token renders `01-E02` for a title spanning two episodes, and a TV template's episode tokens render empty (instead of failing) for titles whose role is not an episode: the path segments holding them are tidied (`S01E - .mkv` becomes `S01.mkv`) and, if the template has no `{track}`, ` - T{track}` is appended to the file name so a disc's bonus titles never share a path.

"Play All" tracks (a single long track that concatenates every episode on the disc) appear with the same mechanical name, and land in the Season folder. The naming layer stays mechanical and does not filter them, but [episode matching](#episode-matching) detects them: a title whose length matches the sum of three or more consecutive episodes, or the sum of the other titles on the disc, is marked a Play All and given the role `extra`, so it is not matched to an episode. The ripper UI also surfaces every track with its duration at rip-selection time, and the user can deselect a Play All (or any track they don't want) before the rip starts.

**Music (CD)** — relative path, prefixed by `Music/` at write time:

- `{Artist}/{Album}/{NN} - {Track} - {transcode_slug}.{ext}`

This is the one case where ARM has reliable track-level metadata (MusicBrainz, CD-Text), so we use it. Track titles are populated automatically. The transcode slug disambiguates parallel FLAC-and-MP3 sessions against the same CD (abcde profile name, slugified — same mechanism as the HandBrake case).

### Episode matching

Per-track season and episode numbers (the `{episode}` token above) come from a separate background stage (`identity/episode_stage.py`), not from the identify step itself. It matches a TV job's tracks against ranked episode-list providers, by default TMDb, then TVmaze, then TVDB (`DEFAULT_EPISODE_SOURCES` in `identity/sources/registry.py`), comparing track runtimes (runtimes only, never titles) against each provider's episode list. Only one provider's placement is used for a job: the resolver takes the first usable provider in rank order, or the operator's pinned one, and ignores the rest. The stage runs after a TV candidate is identified, again at rip start (when a disc that was not held for review first gets its tracks), again whenever season, disc number, media type, the identity title or the show ids change (via `PATCH` or `/resolve`), and once at startup for any identified, `awaiting_review`, `awaiting_user_id` or `ripping` job that has no episode source entry yet, so a job is never left unmatched because it finished before this stage existed or because the backend restarted mid-rip. Ripped jobs are not swept. When the job's season is unknown, the stage fetches every season the provider lists, in this order: the season a disc hint (label or BDMT) proposed, then seasons that sibling discs of the same show hold (nearest the hint first), then the rest ascending. Only a hint- or sibling-proposed season can stop the scan early, and only when it ranks first and nothing would hold its fit; a season reached by the ascending fallback never stops it, so with nothing known every season is tried and ranked (`extra.scan_stopped_early` records whether the stop left seasons untried). Tracks the operator placed by hand (`identity_provenance.episode_number == "manual"`) are left out of the alignment, and their episode numbers are reserved like a sibling disc's, so the other titles align in the runs around them and no title is given an episode the operator already placed. TheDiscDB, when it knows the disc, claims the job's season (when its episodes are all in one season) and, on a single-season release, the disc number. Every result is applied to the tracks. A confident one is applied as is; an uncertain one is stored with `suggestion` set and applied as a guess: the resolver ranks a clean result above a held one within the episode tier (a pinned source above both), records the winner in `Resolution.episode_source` / `episode_unsure`, and `resolve_job` writes `identity_claims.unsure`, which `JobView.episodes_unsure` exposes. A guess never auto-starts: the ripper holds the review countdown while `episodes_unsure` is true, exactly as for a per-job pause, until a Fix match or re-run leaves a confident placement; Start rip by hand is unaffected. `extra.hold_reasons` lists why a result was held, in this order: `auto_apply_off`, `ambiguous` (ambiguous positions), `low_coverage`, `low_confidence`, `near_tie` (another season fits about equally), `thin_win` (a scanned season barely beats the runner-up), `nominal_runtimes`, `sibling_conflict`. Operators inspect and act on matches through `GET /api/jobs/{id}/identity`, `POST /api/jobs/{id}/identity/match` (preview by default, or apply and optionally pin a source; a season or disc number sent with an apply is kept as the operator's own; `scan_seasons` scans every season regardless of the job's season and cannot be combined with `season`), `DELETE /api/jobs/{id}/identity/match` (Clear episodes: forgets every episode source's result and the pin, re-resolves so the placements come off the tracks, keeps hand-placed tracks and the show ids), `DELETE /api/jobs/{id}/identity/pin` (kept for API compatibility; the UI no longer exposes a pin), and `GET /api/jobs/{id}/identity/episodes` (browse one season of a source's episode list; `season` is required), and `GET /api/jobs/{id}/identity/seasons` (the seasons a source lists for the show). The episode stage and these identity endpoints fire a `job.identity_updated` WS event whenever they run the resolver. Clearing the season, disc number or disc total in `/resolve` (an explicit `null`) forgets the operator's value, and the field falls back to what the other sources claim. Which providers run, in what order, the runtime tolerance (an upper limit: ARM narrows it to a tenth of the episode's runtime, at least 60 seconds) and whether confident matches apply as confident (`episode_auto_apply` off marks every TV match a guess, so it is still placed, shown amber and holds the countdown) are operator settings on Settings > Metadata > TV episodes (`episode_sources`, `episode_match_tolerance_seconds`, `episode_auto_apply`); unchecking a source stops it running and stops its stored matches applying, unless a job pins it. A manual `/identity/match` that names a source runs it even when that source is unchecked. A job pinned to a source keeps the tolerance stored when it was pinned. Which disc-hint sources run, and in what order, is set in the same section (`disc_hint_sources`); unchecking one stops it running and resets the fields it owned. Saving a change to either source list re-runs the resolver, then schedules the episode stage, for every job that is not finished: non-terminal jobs, ripped placeholders, and ripped jobs no session has been applied to yet. A newly checked disc-hint source has nothing stored for existing jobs (disc hints are read at identify), so it applies from the next disc.

Every identity writer (title search, `/resolve`, the automatic lookups) stores the show's `tmdb`, `imdb` and `tvdb` ids plus `ExternalIds.tmdb_kind` (`movie` or `tv`), because TMDb numbers movies and series in separate id spaces. The stage never uses a movie-kind TMDb id as a show id: such a job falls back to the IMDb or TVDB id or waits for a TV identity. `PATCH /api/jobs/{id}` accepts `media_type`, so the operator can switch a job between movie and TV (a change re-runs the stage), and title-search candidates carry their `external_ids`. `JobView` exposes `looks_episodic` (the disc is a set of same-length episodes, so the UI defaults to TV) and `has_series` (a usable show id exists).

In ui-neu, a TV job has a **Match Episodes** tab on the job page, and the same panel opens from the Home card's Episodes button. There is no accept step: whatever is on the tracks is what Start rip rips with. The status line names the source, an amber **Guess** chip when the placement came from a held result, and how many tracks are placed; a guess also gets one amber line naming the guessed season and its strongest reason, with an (i) for the rest, and the fit facts (the guessed season's count and the other seasons the scan fit). The controls are **Fix match** (the form: source, season, disc, tolerance, Preview, Apply; opened on the guessed season), **Clear episodes** (`DELETE /identity/match`), **View sources** (read-only), and per track a season control and an episode picker sorted by how close each episode's runtime is to the track's, with revert; rows placed by a held result read "Guess, TMDb". Once a track is set by hand, **Fill the rest** previews the source over the other tracks. The Home card's Episodes row says "Episodes placed, a guess" for a guess, and its countdown reads "Held: episodes are a guess" with no pause toggle while the ripper holds it. It is read-only for guests. The job page's **Info** tab edits title, year, season, disc number and disc total; a save that changes a TV job's season or disc number shows the panel as matching until the re-run reports back. The job header carries a Movie | TV switch (it asks before switching to Movie when tracks have hand-set episodes), and the title search has a Movie/TV toggle that defaults to TV for episodic discs. The panel ends its wait on `job.identity_updated`.

### `output_path_template` tokens

Sessions own the relative path from the media-type root down to the leaf filename. Tokens available at expansion time depend on the session's `media_type`:

| Token | movie | tv | music | Source |
|---|:-:|:-:|:-:|---|
| `{title}` | ✓ | — | — | identification |
| `{year}` | ✓ | ✓ | — | identification |
| `{show}` | — | ✓ | — | identification |
| `{season}` | — | ✓ | — | identification / user input (zero-padded) — usually user input for box sets, since volume labels rarely encode it |
| `{disc}` | — | ✓ | — | identification / user input (zero-padded) — same caveat as `{season}` |
| `{track}` | ✓ | ✓ | ✓ | MakeMKV / CD track number (zero-padded) |
| `{duration_human}` | ✓ | ✓ | — | MakeMKV (`{HH}h{MM}m`) |
| `{artist}` | — | — | ✓ | MusicBrainz / CD-Text |
| `{album}` | — | — | ✓ | MusicBrainz / CD-Text |
| `{track_title}` | — | — | ✓ | MusicBrainz / CD-Text |
| `{transcode_slug}` | ✓ | ✓ | ✓ | transcode preset `name` field, slugified (lowercase, spaces → hyphens, non-alphanumerics stripped). Unavailable when `session.transcode_preset_id IS NULL` (ISO, data-copy). |
| `{ext}` | ✓ | ✓ | ✓ | transcode preset `container` (`mkv`, `mp4`, `flac`, …) |

A token written `{token?}` is optional: when its value is empty it is dropped, together with a `()` or `[]` pair that wraps only it and one space before it, so `{title} ({year?})` becomes `Iron Man` for a title with no year. Empty path segments left behind are collapsed, and a path that is empty after the drop is rejected. `{ext}` and `{transcode_slug}` cannot be optional. A plain `{token}` that expands to empty fails the apply, with a hint to mark it optional. The built-in session defaults mark `{year}` optional (`{title} ({year?})/...`), so a title with no year gets a clean folder name.

Templates are validated on session save: the backend expands the template against a synthetic job of the declared `media_type` and rejects the save if any token resolves to empty for a required slot. This is how we keep users from shipping a template that silently produces `/media/Movies/ ().mkv` on a real rip. Templates that reference `{transcode_slug}` are also rejected at save time when the session has no transcode preset attached.

### Concurrent write safety

Two layers of defense against overlapping writes to the same output path:

**Atomic rename on completion.** The transcoder writes to `<final>.arm-inprogress` in the final directory; on success `atomic_output` `fsync`s the file, `rename(2)`s it to the final path, then `fsync`s the directory so the rename survives a power cut. Same filesystem, so the rename is atomic. Plex and Jellyfin don't match `.arm-inprogress` as a media extension, so half-written files are invisible to scanners — no "corrupt file" flags during transcode, no racy mid-transcode scanning. On crash, leftover `.arm-inprogress` files are swept by the transcoder at startup: any file matching `*.arm-inprogress` under `/media` with no corresponding `transcode_tasks` row in `in_progress` state is deleted. The `.arm-inprogress` suffix is unique to ARM so it never collides with `wget`/`aria2`-style `.part` files or editor `.tmp` files.

**Apply-time collision validation.** When a user applies a session to a job, the Backend resolves every task's output path *before* fan-out. Two failure cases:

1. **Cross-session collision** — two sessions' templates resolve to the same path. This is legal schema-wise: two sessions may share a `transcode_preset_id` while differing in `rip_preset_id` (e.g. one rips main feature only, the other rips the whole disc — the main-feature output path is produced by both). Caught at apply-time, not save-time: when the second session is applied to a job that already has the first session's outputs queued or on disk, the Backend surfaces the same overwrite prompt as the cross-job case below.
2. **Cross-job collision** — the same session applied to two different jobs that identify as the same title (user re-ripping a movie they already have). Caught at apply-time by a lookup against `transcode_tasks.output_path` for any row in `queued | in_progress | done` state, plus a filesystem check for files ARM didn't put there (pre-v3 content, manual user copies). On hit, the UI shows a dialog:

   > "This session would write `Iron Man (2008) - plex-1080p-h265.mkv`, which already exists. Options: (a) Overwrite the existing file; (b) Cancel."

   Option (a) sets `session_applications.overwrite = true`; the transcoder replaces the file atomically via the same `.arm-inprogress` → rename flow. Option (b) aborts the apply. No silent auto-suffix (`(2).mkv`) — that hides user intent and produces files neither scanner recognizes as meaningful versions.

**DB-level safety net.** A partial unique index on `transcode_tasks(output_path)` where `status IN ('queued', 'in_progress', 'done')` catches any path collision the apply-time check missed (concurrent applies, logic bugs). Failed tasks can share paths — their file is presumed absent.

**Idempotency.** Applying the same (session, job) pair twice returns the existing `session_application` rather than fanning out a second set of tasks.

#### Online sources

Every online title lookup goes through one registry (`arm_backend/metadata/sources.py`, accessors in `arm_backend/identity/sources/registry.py`). An adapter per provider (`tmdb`, `omdb`, `musicbrainz`, `arm_server`, `tvmaze`, `tvdb`) wraps the HTTP client and reports whether it is configured; `sources_for(cfg, media_type, registry)` is the only function that decides which sources run and in which order, with `lookup_sources` and `search_source` as its two thin views. The dispatcher walks that list per kind (movie or TV, in the order the disc shape suggests), the job page's search and IMDb lookup routes read the same list, and `MetadataResult.provider` is the source id, or `thediscdb` when a TheDiscDB match carries an IMDb id that no enabled source can resolve and the release itself names the disc. The order comes from the Identification settings: `movie_sources`, `episode_sources` (TV) and `music_sources`; a TheDiscDB IMDb match resolves through the same ranked sources, and the volume label is searched only while the `label` disc hint is enabled. A miss is titled by the BDMT disc name, else the TheDiscDB release, else the raw volume label. A hit from any source has its missing TMDb and TVDB ids filled from TMDb when a TMDb key is saved, so the episode stage can use every provider. (Spec: `2026-10-14-identification-sources-design.md`.)

### Unidentified and placeholder rips

When a user opts into placeholder-rip mode (`rip_presets.identification_mode = deferred_placeholder`, or the global `config.block_on_miss = false`), ripping proceeds immediately on an identification miss. The rip writes to `/raw/<job_id>/` exactly as a normal rip would — raw paths key on `job_id`, which is assigned pre-identify and is identity-independent (see [04-data-model.md § jobs](04-data-model.md)). **Nothing is ever renamed or moved as a consequence of identity resolution.**

Transcode is gated on identity, not on rip completion. Specifically:

- An auto-session queued via `drives.default_session_id` stays in `session_applications.status = waiting_identify` while the job is `awaiting_user_id`. No `transcode_tasks` rows exist yet — fan-out is deferred until identity resolves.
- A manual session apply against an unidentified job returns the same `waiting_identify` state rather than failing; the UI surfaces this as "queued — waiting for you to identify this disc."
- On identity resolution (`POST /api/jobs/{job_id}/resolve`), Backend transitions every `waiting_identify` session_application to `queued` and fans out `transcode_tasks` using the now-resolved title. Path templates expand against the resolved identity; output paths are correct from the first byte the transcoder writes.
- If resolve runs before the rip has started (no Track rows yet — the ripper persists them at rip-start), the application stays `waiting_identify` with `skipped_reason = no_tracks`. `rip-complete` drains parked applications before the drive-default auto-apply hook runs, so an explicit pre-rip session choice is never lost.
- If the user changes identity *again* after transcoding has already started (rare — requires them to re-open the resolve dialog post-identification), already-completed transcode outputs stay where they are. This is identical to the "user renamed the movie after transcoding" case, which v3 treats as out-of-scope manual cleanup. Queued and in-progress tasks are not re-pathed mid-flight.

The raw-side cleanup rule from [§ `/raw` — intermediate storage](#raw--intermediate-storage) applies unchanged: `/raw/<job_id>/` is removed per retention policy once all its derived transcodes are terminal.

## UI touchpoints during a job's life

- **Create phase:** UI shows "waiting for disc" on idle rippers.
- **Identify miss:** UI shows a manual-identify modal; ripper blocks until user resolves.
- **Rip in progress:** UI shows per-track progress bars via WS.
- **Ripped:** UI shows the job with available actions — queue session(s), edit metadata, delete raw.
- **Session queued:** UI shows transcode progress per task.
- **Resume after crash:** UI shows a "resumed from crash" banner on affected jobs/sessions.
