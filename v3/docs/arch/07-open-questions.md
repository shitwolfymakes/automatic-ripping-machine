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

## OQ-3: Base image and PID-1 strategy for v3 service images

**Status:** deferred to the first service-Dockerfile PR.

**Context.** v2 images are built on `phusion/baseimage` (via the `arm-dependencies` submodule for the ripper). phusion was picked in April 2022 (commit `9933545` in `arm-dependencies`) to let v2 run **udev inside the container** so the host needed zero optical-drive setup — users just mapped `/dev/sr*` in compose and the in-container `udevd` fired [51-docker-arm.rules](../../../setup/51-docker-arm.rules) on each disc change, which in turn invoked `/sbin/setuser arm` to spawn the per-disc ripper. That design needs a PID 1 that can supervise a long-running `udevd` service, long-running UI, and whatever else in the same container — phusion's `/sbin/my_init` + `/etc/service/` runit layer was the off-the-shelf answer. Minimizing host deployment was the goal; multi-service supervision was the mechanism that paid for it.

v3 abandons the premise. The ripper is one container per drive, and disc detection is a 2s `ioctl(CDROM_DRIVE_STATUS)` poll on the passed-through device — **no udev rules on host or in container** (see [06-deployment.md § Why one ripper service per drive](06-deployment.md#why-one-ripper-service-per-drive) and [01-architecture.md § Ripper](01-architecture.md#ripper)). Each service image runs a single long-running (or single-shot) process. The supervised-services shape phusion was chosen for — udev + UI + ripper dispatch coexisting under one PID — doesn't exist in v3 at all.

**What v2 paid for phusion, that v3 should not inherit:**

- **UID unsettable at runtime.** Upstream phusion forbids the `usermod`/`groupmod` dance on the built-in user, which forced ARM's bespoke PUID remap logic and leaked into user-visible bugs (`#1180`, `#1395`, and PR `#1742`'s rewrite on Debian Trixie to survive `--security-opt no-new-privileges=true`).
- **`my_init` noise.** Every recent bug report carries `/etc/my_init.d/start_udev.sh: can't access tty; job control turned off` (`#1096`, `#1180`, `#1345`, `#1384`, `#1552`, `#1578`) — not a root cause, but consistent friction.
- **Image bloat.** ~1 GB phusion-based UI image → ~160 MB on `python:3.12-alpine` in the draft PR `#1604`. For a UI container that only runs nginx + a built SPA, the delta is embarrassing.
- **Two-repo version bumps.** The `arm-dependencies` submodule on top of phusion means every base upgrade is two PRs (see dependabot bumps `#1216`, `#1439`, `#1491`, `#1519`, `#1560`, `#1588`, `#1685`; also the whiplash jammy ↔ noble flip in the `arm-dependencies` log). The aborted `no-sub-modules` branch was an explicit attempt to escape this coupling.
- **Timezone / minimal-image friction** (`#1379`): phusion's stripped `tzdata` state caused silent misbehavior until an explicit apt step was added back.

**Candidates to weigh when the first Dockerfile lands:**

- **`debian:stable-slim` + `tini`.** Minimum that does the job. `tini` is Docker's built-in `--init` in library form; enough for zombie-reaping short-lived subprocesses (`makemkvcon`, `HandBrakeCLI`). No multi-service init layer. This is the default bias.
- **`python:3.12-slim`** for Python-heavy services (Backend, Ripper) to avoid reinstalling CPython on top of `debian-slim`. Same PID-1 story, one fewer apt step.
- **`nginx:alpine`** (or distroless nginx) for the UI, which only serves a built SPA — nothing Python-shaped runs in that container at all.
- **`lscr.io/linuxserver/*` bases** — brings a mature PUID/PGID entrypoint for free, at the cost of pulling in their whole s6-overlay worldview. Worth benchmarking against a hand-rolled `gosu`-based entrypoint on `debian-slim`; probably not worth the foreign abstraction if our entrypoint is ~20 lines.
- **`phusion/baseimage` (status quo).** Not ruled out, but needs a concrete reason to be picked — the multi-process justification is gone.

**Resolve by:** when the first real service Dockerfile is written. The choice is per-image (the UI can be nginx-alpine while the Ripper is debian-slim), so this OQ closes out as services land, not in a single pronouncement.

---

## Process for resolving open questions

1. When an OQ is ready to resolve, the relevant design decision is folded directly into the main architecture docs in a PR that also deletes the OQ entry here. No `resolutions/` folder — git history carries the context.
2. OQs don't block development — services are designed around the plug-in points.
