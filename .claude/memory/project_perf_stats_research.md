---
name: Performance/hardware stats in v3 — existing research (B31)
description: v3 deliberately has NO hardware probe; reviving live perf stats (disk/CPU/GPU) is a scoped backlog item B31 with detailed design already written
metadata:
  type: project
---

**Yes, there is substantial prior research** for adding performance/hardware stats
to v3 — and the current state is a *deliberate design decision*, not an oversight.

## v3 has NO hardware/perf probe — by design

- The legacy neu BFF probed hardware (CPU%, RAM, GPU util/VRAM/clocks, storage) and
  rendered it in SidebarStats + BottomStatsBar.
- **v3's backend deliberately does NOT probe hardware** (`gpu_probe.py:3`,
  `main.py`: "the backend no longer probes hardware. GPU detection happens
  host-side"). GPU detection is install-time only — the static `ARM_GPUS` env.
- During the neu→v3 UI port, the hardware-stats UI rendered permanently blank
  (hardcoded null) and was **deleted entirely** (SidebarStats/BottomStatsBar +
  the `SystemStats`/`GpuInfo`/`HardwareInfo` types). Design:
  `../arm-ai/arm-v3/docs/superpowers/specs/2026-06-18-ui-neu-remove-hardware-stats-design.md`.
- v3 keeps only **aggregate counters**: `/api/system/stats` (uptime,
  jobs_by_status, drives_online, events_unsent) and `/api/transcodes/stats`
  (queue counts, gpus_available/total). No live hardware/throughput telemetry.

## The scoped backlog item to revive it: B31

Full design in `../arm-ai/arm-v3/docs/port-backlog.md` (B31) +
`../arm-ai/arm-v3/docs/followups-for-wolfy.md` ("System resource feed B31a").
New endpoint `GET /api/system/resources` (JWT, read-only), split by where the
hardware truth lives in v3's topology:

- **B31a — disk + CPU/mem (the shippable core, S–M).**
  - CPU/mem: `psutil` (`cpu_percent(interval=None)` non-blocking /proc read +
    `virtual_memory()`); new backend dep in `services/backend/pyproject.toml`. Settled.
  - Disk per root via `os.statvfs` **in a subprocess with a timeout, served from a
    TTL cache** — because statvfs HANGS on NFS D-state mounts and would wedge the
    async loop. Reuse `system.py::_roots()` for the root map.
  - v3 background-loop precedent: `arm_backend/log_tailer.py` (run_in_executor +
    lifespan task + stop()).
  - Open decision for wolfy: background-loop+to_thread vs neu's subprocess — hinges
    on how often real deploys put media roots on NFS/SMB.

- **B31b — GPU LIVE util (deferred; relevant to ripper/transcoder containers).**
  - The backend can't measure GPU util (no hardware probe by design); only the
    **ephemeral transcoder** container has the render node + vendor tooling.
  - Live GPU util needs a **transcoder-side probe** — a real design call:
    persistent sidecar vs. heartbeat-only-while-running. Until built,
    `resources.gpu[]` returns inventory + status from the `gpus` table, truthfully
    labelled as NOT live util (don't fake a number the backend can't measure).

## Implication for ripper/transcoder per-container stats

Per-container CPU/GPU/throughput stats (the thing we wished for during the N97
QSV-vs-CPU debugging — see [[hifi-v3-deploy]] and task #10 brainstorm) map to
**B31b**: it requires a transcoder-side (and by extension ripper-side) probe that
reports util via the existing heartbeat channel, since the backend itself is
hardware-blind. The transcoder already heartbeats (`/api/transcoder/.../heartbeat`)
and the ripper heartbeats too — those are the natural carriers for per-container
util/fps/throughput without adding a new probe path.

**Reference code (neu, read-only port source):**
`arm/services/disk_usage_cache.py` (subprocess+cache + NFS D-state rationale),
`arm/models/system_info.py` (psutil cpu/mem), `arm/api/v1/system.py::/system/stats`.
