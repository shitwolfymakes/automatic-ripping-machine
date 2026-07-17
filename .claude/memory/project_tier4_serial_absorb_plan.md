---
name: tier4-serial-absorb-plan
description: ABSORB COMPLETE 2026-07-16 — all 28 open PRs MERGEABLE + CI green after chain-absorbing main-rc3 through the whole tier stack (#11→#47 + #37) and up to deploy 81c66648; twin-resolution template + CI-gate lesson below; hifi still needs manual 0016_1/0016_2 DDL.
metadata:
  type: project
---

**State as of 2026-07-16 (supersedes the "simmer" plan):**
- wolfy merged PR #9 (tier4 drive-serial, migrations 0016_1/0016_2) and PR #10
  (Tier-5 imdb identify) into feat/neu-ports, then neu-ports → main (PR #6),
  version bumped to **3.0.0-rc3**.
- All 28 open stack PRs were repointed base=main (28/28 succeeded, done by
  Claude on owner instruction). 24 went CONFLICTING — main now carries tier4/5
  twins the stack never absorbed. #54/#55 among them.
- **Upstream re-parented `0017_config_metadata_provider` to
  `down_revision = "0016_2_jobs_drive_serial"`** (our lines say
  `0016_notification_inbox`). Main's chain is LINEAR, single head — the
  planned alembic merge revision is NOT needed anymore.

**DONE 2026-07-16: feat/user-management absorbed main (merge e33e067f, pushed;
PR #54 MERGEABLE; 1773 tests pass; ruff clean).** The twin-resolution template
for the remaining absorbs (#11–#47, then re-absorbs as tiers land):
- Migrations: main's re-parented 0017 auto-merges; chain stays linear →0028.
- auth.py: keep `require_writer` guest gating + main's nullable `drive_id` in
  `_verify_drive_owner` (None → 403 "job has no owning drive").
- ripper /identify: keep fork disc-reuse/review-gate flow, ADD
  `drive_serial=drive.serial` to the new-Job constructor; register keeps
  main's serial-swap rewrite (coalesce keeps old serial when ripper sends None).
- metadata/dispatcher.py: MUST take main's version (`omdb_api_key_override`
  ctor kwarg) — main.py passes it; keeping the fork file = TypeError at boot
  and git auto-merges it WRONG (silently keeps fork's).
- routers/system.py: fork's /stats + /resources + ISO_INGRESS_ROOT stay; adopt
  main's cached `_app_version` (env > VERSION file > pkg metadata) + its three
  cache-aware tests. Anonymous tests: guest semantics (200), drop main's 401s.
- Tests: union both sides' new tests; watch hunk placement (main's trailing
  asserts belong to THEIR test, not the fork's last test in the hunk).
- `except A, B:` WITHOUT parens is VALID py3.14 (PEP 758) and is what ruff
  0.15.11 formats to — not a syntax error, don't "fix" it.
- Regen after resolve: snapshot + services/ui npm openapi-types + ui-neu
  codegen.sh (both node_modules need install in a fresh worktree).

**Propagation DONE 2026-07-16:** ui-settings-polish 1bc55258 (PR #55
MERGEABLE, pushed wolfy), mobile-drawer-stats 75c9e56d (pushed origin),
deploy c42d959e (pushed origin+wolfy; 1847 tests). Deploy-side resolution
rule: deploy's per-host /resources (HostResourcesView + resource_probing)
supersedes the inline-psutil version arriving from below — keep deploy's.

**CHAIN ABSORB COMPLETE 2026-07-16:** all 22 tier PRs (#11–#47 + independent
#37) chain-absorbed bottom-up (one hard absorb at #11, then merges up the
stacked ancestry; rerere on), then propagated through #54 → #55 →
mobile-drawer-stats → deploy (81c66648, pushed origin+wolfy). All 28 open
PRs MERGEABLE, all CI runs green.

**CI-gate lesson (cost a red-CI repair pass):** local gate per level MUST
mirror CI: `uvx ruff@<pinned> format --check .` (whole repo, not just
services/packages), `ruff check .`, `uv run mypy -p arm_common -p
arm_backend -p arm_ripper -p arm_transcode`, `npm run check` in
services/ui-neu/frontend when present, pytest, and both codegens. Two
absorb-wide breaks to remember: (1) tier4's nullable jobs.drive_id needs a
None-guard in drives.py's jobs_by_drive grouping and `?? '-'` /
`driveLabel(...)` in ui-neu job-fields; (2) main's diagnostics rename
silently swallows fork endpoints/tests in auto-merges — grep for stale
`PreflightCheck`/`/preflight`/`/paths`/dropped `/stats` after every
system.py merge, and re-seed test_diagnostics_ok healthy for each check
the tier adds (makemkv, keydb, sdf, transcoder).

**⚠ hifi DB hazard (the re-parenting cost):** hifi applied 0017 under the OLD
ancestry; alembic_version=0028. After adopting main's re-parented 0017,
alembic considers 0016_1/0016_2 applied — they never ran on hifi. Before/when
tier4 content reaches deploy on hifi, apply their DDL manually (psql):
`ALTER TABLE drives ADD COLUMN serial VARCHAR;` then
`ALTER TABLE jobs ADD COLUMN drive_serial VARCHAR;`
`UPDATE jobs SET drive_serial = drives.serial FROM drives WHERE jobs.drive_id = drives.id AND drives.serial IS NOT NULL;`
`ALTER TABLE jobs ALTER COLUMN drive_id DROP NOT NULL;`
`ALTER TABLE jobs DROP CONSTRAINT jobs_drive_id_fkey;`
`ALTER TABLE jobs ADD CONSTRAINT jobs_drive_id_fkey FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE SET NULL;`
Also splice `ARM_DRIVE_SERIAL` into hifi's hand-generated ripper compose block
(udevadm ID_SERIAL_SHORT on quark), or accept serial=None (coalesce-safe).

**Also pending:** the other ~22 conflicting PRs (#11-#47) each need a main
absorb — wolfy merges bottom-up; coordinate/sequence with them. New-PR plan
(per-host stats + mobile drawer as stacked PRs off ui-settings-polish)
unchanged, but their auto-retarget target is now main.
