---
name: tier4-serial-absorb-plan
description: LIVE — tier4 (#9) + Tier-5 (#10) merged upstream, neu-ports folded into main (rc3), stack repointed to main 2026-07-16; 24 PRs CONFLICTING pending absorb. Upstream re-parented 0017 → NO merge revision needed, but hifi needs manual 0016_1/0016_2 DDL.
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

**Absorb checklist (bottom of our stack first — feat/user-management):**
1. Merge wolfy/main into feat/user-management. Take MAIN's 0017 file (the
   re-parented one — same revision id must have one content everywhere).
2. Twin conflicts: tier4 quick-wins vs fork implementations — auth.py
   (`_verify_drive_owner` nullable drive_id vs guest gating), routers/ripper.py
   (register serial-swap rewrite vs review-gate), routers/{system,naming}.py,
   metadata/musicbrainz.py, schemas, tests. Union playbook per
   [[deploy-branch-discipline]]; deploy remains the fork-feature oracle.
3. test_migration_chain.py should PASS after (linear chain 0016→0016_1→0016_2
   →0017→…→0028). If it reports two heads, main's 0017 didn't win — fix that.
4. Regen: services/ui snapshot + npm openapi-types + ui-neu codegen.sh.
5. Propagate up: ui-settings-polish → mobile-drawer-stats → deploy.

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
