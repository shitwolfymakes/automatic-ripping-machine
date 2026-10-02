---
name: project_dev_host_validation
description: How to validate the stack on this WSL dev host (browser automation path, ISO path without the corpus, Docker network flakes) and where hifi-server keeps its checkout
metadata:
  type: project
---

Learned during the 1 October 2026 full-stack validation run (results in the "ARM v3 full-stack test plan" doc).

- **Browser automation against the dev stack.** The Playwright MCP browser rejects the dev CA on https://localhost:8081, and anything that weakens TLS is off limits. Use the project's own dev server instead: `ARM_DEV_BACKEND=https://localhost:8081 npm run dev -- --port 5173` in services/ui-neu/frontend (vite proxies /api through nginx). Expect the WebSocket to be refused (403, cross-origin) so the live-updates-down banner shows; /help has no docs-data on the dev server (it is baked into the arm-ui image only).
- **ISO path without the Sintel corpus.** The matrix256-corpus image is private on GHCR and the Docker Hub pull was throttled to nothing on this host. A tiny ISO made with PyCdlib in arm/iso-library (ARM_HOST_ISO_LIBRARY_PATH in .env) exercises the whole Rip-from-ISO flow (virtual drive, ripper spawn, job creation, cancel, watchdog retire); it scans to zero titles, which is the case that crashed #101 before 94271ecb.
- **Ripper container logs vanish.** The backend removes an exited ISO ripper immediately; to see why one died, poll `docker ps` every 100 ms and attach `docker logs -f` the moment it appears.
- **Docker builds on this host hit npm network flakes.** npm silently skips optional deps on a fetch error, so the arm-ui image once built without rolldown's native binding and failed at `npm run build`. Fix: `docker compose build --no-cache arm-ui`, then `setup-dev.sh up`.
- **hifi-server checkout** is `~/src/automatic-ripping-machine-v3` (not ~/src/automatic-ripping-machine); its integration/all-prs-3 clone can lag origin. Its MakeMKV key comes from the forum beta scrape (no key in config).

- **Never restart hifi-server's backend while a passthrough is filing.** ISO passthrough runs inside the backend; raw and media are separate mounts of one NFS share, so filing is a full copy (20 GB over Wi-Fi, 15-50 min), not resumable. A restart kills it (Docker often cannot even stop the backend, which is stuck in NFS I/O; compose then leaves a `<hash>_armv3-backend` container that must be removed before `setup-dev.sh up` works) and the task is requeued from zero with attempts+1 (max 3). setup-dev's active-work guard only sees spawned containers, so it does not protect this. Before a rollout, check `session_applications.status` with SQL sent via a file (`psql -f -` over stdin): `$$` inside an ssh single-quoted string expands to a PID and silently empties the query, which is how a rollout once fired mid-copy.

**How to apply:** reach for these before building new tooling; the test plan doc holds the per-drill evidence and the defect list.
