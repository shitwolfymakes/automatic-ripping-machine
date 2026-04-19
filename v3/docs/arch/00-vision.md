# 00 — Vision, Goals, and Principles

## Who v3 is for

**Single-admin homelab users.** One person running ARM for their own household. Not a shared service, not a multi-tenant platform, not a commercial product.

The user base in practice includes many **data-hoarders** — people who rip to preserve the raw bits, not just to feed a streaming app. This shapes retention defaults (keep raw forever) and session semantics (re-transcode from raw is a first-class operation).

## Problems v3 must solve

Two pain points drove the decision to rebuild rather than incrementally refactor v2:

1. **Clean service boundaries, especially for resource isolation.** In v2, running multiple rips concurrently causes compute contention inside a single container. Rippers, UI, and transcoding all share the same process tree, so heavy work in one area degrades every other area. v3 must separate these so that N concurrent rips and a transcode cannot starve the UI.

2. **Batch-rip resumability.** A user who queues five discs and loses power mid-rip on #3 has, today, no way to recover. The system treats each rip as atomic and non-resumable. v3 must checkpoint finely enough that a power event does not discard completed work, and that partially-completed work is re-queued automatically on restart.

A third, adjacent, pain point surfaced during scoping: users want **Sessions** — the ability to rip once and transcode many times with different presets. v2 conflates rip and transcode into one irreversible pipeline. v3 separates them.

## Design principles

### 1. Bits first, metadata second, transcode third

The three stages are decoupled. A rip succeeds the moment the bits are safely on disk and recorded in the DB. Metadata enrichment and transcoding are independent downstream stages that can fail, retry, or be re-run without touching the raw.

### 2. One service, one responsibility

Every container has a single reason to exist:

- The **Ripper** exists to turn a disc into bytes on disk.
- The **Backend** exists to own state and speak to the internet.
- The **Transcode container** exists to turn one raw into one output.
- The **UI** exists to render state and take commands.

No service does "a little bit of the other guy's job."

### 3. Backend is the single internet boundary

The Ripper and Transcode containers **never talk to the internet**. All external calls (TMDB/OMDB/MusicBrainz/Apprise/webhooks) originate from the Backend. This means workers are simpler to run (no API keys, no outbound firewall holes), and external credentials live in exactly one place.

### 4. Postgres is the source of truth; stdout is the source of logs

Durable state lives in Postgres. At-rest encryption is available but user-owned (LUKS or ZFS) — ARM does not hold any encryption keys, because losing an ARM-owned key would mean losing user data, which is a red line. Logs are structured JSON emitted to stdout and appended to a shared volume. We do not invent a third persistence mechanism for state, and we do not hide debug data behind a query language.

### 5. Crash-safe by default

Every long-running operation is checkpoint-able. A worker crash must not discard completed sub-work. A stale "in-progress" row with no live worker is the signal for "re-queue me."

### 6. No sacred cows

This is a greenfield rebuild. Any assumption inherited from v2 is open for review. When in doubt, re-decide from first principles rather than preserve an old shape.

## Success criteria for v3.0

v3.0 is ready when:

- Five discs queued across two drives complete without manual intervention, including a simulated power-cut mid-batch that resumes cleanly.
- A ripped disc can have a new transcode session queued from the UI months later without re-ripping.
- A single PR can change a protocol payload and its two endpoints (ripper side + backend side) atomically.
- A bug-reporter can download one log file scoped to one job_id and attach it to a GitHub issue.
- Fresh install on a new host lands at the login screen in under 5 minutes.
