# v3 backlog — open items from live hifi testing (2026-06-24)

Captured from a session deploying v3 to hifi-server and exercising the full
rip→transcode pipeline. Companion issue write-ups live alongside this file in
`docs/issues/`. Status legend: 🔴 open · 🟡 worked-around · ✅ done.

---

## 1. Rip progress is per-track on the wire, should be per-job 🔴
The dashboard bar already *displays* per-job (keyed by `job_id`), but progress is
published per-track: the WS payload carries a `track_id`, and the DVD `mkv all`
path attributes disc-overall PRGV to the "first eligible track" as a placeholder
(`services/ripper/arm_ripper/rip/dispatcher.py:205-219`). The ui-neu store resets
its ETA baseline on `track_id` change (`lib/stores/rips.svelte.ts:89-92`), so any
genuinely per-track stream (CD abcde via `_on_title_progress`,
`dispatcher.py:189-195`) makes the single bar jump backward 0→100% per track and
reset ETA.
**Goal:** job-scoped progress end-to-end (one continuous 0→100% per disc).
**Touches:** `dispatcher.py`, `job_controller.py:607-617` (WS publish),
`lib/stores/rips.svelte.ts`. Add multi-track monotonic-progress tests.

## 2. ARM_GPUS over-claims encoder caps → transcode rc=3, no CPU fallback 🟡
On hifi the N97 (Alder Lake-N) QSV advertised `encoder_kinds={h264,h265}` in
`ARM_GPUS`, but HandBrake reports `H.265 encoder: no` (h265 is decode-only on this
silicon). h265 presets (`hw_preference=any`) routed to QSV and failed instantly:
`hb_qsv_apply_encoder_options invalid pointer` / `Error setting child device
handle: -17` / `Encode failed (error 3)`, rc=3.
**Worked around** on the server: set `ARM_GPUS` `encoder_kinds=["h264"]`, recreate
backend → h265 falls back to CPU x265 (verified: software encode, 366% CPU, no
GPU device mounted).
**Real fix (wolfy):** see `docs/issues/dispatcher-transcoder-puid.md` is a
*different* bug; this one needs: validate `ARM_GPUS` against actual HandBrake
encoder caps at install (derive encoder_kinds), AND/OR auto-retry-on-CPU when a HW
encoder init fails instead of failing the task. Also: no built-in h264 GPU preset
exists, so an h264-only GPU has no built-in GPU target.

## 3. 'Done' status rendered gray instead of green ✅ FIXED
`statusColor()`/`statusAccentVar()` in `lib/utils/format.ts` were missing the
`done` case (TaskStatus terminal success) → fell through to gray. Now mapped to
status-success/green. Committed `d530afde` (Tier-12), deployed to hifi.

## 4. 'ripped' jobs stay stuck in FINISHING section 🔴
The dashboard groups by `job.status`; `finishingJobs` filters status in
(identified, ripped, ripped_partial) (`routes/+page.svelte`). A `ripped` job is
terminal at the job level — transcode progress lives on `transcode_tasks`, not the
job — so a ripped job never leaves FINISHING on its own, even while actively
transcoding.
**Decide:** a ripped+transcoding job should move to a Transcoding view (driven by
session_application/transcode_task state); an un-actioned ripped job needs an exit
(auto-drop or dismiss, like the sticky-review pattern). Relates to #1.

## 5. Brainstorm: polish the rip→transcode→completed experience 🔴
Hold a brainstorming session (use the brainstorming skill) on the end-to-end flow.
Pain points seeded from live testing:
- GPU/encoder: ARM_GPUS trust + no CPU fallback (#2); no h264 GPU preset; no UI
  surface for "running on GPU or CPU?" (had to inspect /dev/dri + CPU%).
- Pipeline UX: rip→transcode decoupling — ripped jobs dead-end unless a session is
  applied (no default session + auto_transcode off); unidentified discs block on
  the `{year}` template token (`docs/issues/unidentified-rip-blocks-transcode.md`);
  dispatcher PUID/PGID bug (`docs/issues/dispatcher-transcoder-puid.md`).
- Observability: transcode % only on /transcoder page, not the dashboard job card;
  ETA/encoder/fps/stage not surfaced cohesively.

## Related: performance/hardware stats (B31)
Per-container CPU/GPU/throughput stats are a *deliberately deferred* v3 initiative,
fully scoped as backlog B31 (`../arm-ai/arm-v3/docs/port-backlog.md`) +
`followups-for-wolfy.md`. v3's backend has no hardware probe by design; live GPU
util (B31b) needs a transcoder-side probe via the heartbeat channel. See in-repo
memory `project_perf_stats_research.md`.

## Companion issue write-ups (ready to hand to wolfy)
- `docs/issues/unidentified-rip-blocks-transcode.md` — `{year}` template gate
- `docs/issues/dispatcher-transcoder-puid.md` — dispatcher drops PUID/PGID
