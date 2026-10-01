---
name: project_automation_gap_register
description: The live gap-analysis is the ARM Automation Gap Register (artifact + docs/plans/AUTOMATION_GAP_ANALYSIS.md), not the June port-backlog
metadata:
  type: project
---

As of 2026-09-22 the current gap-analysis workstream is the **ARM Automation
Gap Register** - an audit of everything blocking fully unattended
rip-to-transcode. G-01..G-26 gaps + R-1..R-6 refactors, six sequenced phases.

- Artifact: https://claude.ai/code/artifact/d2b0be69-6991-48de-9bf6-998f83aa5df1
- Repo copy: `docs/plans/AUTOMATION_GAP_ANALYSIS.md` (commit 9ca4c88c, on the
  wolfy stack branches - NOT on the stale local integration/all-prs checkout)
- Evidence base: integration/all-prs @ 65a39959 + live hifi-server 2026-09-12.

Status (verified against wolfy remote 2026-09-22):
- Phase 1 DONE on the stack (marked in the doc 2026-09-13): G-05 parked
  session survives rip (35ed68d8), R-6, R-2, G-01 rip preset honoured,
  G-06+G-07 (d38e7479), G-09 ripped_awaiting_identify assigned.
- Review pass 2026-09-22 pushed (ba35364e on wolfy/integration/all-prs + artifact v4): G-19 verified done, G-26 narrowed, G-27 SSH-transport wedge / G-28 WS origins / G-29 silent notification failures added.
- Phase 2 CODE-COMPLETE 2026-09-22 at ecfaaa8d on feat/job-identity-columns
  (typed ResolveRequest music/external_ids + extra=forbid; pending mirror
  removed + 0032 scrub; JobView.metadata_json typed as JobMetadata; ui-neu
  fallbacks deleted; final review + fix wave clean). Local stack gate PASSED
  (real-row lift 0030-0032, 9/9 rows validate, typed API live on :8082).
  Quark gate PASSED 2026-09-23 (DB-copy variant, real rows, zero disruption). HELD: push to wolfy (user decision pending). Phase 3 COMPLETE 2026-09-23 at 76e6b519 on feat/session-routing (stacked on
  phase 2): G-27 SSH recovery, G-02 routing table + editor, G-04 compatibility
  guard, G-08 job-scoped eviction, G-17 music routing with compatibility-gated
  drive override. Final review + fix wave clean (backend 1905, ui-neu 1327).
  SHIPPED as stacked squashed PRs 2026-09-24: wolfy #75
  (feat/phase2-job-metadata -> main, phases 1-2 squashed, reconciled with
  current main) and #76 (feat/phase3-session-routing -> #75's branch,
  phase 3 squashed; retarget to main when #75 merges). Unsquashed stack
  branches superseded. RESTACK DONE 2026-09-24: drive-lifecycle chain #61-#66 refreshed onto
  current main and pushed (fast-forward, no force): #61 base refresh
  (entrypoint union: optical nodes + render-gid self-derive), #62 carries
  the migration renumber 0029_drive_lifecycle -> 0030_drive_lifecycle
  (down 0029_thediscdb), chain tip green (backend 2116, ui-neu 1465,
  check clean; dead restartArm import dropped — main descoped restarts,
  B27). #73 verified clean vs main, untouched. CONSEQUENCE: #75/#76 must
  renumber their migrations 0030-0034 -> 0031-0035 once the lifecycle
  chain merges (controller owns it). CI verified 2026-09-24: ALL NINE open PRs green 15/15 (61-66, 73, 74, 75, 76) after a fix round (entrypoint SOURCE_ONLY seam reorder, ruff format on merged main.py, api.gen.ts docstring regen, F811 test dedup on 75). Queue is fully green for wolfy. STACK LINEARIZED 2026-09-24 (user directive): #75 rebased onto
  feat/drive-lifecycle-6 (migrations 0031-0033 off 0030_drive_lifecycle),
  #76 follows (0034-0035), #74 branch now contains the full stack with
  stack-added components converted to its styling system (style lint 0
  violations; FE 1549, BE 2277 tests green). The renumber-on-merge trigger
  is GONE - chain 0029_thediscdb..0035 coherent in every PR tree. #74's
  PR base is stack-managed by GitHub (manual retarget refused; rolls
  forward as predecessors merge). Merge order: 61,62,64,65,66,(73),75,76,74.
  UI-pass backfills DONE in #74's conversion commit except: G-28 origin
  fix + live-updates-down indicator (separate small PR, still queued).
  FRESH REVIEW 2026-09-24 on #75 (high effort, post-linearization): 10
  findings; 9 fixed in a review wave (worst: pending_session_id assigned
  after review-gate persist; resolve rollback hazard; partial-placeholder
  transcode leak; double-apply; explicit-null-clears via model_fields_set;
  new ApplySkippedReason "no_outputs"), 1 parked (strict JobView row
  validation 500s the listing - documented follow-up). Wave re-reviewed
  clean and propagated through #76 and #74 (2214/2287 backend, 1484/1549
  FE, style lint clean). #75 body's alembic fixup note corrected to
  0030_drive_lifecycle. #76 fresh review DONE 2026-09-25: 10 findings, all
  10 fixed in a wave (worst: 0035 seed-marker bricked G-17 seeding for
  upgrading installs - now conditional on routes existing; blocking SSH
  rebuild moved off the event loop via to_thread; EOFError added to
  transport detection; route upsert uses media compatibility; other-routes
  UI list; unowned-task collisions cross-job; full collision reporting;
  outcome-carried 422 detail; corrected help copy; paramiko declared).
  Re-reviewed clean, propagated to #74 (other-routes section converted to
  block vocabulary, style lint 0). All of 74/75/76 green 15/15; branch
  tips stable. #73 SLOTTED INTO STACK END 2026-09-24 (user directive):
  feat/notifications-bash-channel merged with feat/phase3-session-routing
  (one conflict, main.py). CRITICAL CORRECTION: the "rerere poison" was
  NEVER poison. `except TimeoutError, asyncio.CancelledError:` is VALID
  Python 3.14 (PEP 758, unparenthesized except tuples) and is the repo's
  ruff-format canonical form - wolfy/main itself carries it. Every earlier
  "sed fix" to parenthesized form was the actual drift and caused the
  ruff-format CI failures. Root cause of the misdiagnosis: parse checks
  ran on system python3 (3.12), which rejects PEP 758; always parse-check
  with `uv run python` (3.14.4). rerere's resolutions were correct all
  along. Canonical form restored on both branches (41e1ffbe on 73,
  047adbd8 merge on 74); CI-pinned ruff 0.15.11 format+check clean.
  #73 base -> feat/phase3-session-routing.
  73 merged into chore/ui-neu-css-cleanup (only main.py changed, 74's
  converted components all won), pushed d71b31c9 then 047adbd8. Validation on both trees:
  BE 2302 green, FE 1553 green, svelte-check 0/0, style lint 0 violations
  (@types/node false alarm = stale node_modules from 73's branch). #74 base
  retarget REFUSED - user rebuilt the 8-PR stack main->61->62->64->65->66->
  75->76->74 mid-task; user then inserted #73 via the stack UI. STACK
  COMPLETE 2026-09-24: 9-entry GitHub stack main->61->62->64->65->66->
  75->76->73->74 verified via GraphQL (#74 base rolled onto
  feat/notifications-bash-channel), ALL NINE PRs green 15/15. slot73
  worktree + local branches cleaned up. Queue is wolfy's to merge in
  stack order. G-28 SHIPPED 2026-09-24 as wolfy #81
  (feat/ws-origins-live-status, stacked on #74 at stack end): same-origin
  WS default (Origin vs Host/X-Forwarded-Host, forwarded by ui-neu nginx +
  vite dev proxy; ARM_ALLOWED_ORIGINS now additive-only, empty default),
  wsStatus store + LiveUpdatesBanner (offline after 2 failed attempts),
  wiki/arch docs updated, install.sh untouched (note filed in the
  installer-rewrite carryover doc). BE 2312 / FE 1559 green, style lint 0.
  MATRIX256 SHIPPED 2026-09-25 as wolfy #82 (feat/matrix256-fingerprint,
  base main, independent of the stack): scan computes matrix256v1 via a
  pycdlib enumeration (UDF>RR>Joliet>ISO9660 view order per
  IMPLEMENTERS.md) + sparse-file skeleton materialization feeding the
  reference PyPI package `matrix256` 1.0.3 (arm_ripper runtime dep) -
  REWORKED 2026-09-25 per user directive ("prefer using the python
  library over creating the code here"): the local serializer was
  deleted; the library computes every digest; skeleton fidelity is
  test-proven against a real tree. Storage/dedupe/UI pick it up via the
  existing algo-agnostic plumbing, zero backend/UI code change (UI row
  test extended). NEW INTEGRATION BRANCH 2026-09-25: integration/all-prs-2
  on wolfy + origin (08422964: feat/ws-origins-live-status f76165f2 = the
  full 10-PR stack incl. #81, merged clean with wolfy/feat/
  matrix256-fingerprint). Validated: BE 2324, FE 1559, svelte-check 0/0,
  style lint 0, pinned ruff clean, uv.lock consistent. Supersedes the
  stale integration/all-prs (local checkout still parked there); deploy
  target for quark/hifi-server. Register work COMPLETE - no queued gap
  PRs remain; artifact + repo copy
  of the register still show G-28 open (update on next register pass). Backfilling UI
  workarounds (Glyph/CloseButton adoption in SessionRoutesCard, routing
  card refresh on session delete, load-error auto-dismiss, cross-job
  collision copy polish, G-28 WS origin fix + live-updates-down indicator). Follow-ups queued in
  the SDD ledgers: systemic test-isolation flakes (4 distinct one-off sightings),
  per-row jobs-list degradation, session-routes IntegrityError 409, paramiko
  keepalives, SessionRoutesCard refresh on same-tab session delete. Gate branch
  gate/main-plus-phase2 in worktree .claude/worktrees/phase2-lockdown/.gate-merge;
  SDD ledger at .superpowers/sdd/2026-09-22-phase2-lockdown/progress.md.
  Deployed-DB surgical path (old-integration chains): UPDATE alembic_version
  to 0029_thediscdb, upgrade to 0032, stamp past applied drive-lifecycle DDL.
- NEXT: phase-2 lockdown plan at `../arm-ai/arm-v3/docs/superpowers/plans/2026-09-22-phase2-lockdown.md` (stack-validation gate on quark first, then typed resolve, mirror removal + 0032, wire typing).
- Phases 3-6 (routing table, UHD/disc awareness, multi-title/TV, ops
  retention) not started. No PRs opened for the stack yet (queue behind
  drive-lifecycle #61-66, #73, #74).

The June `../arm-ai/arm-v3/docs/port-backlog.md` (B-items) is the OLDER
neu-parity queue; its status board is stale (last updated 2026-06-14 - B31,
B4b, B9, B13, B18, B22, B23 shipped unmarked). Superseded for automation
work by the register; still the reference for remaining neu-parity items
(B1/B2 eject-scan, B15, B16/B17 full import, B20, B27).

TESTER REPORT 2026-09-25 (Ryzen 7700X iGPU vaapi + Arc B580 qsv) added
G-30/G-31 to the register (artifact v5):
- G-30 (major, CONFIRMED in code): _claim_gpu_for_task matches by codec
  only, vendor-blind - a qsv job can claim the vaapi device, transcoder
  bridges vaapi->vce_* and fails. Fix direction: vendor pin on presets
  (extend hw_preference or preset.gpu_vendor) honored in the claim matrix.
- SHIPPED 2026-09-25 as wolfy #84 (feat/gpu-inventory-alignment, stacked
  on #83; merged to integration/all-prs-2 e8dcda76): gpus table now
  DB-AUTHORITATIVE (ARM_GPUS seeds only an empty table; gpus.enabled
  switch, migration 0036; /api/gpus CRUD w/ 409-when-claimed; Settings >
  Transcoding GPUs card + transcoder-page device rows + preset-form
  inventory hint), deterministic claim order nvenc>qsv>vaapi + disabled
  filtering (G-30 FIRST HALF - vendor pin per preset still open), and
  config.max_parallel_transcodes moved env->DB (seed-once, per-tick
  read, schema-driven Settings field). G-31 relabel shipped in same PR.
- G-31 (minor): preset codec NULL = CPU spawn, no GPU injected; the
  session editor labels it "default" - relabel to "CPU (preset encoder)"
  or make codec required.
- Trixie base bump offered by the tester (Battlemage/B580 needs newer
  intel-media stack than bookworm non-free). bookworm is NOT load-bearing
  per se; the load-bearing part is the nv-codec-headers 12.1.14.0 pin
  (driver floor 530 - chosen BECAUSE trixie ships 550) + the 3-file
  ARM_NVENC_MIN_DRIVER coupling (see [[feedback_nvenc_header_driver_pin]]).
  Patch welcome if it keeps the pin, verifies QSV non-free driver names on
  trixie, and NVENC still builds.

Candidate additions surfaced from the 2026-09-12 live sessions, not yet in
the register: the transcode dispatcher's docker-over-SSH transport wedge
(dead paramiko transport is never rebuilt; unattended transcode halts until
backend restart) and the default `ARM_ALLOWED_ORIGINS` breaking ui-neu live
progress/events. See [[project_transcode_offload_architecture]].

2026-09-26 TESTER REPORT FOLLOW-UP (G-30/G-31 + trixie):
- Root causes found beyond G-30: encoder probe is BUILD-level (HandBrake
  --help token presence), not per-device - AMD vaapi rows get vce_* (needs
  AMF, absent) and fail; codec NULL + a HandBrake QSV preset_ref = CPU spawn
  with no device -> "no qsv"; _HW_ENCODER_TABLE lacks av1.
- DESIGN AGREED (brainstorm, spec NOT yet written): encoder-first presets
  (`encoder` VARCHAR: preset | cpu_<codec> | any_<codec> | <vendor>_<codec>,
  replaces codec+hw_preference, migration 0038), backend-spawned per-device
  probe container (real test encode, verified list on gpus row +
  probed_at/probe_error, auto at boot + Re-probe button; covers remote
  hosts), queue-if-busy / refuse-at-apply / fail-queued-if-hardware-vanishes,
  shared encoder catalog in arm_common, ARM_TRANSCODE_ENCODER env (+ legacy
  ARM_GPU_* kept one release). Stacks on #85. Next step: write spec.
- Transcode image -> trixie: IN PROGRESS on branch feat/transcode-trixie
  (off wolfy/main). Battlemage needs trixie's intel-media 25.2.3 /
  libmfx-gen 25.1.4 (bookworm 23.x). Keep nv-codec-headers 12.1.14.0 pin.
- FOLLOW-UP (not started): backend + ripper to trixie. Bookworm is in LTS
  since ~2026-06. Ripper renames verified: libavcodec59->61,
  libssl3->libssl3t64, liblept5->libleptonica6, openjdk-17->21; MakeMKV must
  build vs ffmpeg 7.1 + BD-J on Java 21; verify with iso-smoke + real BD +
  audio CD on hifi. Backend is a trivial FROM swap.
