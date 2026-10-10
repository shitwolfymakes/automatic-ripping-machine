---
name: project_no_transcode_mode
description: No-transcode mode (capability + toggle + in-process passthrough) shipped as wolfy PR #85; known follow-ups
metadata:
  type: project
---

Shipped 2026-09-25 as wolfy **#85** (`feat/no-transcode-mode`, draft, stacked on
`feat/gpu-inventory-alignment` at stack end; migration **0037**). Spec/plan in
`../arm-ai/arm-v3/docs/superpowers/{specs,plans}/2026-09-25-no-transcode-mode*`.

Design (owner-approved, do not relitigate):
- Two layers: env `ARM_TRANSCODE_CAPABLE` (deployment fact; `setup-dev.sh
  --ripper-only` writes false PER RUN, not sticky; a set
  `ARM_TRANSCODE_DOCKER_HOST` implies capable) + DB `config.transcode_enabled`
  (Settings toggle; enable-while-incapable = 422; NULL = enabled).
- Disabled gates ENCODE only. Passthrough (no preset or `TranscodeTool.NONE`)
  ALWAYS runs in-process in the backend dispatcher (`passthrough_executor.py`),
  never a container - the `transcode_none` container path is retired. Queued
  encode tasks are held, not cancelled; re-enable resumes + re-drains parked apps.
- In-process finalize writes `/media` as the BACKEND's uid (marvin/TrueNAS ACL
  rule applies to the backend PUID now); `ARM_TRANSCODE_PUID` = encode
  containers + best-effort chown after in-process moves.

Hard-won dispatcher invariants (4 fix rounds, opus reviews):
- Claim is COMMITTED before the move (no FOR UPDATE locks across cross-mount
  copies); every queued row reloaded per iteration with `populate_existing`
  (identity-map staleness after rollback = MissingGreenlet; FakeSession's no-op
  rollback CANNOT catch this class - real-session e2e tests in
  `tests/e2e/test_dispatcher_real_session.py` pin it).
- Never read ORM attributes in except blocks before `db.rollback()`.
- In-process claim heartbeat is set once, never refreshed - safe ONLY while
  sweep_stale_claims shares the dispatcher coroutine (documented at
  IN_PROCESS_CLAIMANT).

Known follow-ups (ledgered, PR body names the first):
1. Re-drain failure path 500s the config PATCH (`job.id` read after rollback in
   `drain_parked_applications_after_rip`; same pattern pre-exists in `after_rip`).
2. EXDEV passthrough copy not atomic (container parity; `transcode_none`
   docstring still overclaims).
3. Serial passthrough copies stall the tick for the batch; cancel of an
   in-process passthrough doesn't stop the copy.
4. install.sh compose heredoc lacks `ARM_TRANSCODE_CAPABLE` passthrough
   (carryover doc; [[install-sh-is-legacy]]).
5. Stale-config merge bug pre-exists in Metadata/Ripping settings forms (fixed
   for Transcoding only; generic fix would round-trip secrets).

Relates to [[project_transcode_offload_architecture]] (tier25 remote offload
still works on ripper-only boxes via ARM_TRANSCODE_DOCKER_HOST).
