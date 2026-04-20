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

## Track state machine (the one that matters for recovery)

Every track is a row with a status column. Checkpointing happens by writing to this row, not by writing checkpoint files on disk.

```
    ┌────────┐   ripper claims it        ┌─────────────┐
    │ queued │ ────────────────────────▶ │ in_progress │
    └────────┘                           └──────┬──────┘
                                                │
                      ┌─────────────────────────┼─────────────────────────┐
                      │                         │                         │
                      ▼                         ▼                         ▼
                  ┌──────┐                  ┌──────┐                  ┌──────┐
                  │ done │                  │failed│                  │stale │◀─── detected on startup
                  └──────┘                  └──────┘                  └──┬───┘
                                                                         │
                                                                         ▼
                                                                    ┌────────┐
                                                                    │ queued │ (re-enqueued)
                                                                    └────────┘
```

A `Track` carries these fields relevant to recovery:
- `status` — one of the states above.
- `claimed_by` — container id (or hostname) of the ripper currently working on it.
- `claim_heartbeat_at` — last time the ripper pinged "still alive."
- `attempts` — how many times this track has been tried. Used to cap retries.

## Crash recovery: the "stale claim" rule

On Backend startup, a one-shot sweep runs this query (semantically):

```sql
UPDATE tracks
   SET status = 'queued',
       claimed_by = NULL,
       claim_heartbeat_at = NULL,
       attempts = attempts + 1
 WHERE status = 'in_progress'
   AND (claim_heartbeat_at IS NULL
        OR claim_heartbeat_at < NOW() - INTERVAL '2 minutes');
```

Every ripper pings `PATCH /api/tracks/{id}/heartbeat` every 30 seconds while it holds a claim. If heartbeats stop (container died, host powered off, network partition), the next Backend startup re-queues the track. If the Backend itself died but rippers were still alive, the rippers continue their current track; on Backend restart, live heartbeats keep those claims intact.

The UI surfaces this: any track that was re-queued after a stale-claim sweep is marked "resumed from crash" until it next reaches a terminal state, and the job carries a "resumed" banner.

### What this buys us

- **Power cut mid-batch.** All `in_progress` tracks go back to `queued`. Rippers restart, claim, finish. Already-`done` tracks are never re-ripped.
- **One ripper crashes, others keep working.** Only the dead ripper's claims go stale; everything else continues.
- **Backend crashes, rippers keep going.** Rippers retry REST calls with exponential backoff (1s, 2s, 4s, 8s, 30s cap) — sibling containers on a Compose network don't partition, so realistic outages are a Backend restart of a few seconds. WS progress is fire-and-forget; if a heartbeat tick lands during the outage it's dropped, the next one replaces it. State-transition REST calls (`complete`, `fail`) retry until acknowledged. The DB row is still source of truth.

### What this does NOT do

- **Resume mid-track.** MakeMKV cannot resume a partial rip of one title. `in_progress → queued` means "re-rip that track from scratch." This is a deliberate accepted loss — the crash-resumability goal is batch-level, not byte-level.
- **Protect against corrupt output.** A rip that crashed halfway may leave a truncated file in `/raw/<job_id>/`. The re-rip overwrites it.

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

Identical in shape to the Track state machine: `queued → in_progress → (done|failed|stale)`, with heartbeats. The stale-claim rule also applies, though in practice HandBrake cannot resume mid-transcode either, so `stale → queued` means "re-transcode from scratch."

## Why track-level (not job-level) checkpointing

A single Blu-ray can take 45 minutes to rip. A batch of five BDs can take 4 hours. Losing progress to job-level checkpointing would force the user to manually identify and restart every partially-completed disc. Track-level granularity is the smallest unit that matches the natural retry boundary of the underlying tools (MakeMKV rips one title at a time; HandBrake transcodes one file at a time).

Byte-level checkpointing — resuming MakeMKV mid-title — would require tool cooperation we don't have. Track-level is the right floor.

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

The core design principle: **don't pretend to know what we don't know.** MakeMKV surfaces only a track layout (per-title durations, stream info) and the disc's volume label — no episode titles, no disc numbers, no "this is the main feature" signal; per-track names come back as generic `title_nn`. Title and year are resolved by the TMDB/OMDB lookup at identify time; disc number for multi-disc TV sets is user-supplied (volume labels occasionally encode it as a hint, but most don't, and TV box sets are the routine case where identify lands in `awaiting_user_id`). Defaults therefore generate mechanical names that the user can edit post-rip for scanner-perfect matching.

**Movies** — relative path, prefixed by `Movies/` at write time:

- Longest feature-length track → `{Title} ({Year})/{Title} ({Year}) - {transcode_slug}.{ext}`
- Other feature-length tracks (≥ 80 min) → `{Title} ({Year})/{Title} ({Year}) - Track {NN} ({HH}h{MM}m) - {transcode_slug}.{ext}`
- User renames to `{Title} ({Year}) {edition-Director's Cut} - {transcode_slug}.{ext}` etc. when they know which alternate cut is which.

Multi-feature discs (extended editions, alternate endings) produce multiple feature-length tracks with *different* file sizes — the ripper surfaces these in the UI at rip-selection time so the user can pick which to rip. Alternate-angle tracks don't manifest as separate long tracks (they live inside a single title via branching playlists), so they don't trigger this flow. Whether these surfacing rules fire automatically is governed by the `rip_preset.track_filters_json` — the `main_feature` rip preset enables "flag multi-feature," `archive` disables it, `custom` lets the user wire their own rules.

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
| `{season}` | — | ✓ | — | identification (zero-padded) |
| `{disc}` | — | ✓ | — | identification / user input (zero-padded) |
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
