---
name: ripper-restart reconciliation gap (file PR to wait-PR)
description: Two related defects — resolve-after-identify-timeout never rips, AND a ripper restart on a disc-in-drive mints a duplicate job — same root family, both for the wait-PR follow-up
metadata:
  type: project
---

**Status (2026-06-26):** diagnosed, NOT fixed. To be filed as a follow-up PR
against the **timed-review-gate / wait PR** (per user). Task #58 tracks BOTH.

Root family: a ripper restart / re-scan on a disc still in the drive is **not
reconciled** against the disc's existing job. Two visible symptoms:

## Defect 1 — resolve-after-timeout never rips
Ripper `_await_resolution` for an `awaiting_user_id` disc has a HARD 30-min
ceiling: `RESOLUTION_WAIT_TIMEOUT_SECONDS = 30 * 60`
(`services/ripper/arm_ripper/job_controller.py:34`, *"we assume the user
abandoned the disc"*). After timeout the ripper drops to a bare heartbeat loop
(`job_id: null`) and does NOT re-pick-up. A later "Start rip" → backend
`resolve()` flips `awaiting_user_id -> identified` and emits `identify.resolved`
on `ripper.commands.{job.drive_id}` (`routers/jobs.py:902`) with **no waiter
listening** → the identified disc never rips. Secondary: `handleStartRip` in
`DiscReviewWidget.svelte` is fire-and-forget, so the no-op looks like success.

## Defect 2 — duplicate job on ripper restart
`identify` (`routers/ripper.py:273`) **unconditionally creates a new `Job`** —
no fingerprint/existing-job pre-check. (The "idempotent" comment there only
covers `(job_id, algo)` fingerprint dedup WITHIN one scan.) The boot-recovery
endpoints cover only narrow statuses:
- `/drives/{id}/in-flight-job` → `RIPPING` only (`ripper.py:551`)
- `/drives/{id}/held-job` → `AWAITING_REVIEW` only (`ripper.py:584`)

**Neither covers `awaiting_user_id` or `identified`.** So a ripper restart on a
disc-in-drive gets 404 from both (confirmed in live logs), falls through to a
fresh scan, and `identify()` mints a SECOND job for the same fingerprint.
Live evidence (hifi): MysterySuspense fingerprint `be0844c6873d7462` has TWO
jobs — `job_01KW3BY0YGK7RPVEBHENR3JNR7` (awaiting_user_id, the restart dup) and
`job_01KW2CS8D1G21990R9CA8S0FWZ` (identified, original) — both render on the
dashboard ("showing twice").

## Fix shape (decide in the PR)
1. `identify()` dedupes by fingerprint + drive: reuse/return an existing
   non-terminal job for the same disc instead of creating a new one.
2. Extend boot-recovery to cover `awaiting_user_id` + `identified` (a
   held-job-style endpoint returning the pre-rip job) so the ripper
   re-parks/re-picks-up instead of re-scanning.
3. Durable pickup so a resolve after timeout still rips (re-check the drive's
   job, or pull-based "needs pickup" the ripper acts on at heartbeat).
4. Optional UI: Start warns if no ripper accepted the work.

## Not a regression
All frontend work this session (Info tab, scanned titles, detail metadata, JSON
tree, review-card chips) is correct and unaffected. These are pre-existing
ripper/backend lifecycle gaps exposed by a restart + a long operator delay. The
device `sr0→sr1` re-enumeration in [[hifi-server-v3-deploy]] is a separate
device-binding issue, not this.
