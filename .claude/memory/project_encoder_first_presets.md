---
name: project_encoder_first_presets
description: Encoder-first transcode presets, per-device GPU probe, and vendor image variants (wolfy #87, migration 0038) - model, upgrade behavior, parked follow-ups
metadata:
  type: project
---

Built 2026-09-26 from a tester report (Ryzen 7700X iGPU on VAAPI plus Arc B580
on QSV): QSV presets landed on the VAAPI card because the GPU claim ignored
vendor, and a codec of "default" behaved like NULL. Draft wolfy **#87**,
stacked on no-transcode mode ([[project_no_transcode_mode]]) and carrying the
transcode trixie bump (#86).

Model:
- A preset names one encoder id from `arm_common.encoders`: `preset`,
  `cpu_*`, `any_*`, `qsv_*`, `nvenc_*`, `vaapi_*`. `codec`/`hw_preference` are
  gone (migration 0038 backfills and drops them).
- A GPU row is eligible only when enabled, probed (`probed_at`), and the codec
  is in `encoder_kinds`. `any_*` picks NVENC, then QSV, then VAAPI; it falls
  back to CPU only when no eligible device exists, and queues while one is busy
  or awaiting its first probe.
- The backend spawns `--probe-device` per GPU: boot pass, `POST /api/gpus/{id}/probe`,
  `POST /api/gpus/probe`, and on enabling a never-probed row.
- `any_*` on AMD runs the ffmpeg VAAPI engine and ignores the HandBrake preset
  (owner accepted; the picker notes it).
- QSV/VAAPI need the `-intel`/`-amd` image variants, pulled on demand
  (overrides `ARM_TRANSCODE_IMAGE_QSV/_VAAPI/_NVENC`). A remote transcode host
  with an image older than `--probe-device` shows a stale-image probe error
  and gets no GPU work until the image is rebuilt.

**Why:** the vendor-blind claim and NULL codec semantics were the root causes;
verifying encoders inside the actual transcode image per device is the only
truthful source.

**How to apply / open items:**
- Parked minors: an open preset form ignores `gpu.probed`; a joined encoders
  store refresh can return pre-probe data; `/api/encoders` greys pinned
  encoders during the probe window although apply accepts them;
  `set_active_dispatcher(None)` is not in a `finally`; probe container removal
  stops at the first failure.
- Found on the way, out of scope: cancelling an in-flight encode can be
  swallowed (`CancelRequested` in consume_progress); a PATCH with an explicit null
  tool/container writes NULL; install.sh has no variant awareness.
- Deferred: AMF (`vce_*`) on real AMD hardware; the backend + ripper trixie bump.
- Migration 0038 downgrade does NOT restore `gpus.encoder_kinds`.
