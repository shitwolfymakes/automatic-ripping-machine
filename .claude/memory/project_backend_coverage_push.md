---
name: project_backend_coverage_push
description: Status of the backend 100%-coverage push — what's done, what modules still have gaps, and the pattern to finish them
metadata:
  type: project
---

Ongoing effort (started 2026-05-16) to drive `v3/services/backend` toward
100% coverage. Branch `wolfy/v3-improvments`. Measured via `uv run coverage
run -m pytest` (config in `v3/pyproject.toml [tool.coverage]`, branch=true).
See [[project_backend_test_harness]] for the two test tiers and gotchas.

**Progress: 70% → 94%** (branch coverage), 535 tests passing. Committed in
small per-module commits (`test(v3-backend): ...`).

**At 100%:** every router (jobs, ripper, transcodes, transcode_presets,
rip_presets, drives, config, auth), all metadata clients + dispatcher,
auth.py, ws/router.py, ws/authz.py, ws/hub.py, config.py,
notification_format.py, track_selection.py. routers/transcoder.py and
routers/sessions.py are at 97–99% (a few partial branches only).

**Still has gaps (largest first):** auto_session.py (~29), main.py (~25,
mostly the lifespan dispatcher/docker branches + the `main()` uvicorn
entrypoint — pragma candidates), log_tailer.py (~23), transcode_dispatcher.py
(~21), transcode_apply.py (~16), db.py (~10 — the SSL-context branches and
`get_session` are pragma/real-DB-only), notification_dispatcher.py (~9),
seeders.py (~8 — idempotent-rerun + FIRST_BOOT_LOG OSError), logs.py (~7 —
zip/stream file paths), gpu_probe.py (~7 — renderD*/nvidia-smi parsing),
plus the transcoder/sessions partial branches.

**Pattern that works:** fast fake-session (`tests/_fakes.FakeSession`) +
`TestClient` per module for branch coverage; real-DB e2e (`tests/e2e/`) for
wiring; respx for HTTP clients; `tmp_path` for filesystem modules
(log_tailer/logs/gpu_probe); monkeypatch module globals for dispatchers.
Genuinely-unreachable lines get `# pragma: no cover` (short inline — ruff
reformats long ones and misplaces the pragma) with a justification comment
on the line above; exhaustive-enum/union fallthroughs get `# pragma: no
branch`.

CI measures coverage but does **not** gate yet (user's call — no
`fail_under`). Add the ratchet once near 100%.
