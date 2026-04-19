# 07 — Open Questions & Deferred Decisions

Decisions we have explicitly chosen not to make in the first-draft architecture, in the order they need to be resolved.

---

## OQ-1: Queue mechanism for async work

**Status:** deferred, not a v3.0 blocker.

**Context.** The data model has `tracks.status` and `transcode_tasks.status`. Worker claim happens by `SELECT … FOR UPDATE SKIP LOCKED`. This is effectively DB-as-queue, and it's what v3.0 will ship with.

The deferred question is whether to upgrade this to Redis+RQ, NATS, or keep DB-as-queue indefinitely.

**Why deferred.** DB-as-queue is adequate for the expected scale (1-4 drives, 1-4 concurrent transcodes). The moment we start needing delayed jobs, fan-out topics, or back-pressure, we re-evaluate. The state machine is designed so the queue is a replaceable component — services call a `JobQueue` interface; the Postgres implementation lives behind it.

**Resolve by:** when a concrete pain point emerges (multi-minute claim latency, retry explosion, etc.), not before.

---

## OQ-2: Frontend framework — Vue vs React

**Status:** deferred to the UI track.

**Context.** Both are reasonable for a small SPA; the project's contributor pool is the deciding factor. No strong architectural consequences either way — both work fine with Vite, OpenAPI codegen, and WS subscriptions.

**Considerations:**
- **Vue.** Smaller bundle, less JS ceremony, gentler learning curve. Composition API fits the "reactive stores" pattern the UI will need for job lists.
- **React.** Larger contributor pool in the Python/homelab crossover. More libraries for niche components.

**Resolve by:** when the first UI contributor commits to leading that track.

---

## Process for resolving open questions

1. When an OQ is ready to resolve, the relevant design decision is folded directly into the main architecture docs in a PR that also deletes the OQ entry here. No `resolutions/` folder — git history carries the context.
2. OQs don't block development — services are designed around the plug-in points.
