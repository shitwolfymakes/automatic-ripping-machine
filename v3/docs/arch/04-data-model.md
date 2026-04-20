# 04 — Data Model

Postgres 18 is the source of truth. All durable state lives here. No SQLite fallback, no sidecar state stores.

This document sketches the logical data model. Exact column types, indexes, and constraints land in the first Alembic migration — this is the shape, not the DDL.

## Conventions

- Primary keys are ULIDs (text, lexicographically sortable) prefixed with the entity name: `job_01HXYZ…`, `track_01HXYZ…`. This makes log lines and URLs legible.
- Every table has `created_at` and `updated_at` (`TIMESTAMPTZ NOT NULL DEFAULT now()`).
- Soft-delete is avoided. If a row needs to hide, a status column handles it.
- Foreign keys are enforced at the DB layer; no ORM-only relationships.
- Enums are Postgres enum types so they show up sanely in `psql`.

## Core entities

### `users`
One row per admin account. v3.0 has exactly one default user (`admin`) seeded on first boot, forced to change password on first login. Table exists to allow trivial multi-user later without a migration.

- `id` (ULID)
- `username` (unique, citext)
- `password_hash` (argon2id)
- `password_must_change` (bool, default true for seeded admin)
- `last_login_at`

### `config`
Single row. Runtime configuration that the UI writes to — third-party API keys, auto-transcode flag, default retention, etc. Values stored in plaintext.

- `id` (always 1 — sentinel)
- `tmdb_api_key` (text, nullable)
- `omdb_api_key` (text, nullable)
- `musicbrainz_user_agent` (text, nullable)
- `auto_transcode_on_idle` (bool)
- `default_retention_policy` (enum: keep_forever | prune_after_session | custom)
- `notification_apprise_urls` (text[] — list of Apprise-native URLs; UI is a textarea, validated on save)
- `session_signing_key` (bytea — auto-generated on first Backend boot; HS256 signing secret for user-auth JWTs; rotating this value invalidates all outstanding tokens)
- `updated_by_user_id`
- `updated_at`

### `drives`
One row per optical drive declared in compose.

- `id` (ULID)
- `hostname` (the ripper container's hostname, e.g. `arm-ripper-sr0`)
- `device_path` (`/dev/sr0`)
- `display_name` (user-editable)
- `status` (enum: online | offline | ripping | error)
- `last_seen_at`
- `rip_params_json` (jsonb: MakeMKV flags, DVD decrypt, etc.)
- `default_session_id` (nullable FK → `sessions.id` — if set and config's auto-transcode is on, queues this session after each successful rip)

Rippers register themselves at startup; Backend upserts this row by hostname. The UI lets the user rename, set `default_session_id`, and tweak rip params.

### `jobs`
One row per disc insertion the ripper detected (via its `ioctl(CDROM_DRIVE_STATUS)` poll loop).

- `id` (ULID)
- `drive_id` (FK → `drives.id`)
- `disc_type` (enum: dvd | bluray | cd | data | unknown)
- `title` (text, nullable — from metadata lookup, editable in UI)
- `year` (int, nullable)
- `metadata_json` (jsonb — full lookup result: artwork URLs, cast, synopsis)
- `status` (enum: created | awaiting_user_id | identified | ripping | ripped | ripped_partial | abandoned | failed)
- `resumed_from_crash` (bool, default false — set by stale-claim sweep)
- `started_at`, `ripped_at`

### `tracks`
The **checkpoint unit**. Every title on a DVD/BD or every song on a CD is a track row.

- `id` (ULID)
- `job_id` (FK)
- `kind` (enum: video_title | audio_track | data_dump)
- `index` (int — zero-based position on the disc)
- `source_ref` (text — MakeMKV title id / CD track number / etc.)
- `expected_duration_seconds` (int, nullable)
- `status` (enum: queued | in_progress | done | failed)
- `claimed_by` (text, nullable — ripper container hostname)
- `claim_heartbeat_at` (timestamptz, nullable)
- `attempts` (int, default 0)
- `output_path` (text, nullable — `/raw/<job_id>/<file>` once done)
- `size_bytes` (bigint, nullable)
- `sha256` (text, nullable)
- `duration_seconds` (int, nullable — actual, measured post-rip)
- `last_error` (text, nullable)

Indexes:
- `(status, claim_heartbeat_at)` for the stale-claim sweep.
- `(job_id)` for job detail views.

### `rip_presets`
Controls ripper behavior: which tracks to rip, whether to identify, and what output form they take. Built-ins are seeded on first boot and are `is_builtin=true` (locked). Users create editable copies by cloning a built-in in the UI wizard (which pre-fills the form; no parent FK is stored).

- `id` (ULID)
- `name` (text)
- `media_type` (enum: `movie` | `tv` | `music` | `data` | `iso`)
- `is_builtin` (bool — `true` rows are ARM-shipped and not editable through the API)
- `track_selection` (enum: `main_feature` | `all_tracks` | `archive` | `custom`) — `archive` = all tracks + chapters + subtitle tracks + metadata preserved. `custom` relies entirely on `track_filters_json`.
- `identification_mode` (enum: `required` | `skip` | `deferred_placeholder`) — `required` = block ripping until identity is known. `skip` = home-movie style (no metadata lookup; the job is marked identified with a user-supplied or generic title). `deferred_placeholder` = rip immediately on an identify miss; raw output goes to `/raw/<job_id>/` (identity-independent); any queued session applications sit in `session_applications.status = waiting_identify` until the user resolves identity, at which point transcode fans out against the resolved title. No files are ever renamed or moved after identity resolves — see [02-job-lifecycle.md § Unidentified and placeholder rips](02-job-lifecycle.md#unidentified-and-placeholder-rips).
- `output_mode` (enum: `tracks` | `iso` | `data_copy`) — `tracks` = per-title extraction (MakeMKV). `iso` = full-disc ISO image. `data_copy` = `cp -r` of disc contents.
- `track_filters_json` (jsonb, nullable) — declarative rules: min/max duration, "skip Play All heuristic flag," "flag multi-feature-length tracks for user review," etc. Shape evolves as features land; no hard schema.
- `created_by_user_id` (nullable FK — null for built-ins)
- `created_at`, `updated_at`

### `transcode_presets`
Controls encoding: which tool, which preset, which container. Built-ins wrap HandBrake's native preset catalog by name plus a curated set of ARM-specific presets; same `is_builtin` + clone-to-edit pattern.

- `id` (ULID)
- `name` (text)
- `media_type` (enum: `movie` | `tv` | `music` | `data` | `iso`)
- `is_builtin` (bool)
- `tool` (enum: `handbrake` | `abcde` | `none`) — `none` for ISO / data-copy passthrough sessions; no transcode runs.
- `preset_ref` (text, nullable — HandBrake built-in preset name (e.g. `"H.265 MKV 1080p30"`, `"Apple 2160p60 4K HEVC Surround"`) or an abcde config profile key. Null for `tool=none`.)
- `preset_json` (jsonb, nullable — inline custom HandBrake preset when the user's configuration isn't in the built-in catalog)
- `container` (enum: mkv | mp4 | webm | flac | mp3 | ogg | iso | none)
- `hw_preference` (enum, nullable — same semantics as old sessions field: `NULL` = "prefer HW, queue if all busy, CPU only if no GPU is present anywhere"; `cpu_only` forces CPU; `any` = "don't queue for HW, CPU is fine")
- `extra_args` (text, nullable — raw CLI args appended to the tool invocation; escape hatch)
- `created_by_user_id` (nullable FK — null for built-ins)
- `created_at`, `updated_at`

### `sessions`
The user-facing composition: a named bundle of (rip preset, transcode preset, output path convention) that can be applied to rips of matching media type. Sessions are the thing a user picks in the UI; rip presets and transcode presets are the parts a session is built from.

- `id` (ULID)
- `name` (text) — user-facing label. Unique within the user's sessions for the picker UI. Not used in output filenames — the transcode preset name (slugified as `{transcode_slug}`) handles that.
- `media_type` (enum: `movie` | `tv` | `music` | `data` | `iso`) — sessions are media-type-scoped; a session only targets rips of the matching type. UI filters the session picker at apply-time. Must equal `rip_presets.media_type` and (if `transcode_preset_id` is set) `transcode_presets.media_type`.
- `is_builtin` (bool)
- `rip_preset_id` (FK → `rip_presets.id`)
- `transcode_preset_id` (FK → `transcode_presets.id`, **nullable**) — null for ISO / data-copy sessions where no transcode stage runs.
- `output_path_template` (text — tokenized path, **relative to the media-type library root**. Example for `media_type=movie`: `{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}`. See [02-job-lifecycle.md § Output paths and naming](02-job-lifecycle.md#output-paths-and-naming) for defaults and token list.)
- `overrides_json` (jsonb, nullable — per-session tweaks applied on top of the referenced presets, e.g. "use this preset but force CRF 22 instead of 20." Keeps users from having to clone a whole preset for one-field changes.)
- `created_by_user_id` (nullable FK — null for built-ins)
- `created_at`, `updated_at`

**Why the three-table split.** v2 bundled rip strategy + transcode settings + output convention into one "session" concept. v3 decomposes them so they're independently reusable — the same "Plex 1080p H.265" transcode preset applies whether the source was ripped as `main_feature` or `archive`; the same `home_movie` rip preset can be paired with any transcode preset the user likes. Sessions recompose these pieces into a named, picker-friendly bundle.

### `transcode_tasks`
One row per "one raw track → one output file" operation. Fans out from a session.

- `id` (ULID)
- `session_application_id` (FK — see below)
- `source_track_id` (FK → `tracks.id`)
- `status` (enum: queued | in_progress | done | failed)
- `claimed_by` (text, nullable — transcode container hostname)
- `claim_heartbeat_at` (timestamptz, nullable)
- `attempts` (int, default 0)
- `output_path` (text, nullable — resolved at fan-out time from the session's `output_path_template`)
- `progress_pct` (int, default 0)
- `last_error` (text, nullable)

Indexes:
- `(status, claim_heartbeat_at)` for the stale-claim sweep.
- `(session_application_id)` for progress rollup.
- **Partial unique index** on `(output_path) WHERE status IN ('queued', 'in_progress', 'done')`. Prevents two live tasks from claiming the same output path. Failed tasks can share paths — their file is presumed absent. See [02-job-lifecycle.md § Concurrent write safety](02-job-lifecycle.md#concurrent-write-safety) for the full collision model.

### `session_applications`
A user (or auto-transcode) says "apply session S to job J." This is the durable record of that intent. It owns the fan-out of tasks.

- `id` (ULID)
- `session_id` (FK)
- `job_id` (FK)
- `status` (enum: waiting_identify | queued | running | done | done_partial | failed | cancelled) — `waiting_identify` is used when the session is applied (or auto-queued from `drives.default_session_id`) against a job that is still `awaiting_user_id` under a `deferred_placeholder` rip preset. No `transcode_tasks` rows are fanned out until identity resolves; the transition is `waiting_identify → queued` at that point. See [02-job-lifecycle.md § Unidentified and placeholder rips](02-job-lifecycle.md#unidentified-and-placeholder-rips).
- `overrides_json` (jsonb, nullable — per-application tweaks to the session template)
- `overwrite` (bool, default `false`) — set by the collision dialog when the user chooses to replace an existing output file. Transcoder's atomic-rename step overwrites the target instead of failing the uniqueness check.
- `created_by_user_id` (nullable — null if auto-queued from drive default)
- `created_at`, `completed_at`

### `gpus`
Runtime inventory of hardware encoders the Backend detected on startup. The table is **truncated and repopulated on every Backend boot** — it is not user-editable and not persistent across restarts. The Backend container gets full host HW access in compose and probes directly.

- `id` (ULID)
- `vendor` (enum: vaapi | nvenc | qsv)
- `device_path` (text — e.g. `/dev/dri/renderD128` for VAAPI, `nvidia://0` for NVENC)
- `encoder_kinds` (text[] — codecs this device advertises, e.g. `['h264','h265','av1']`)
- `status` (enum: available | busy)
- `claimed_by_task_id` (FK → `transcode_tasks.id`, nullable)
- `last_seen_at`

Transcode task spawn takes a row via `SELECT … FOR UPDATE SKIP LOCKED`, flips `status` to `busy`, and passes the device path to the spawned container (`ARM_GPU_DEVICE` or the NVIDIA equivalent). Release on container exit. If the table is empty (no GPUs on host), tasks fall back to CPU automatically; a single `transcode.hw_unavailable` event is emitted at Backend startup rather than per task.

### `events`
Append-only event log. Every typed event the system emits lands here. The `NotificationDispatcher` (Apprise-backed) and the UI's activity feed both read from this.

- `id` (ULID)
- `event_type` (text — e.g. `rip.completed`)
- `emitted_at` (timestamptz)
- `job_id` (FK, nullable)
- `track_id` (FK, nullable)
- `session_application_id` (FK, nullable)
- `payload_json` (jsonb)

Retention: 90 days by default, trimmed by a Backend background task.

## Entity relationship summary

```
users ──────┐
            │ (created_by, updated_by)
            ▼
         config
         drives ──┐
                  │  (drive_id)
                  ▼
                jobs ──────── tracks (N)
                  │
                  │  (job_id)
                  ▼
         session_applications ──────── transcode_tasks (N)
                  │                           │
                  │  (session_id)             │  (source_track_id)
                  ▼                           │
               sessions                       │
                                              ▼
                                         tracks (same table, reverse FK)

events (sparse FKs to jobs / tracks / session_applications)
```

## Schema definition and migrations

**ORM: SQLModel (Pydantic + SQLAlchemy 2.0).** Tables are defined as SQLModel classes in `packages/arm_common/models/` — one class per entity, doubling as the request/response Pydantic schema where the wire shape matches the row shape. SQLAlchemy 2.0 typed mappings + mypy give static checking on column access; query construction is runtime-introspected (no entgo-style codegen — Python's ecosystem doesn't have an equivalent, and the FastAPI/SQLModel stack is the closest practical match).

**Migrations: Alembic with `--autogenerate`.** Lives at `services/backend/migrations/`. Workflow:

- Edit a SQLModel class.
- `alembic revision --autogenerate -m "…"` diffs models against the live DB and emits a revision file.
- **Review the generated revision before committing.** Autogenerate handles column add/drop/type changes well; it misses constraint renames, server defaults on existing columns, Postgres enum value additions, and partial-index changes — patch those by hand. Treat the generated file as a draft, not the final.
- Hand-edited revisions for data migrations (backfills, enum value renames, etc.).

**Runtime:** Backend runs `alembic upgrade head` on startup before serving requests. No sidecar migration container. No online schema changes planned for v3.0 — downtime during `docker compose up` after a migration is acceptable for a homelab.

**Why this stack.** SQLModel is the FastAPI-native default (same author), so model classes flow into route signatures without a second Pydantic layer. Alembic is the de-facto Python migration tool — v2 already uses it under Flask-Migrate, so the operational playbook (rollback, dry-run, manual revision authoring) carries over. Tortoise+Aerich and Piccolo were considered for a more entgo-shaped single-source-of-truth feel; both have smaller ecosystems and weaker Postgres-specific feature support (partial indexes, JSONB ops, enum management), and the tradeoff didn't justify diverging from the FastAPI default.

## What the data model deliberately does NOT have

- **A queue table.** Queue mechanism is deferred. For now, "queue" is just `tracks WHERE status='queued'` and `transcode_tasks WHERE status='queued'`. This keeps the door open to swap in Redis/RQ/NATS without reshaping the model.
- **Per-user libraries.** One library, one user.
- **Download history / play tracking.** ARM is a rip-and-transcode system, not a media server.
- **Disc rental / sharing.** Out of scope.
