# ARM v3 Architecture

This directory captures the v3 architecture for the Automatic Ripping Machine as of 2026-04-18. v3 is a **ground-up rebuild** — no part of the v2 architecture is carried forward unconditionally.

**Repo isolation.** All v3 code, compose config, and tooling lives under the top-level `v3/` directory. v2 files at the repo root are never modified during v3 development; v3 and v2 coexist in the same repo on the same branch, each ignorable by the other. The only moment existing v2 files change is the one cutover PR when v3 is ready to take over the repo — see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md).

## Quick summary

v3 is a **multi-container, Python-first** system built around a job/session state machine, per-drive ripper containers, and ad-hoc transcode containers. The Backend is the brain; everything else is a worker that talks to the Backend over REST + WebSocket.

| Service | Image | Lifetime | Role |
|---|---|---|---|
| **UI** | `arm-ui` | Long-running | SPA (Vite-built) served by nginx; consumes Backend API + WS |
| **Backend** | `arm-backend` | Long-running | FastAPI: job/session state machine, internet adapters, WS hub, spawns transcoders |
| **Ripper** | `arm-ripper` | Long-running, one per drive | Bound to a single `/dev/sr*`; identifies disc, rips to `/raw`, reports to Backend |
| **Transcode** | `arm-transcode` | Ad-hoc, one per transcode | Spawned by Backend; optional GPU pass-through; reports progress, exits |
| **DB** | `postgres:16` | Long-running | Encrypted-at-rest Postgres; source of truth for all state |

## Documents

0. [Vision, goals, principles](00-vision.md)
1. [System architecture overview](01-architecture.md)
2. [Job lifecycle & crash recovery](02-job-lifecycle.md)
3. [Protocol: REST + WebSocket contract](03-protocol.md)
4. [Data model](04-data-model.md)
5. [Cross-cutting: config, auth, logging, testing](05-cross-cutting.md)
6. [Deployment: compose, volumes, sockets](06-deployment.md)
7. [Open questions & deferred decisions](07-open-questions.md)
8. [v2 isolation & cutover plan](08-v2-isolation-and-cutover.md)

## Non-goals

Explicit non-goals for v3.0 — not features that are not done yet, but features we have actively decided **not** to pursue:

- **No TrueNAS / iX Systems support.** Not a supported target.
- **No v2 → v3 data migration.** v2 stays on its own tag; v3 starts from a clean schema.
- **No multi-tenancy / RBAC.** Target user is a single homelab hobbyist. One admin.
- **No Kubernetes / Helm.** Docker Compose is the only supported deploy surface.
- **No in-backend transcoding.** Transcode always runs in a dedicated ephemeral container.

## Status

This is a **first-draft architecture**, initially drawn up on 2026-04-18 and refined through a follow-up pass that resolved most of the first-draft open questions. A small set of decisions remain deliberately deferred (queue mechanism, frontend framework) — see [07-open-questions.md](07-open-questions.md).

Disc fingerprinting was explored during scoping and spun out to a standalone spec at [../../../disk-fingerprinting-algorithm/](../../../disk-fingerprinting-algorithm/) — it is **not** part of v3.0 scope.
