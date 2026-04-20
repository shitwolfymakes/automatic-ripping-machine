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

Terminal states for a `Job`: `ripped`, `ripped_partial`, `abandoned` (user gave up in UI), `failed` (identification failed catastrophically).

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

`waiting_identify` is the durable "this session application is parked until you tell us what the disc is" state. See [§ Unidentified and placeholder rips](#unidentified-and-placeholder-rips) for when it's used and the transitions around it.

### Transcode task state machine

`queued → in_progress → (done | failed | stale)`, with per-task claims and heartbeats — see `transcode_tasks.claimed_by` / `claim_heartbeat_at` in [04-data-model.md](04-data-model.md#transcode_tasks). Unlike the rip side, multiple ephemeral transcoder containers really do compete for queued tasks, so the claim mechanism is load-bearing here. The stale-claim sweep applies; HandBrake can't resume mid-transcode either, so `stale → queued` means "re-transcode that file from scratch" — but already-`done` sibling tasks in the same session application keep their output.

## Why rip-level restart but task-level checkpointing for transcode

Two different cost models drove two different choices.

**Rip side: whole-job restart on interruption.** Crash recovery for a rip means re-running MakeMKV against the disc and overwriting `/raw/<job_id>/`. We accept re-ripping done tracks because (a) MakeMKV has no mid-title resume, so the in-progress track is already a re-rip; (b) "done" in the DB doesn't guarantee the file is durable on disk without a per-track `fsync` we don't issue; and (c) interruptions are rare — a power outage every few months that costs an extra 30 minutes of re-ripping is cheaper than the machinery to make per-track resume safe.

**Transcode side: per-task checkpointing.** A session application can fan out into many transcode tasks (one per ripped track), and a 4-hour batch transcode losing all progress on a Backend restart is a different cost than a 45-minute rip losing progress on a power cut. Transcode tasks have stable inputs (the raw files in `/raw/`, which don't change), no spinning physical media to babysit, and run in ephemeral containers that come and go anyway — so they're a natural fit for claim-and-heartbeat with per-task retry. Done tasks are kept; only the interrupted ones re-run.

## Session model details

A **Session** is a named composition of (rip preset, transcode preset, output path convention) that can be applied to any rip of the matching media type. Sessions are what users pick in the UI; the two preset tables under them hold the reusable rip-strategy and encoding building blocks.

- **Three tables, one user-facing concept.** `rip_presets` govern ripper behavior (track selection, identification mode, output mode — tracks vs ISO vs data copy). `transcode_presets` govern encoding (HandBrake preset reference, abcde profile, container, hardware preference). `sessions` compose one of each plus an `output_path_template`. Full field lists in [04-data-model.md](04-data-model.md#rip_presets).
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

Cleanup: when every transcode task derived from a job reaches a terminal state and retention policy allows, the whole `/raw/{job_id}/` directory is removed. Retention is user-configurable; the default is "keep raw until all queued sessions complete, then remove."

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

The core design principle: **don't pretend to know what we don't know.** MakeMKV surfaces only a track layout (per-title durations, stream info) and the disc's volume label — no episode titles, no season or disc numbers, no "this is the main feature" signal; per-track names come back as generic `title_nn`. Title and year are resolved by the TMDB/OMDB lookup at identify time; **season and disc number for TV box sets are both user-supplied** (volume labels occasionally encode one or both as a hint — `WEST_WING_S03_D02` — but most don't, and TV box sets are the routine case where identify lands in `awaiting_user_id` waiting for the user to enter them). Defaults therefore generate mechanical names the user can rename in `/media` after transcode completes, for scanner-perfect matching.

**Movies** — relative path, prefixed by `Movies/` at write time:

- Longest feature-length track → `{Title} ({Year})/{Title} ({Year}) - {transcode_slug}.{ext}`
- Other feature-length tracks (≥ 80 min) → `{Title} ({Year})/{Title} ({Year}) - Track {NN} ({HH}h{MM}m) - {transcode_slug}.{ext}`
- User renames to `{Title} ({Year}) {edition-Director's Cut} - {transcode_slug}.{ext}` etc. when they know which alternate cut is which.

Multi-feature discs (extended editions, alternate endings) produce multiple feature-length tracks with *different* file sizes — the ripper surfaces these in the UI at rip-selection time so the user can pick which to rip. Alternate-angle tracks behave the same way at our layer: an "angle" is a DVD/Blu-ray feature where a single playlist encodes multiple time-synchronized video streams the player hot-swaps between via the remote's angle button (concert footage from different cameras is the canonical legitimate use; adult content is where it shows up most often in the wild). The disc-spec mechanism is in-title branching, but MakeMKV flattens that and enumerates each angle as its own title — so they appear in the selection UI as several long tracks of near-identical duration, indistinguishable from any other multi-feature case, and the user picks. No special handling. Whether these surfacing rules fire automatically is governed by the `rip_preset.track_filters_json` — the `main_feature` rip preset enables "flag multi-feature," `archive` disables it, `custom` lets the user wire their own rules.

**TV** — relative path, prefixed by `TV Shows/` at write time:

- All tracks → `{Show} ({Year})/Season {NN}/{Show} - S{NN}D{DD}T{NN} ({HH}h{MM}m) - {transcode_slug}.{ext}`

Season + disc + track + duration + session in a predictable, greppable pattern. **No auto-`SNNEMM`:** disc order is not always episode order, and silently guessing wrong is worse than shipping honest names. Users rename to `{Show} - S{NN}E{MM} - Episode Title - {transcode_slug}.{ext}` post-rip once they know which track is which.

"Play All" tracks (a single long track that concatenates every episode on the disc) appear with the same mechanical name, and land in the Season folder. They are *not* auto-detected and filtered — "duration ≈ sum of other tracks" doesn't work because special features on the same disc confound the heuristic. Instead, the ripper UI surfaces all tracks with their durations at rip-selection time, and the user deselects Play All (or any tracks they don't want) before the rip starts. The naming layer stays mechanical.

**Music (CD)** — relative path, prefixed by `Music/` at write time:

- `{Artist}/{Album}/{NN} - {Track} - {transcode_slug}.{ext}`

This is the one case where ARM has reliable track-level metadata (MusicBrainz, CD-Text), so we use it. Track titles are populated automatically. The transcode slug disambiguates parallel FLAC-and-MP3 sessions against the same CD (abcde profile name, slugified — same mechanism as the HandBrake case).

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

Templates are validated on session save: the backend expands the template against a synthetic job of the declared `media_type` and rejects the save if any token resolves to empty for a required slot. This is how we keep users from shipping a template that silently produces `/media/Movies/ ().mkv` on a real rip. Templates that reference `{transcode_slug}` are also rejected at save time when the session has no transcode preset attached.

### Concurrent write safety

Two layers of defense against overlapping writes to the same output path:

**Atomic rename on completion.** The transcoder writes to `<final>.arm-inprogress` in the final directory, `fsync`s, then `rename(2)` to the final path on success. Same filesystem, so the rename is atomic. Plex and Jellyfin don't match `.arm-inprogress` as a media extension, so half-written files are invisible to scanners — no "corrupt file" flags during transcode, no racy mid-transcode scanning. On crash, leftover `.arm-inprogress` files are swept by the transcoder at startup: any file matching `*.arm-inprogress` under `/media` with no corresponding `transcode_tasks` row in `in_progress` state is deleted. The `.arm-inprogress` suffix is unique to ARM so it never collides with `wget`/`aria2`-style `.part` files or editor `.tmp` files.

**Apply-time collision validation.** When a user applies a session to a job, the Backend resolves every task's output path *before* fan-out. Two failure cases:

1. **Cross-session collision** — two sessions' templates resolve to the same path. This is legal schema-wise: two sessions may share a `transcode_preset_id` while differing in `rip_preset_id` (e.g. one rips main feature only, the other rips the whole disc — the main-feature output path is produced by both). Caught at apply-time, not save-time: when the second session is applied to a job that already has the first session's outputs queued or on disk, the Backend surfaces the same overwrite prompt as the cross-job case below.
2. **Cross-job collision** — the same session applied to two different jobs that identify as the same title (user re-ripping a movie they already have). Caught at apply-time by a lookup against `transcode_tasks.output_path` for any row in `queued | in_progress | done` state, plus a filesystem check for files ARM didn't put there (pre-v3 content, manual user copies). On hit, the UI shows a dialog:

   > "This session would write `Iron Man (2008) - plex-1080p-h265.mkv`, which already exists. Options: (a) Overwrite the existing file; (b) Cancel."

   Option (a) sets `session_applications.overwrite = true`; the transcoder replaces the file atomically via the same `.arm-inprogress` → rename flow. Option (b) aborts the apply. No silent auto-suffix (`(2).mkv`) — that hides user intent and produces files neither scanner recognizes as meaningful versions.

**DB-level safety net.** A partial unique index on `transcode_tasks(output_path)` where `status IN ('queued', 'in_progress', 'done')` catches any path collision the apply-time check missed (concurrent applies, logic bugs). Failed tasks can share paths — their file is presumed absent.

**Idempotency.** Applying the same (session, job) pair twice returns the existing `session_application` rather than fanning out a second set of tasks.

### Unidentified and placeholder rips

When a user opts into placeholder-rip mode (`rip_presets.identification_mode = deferred_placeholder`, or the global `config.block_on_miss = false`), ripping proceeds immediately on an identification miss. The rip writes to `/raw/<job_id>/` exactly as a normal rip would — raw paths key on `job_id`, which is assigned pre-identify and is identity-independent (see [04-data-model.md § jobs](04-data-model.md)). **Nothing is ever renamed or moved as a consequence of identity resolution.**

Transcode is gated on identity, not on rip completion. Specifically:

- An auto-session queued via `drives.default_session_id` stays in `session_applications.status = waiting_identify` while the job is `awaiting_user_id`. No `transcode_tasks` rows exist yet — fan-out is deferred until identity resolves.
- A manual session apply against an unidentified job returns the same `waiting_identify` state rather than failing; the UI surfaces this as "queued — waiting for you to identify this disc."
- On identity resolution (`POST /api/jobs/{job_id}/resolve`), Backend transitions every `waiting_identify` session_application to `queued` and fans out `transcode_tasks` using the now-resolved title. Path templates expand against the resolved identity; output paths are correct from the first byte the transcoder writes.
- If the user changes identity *again* after transcoding has already started (rare — requires them to re-open the resolve dialog post-identification), already-completed transcode outputs stay where they are. This is identical to the "user renamed the movie after transcoding" case, which v3 treats as out-of-scope manual cleanup. Queued and in-progress tasks are not re-pathed mid-flight.

The raw-side cleanup rule from [§ `/raw` — intermediate storage](#raw--intermediate-storage) applies unchanged: `/raw/<job_id>/` is removed per retention policy once all its derived transcodes are terminal.

## UI touchpoints during a job's life

- **Create phase:** UI shows "waiting for disc" on idle rippers.
- **Identify miss:** UI shows a manual-identify modal; ripper blocks until user resolves.
- **Rip in progress:** UI shows per-track progress bars via WS.
- **Ripped:** UI shows the job with available actions — queue session(s), edit metadata, delete raw.
- **Session queued:** UI shows transcode progress per task.
- **Resume after crash:** UI shows a "resumed from crash" banner on affected jobs/sessions.
