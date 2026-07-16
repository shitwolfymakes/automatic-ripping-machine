---
name: tier4-serial-absorb-plan
description: PENDING — wolfy's PR #9 (tier4 drive-serial, migrations 0016_1/0016_2) is simmering; when it lands, the absorb needs an alembic merge revision + twin reconciliation. The full plan, decided 2026-07-16.
metadata:
  type: project
---

wolfy pushed `dc510be1` to `feat/tier4-quickwins` (PR #9, base feat/neu-ports,
verified 2026-07-16: suite green, merges clean into neu-ports): drive identity
anchored to hardware serial (`Drive.serial` via udev ID_SERIAL_SHORT threaded
from setup-dev.sh → ripper `ARM_DRIVE_SERIAL` → register endpoint swap
detection with coalesce-guarded upsert), and jobs survive drive delete
(`jobs.drive_id` → nullable + ON DELETE SET NULL, permanent `Job.drive_serial`
snapshot). Migrations **0016_1_drive_serial → 0016_2_jobs_drive_serial**, both
hanging off `0016_notification_inbox`.

**Owner decision 2026-07-16: let PR #9 simmer; pick up its changes when it
lands.** No pre-staging, no ordering nudge to wolfy.

**When absorbing (whoever does it):**
1. **Migration two-heads:** fork's `0017_config_metadata_provider` shares
   parent `0016_notification_inbox` with their `0016_1` → after the merge the
   chain branches and `alembic upgrade head` refuses. `test_migration_chain.py`
   (on the stack since PR #54) fails immediately — expected. Fix: an **empty
   alembic merge revision** on the absorbing branch,
   `down_revision = ("0016_2_jobs_drive_serial", "0028_user_role_disabled")`
   (or the then-current fork head). NEVER re-parent existing migration files —
   deployed DBs (hifi at 0028+) assume recorded ancestry ran; the merge
   revision makes hifi apply only the unapplied 0016_1/0016_2 branch.
2. **Twin conflicts:** PR #9 also carries older tier4 quick-wins (naming
   validate, system /version, music disc token) that the fork line implemented
   separately — expect ~a dozen conflicts concentrated in auth.py (guest gating
   vs nullable-drive_id `_verify_drive_owner`), routers/ripper.py (review-gate
   vs register rewrite), routers/system.py, routers/naming.py,
   metadata/musicbrainz.py, schemas. Same union playbook as the 2026-07-16
   neu-ports reconciliation ([[deploy-branch-discipline]],
   [[stacked-branch-migrations]]).
3. **Regen** services/ui openapi snapshot + services/ui npm openapi-types +
   ui-neu scripts/codegen.sh (per line — deploy regenerates from its own
   snapshot).
4. **hifi compose:** the ripper service is hand-spliced; add
   `ARM_DRIVE_SERIAL` (from `udevadm info --query=property --name=/dev/sr0 |
   sed -n 's/^ID_SERIAL_SHORT=//p'` on quark) or accept serial=None — the
   coalesce upsert degrades gracefully.

Optional cheap win still on the table: upstream `test_migration_chain.py` to
neu-ports as a standalone PR so wolfy's line gets the chain guard in CI.
