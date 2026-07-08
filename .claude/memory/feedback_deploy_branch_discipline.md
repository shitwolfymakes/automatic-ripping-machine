---
name: deploy-branch-discipline
description: How changes flow between the deploy line, the wolfy PR stack, and upstream main — author on the PR stack, MERGE (never cherry-pick) into deploy, absorb main often
metadata:
  type: feedback
---

The fork runs three lines: **wolfy `main`** (upstream trunk), the **PR stack**
on wolfy (`feat/tier25-remote-transcode-offload` → `fix/installer-puid-abandon-eject`,
PRs #41/#48), and the **deploy line** (`deploy/hifi-YYYYMMDD`, ~318 commits of
fork features, what hifi runs).

**Why:** on 2026-07-06 the deploy line nearly "exploded": fixes were authored
on deploy and cherry-picked to the PR stack, creating patch-id twins whose
hand-edited variants (abandon-eject import resolve) plus upstream's own ripper
fixes made BOTH future merge directions conflict (verified via
`git merge-tree`). Two reconciliation merges (`5a2756ba` PR-line, `a5102e1a`
wolfy main) converted the twins into shared ancestry — both are now ancestors
of deploy, so their eventual landing on main merges as a no-op.

**How to apply:**

1. **Author each change ONCE, on the most-upstream branch it can live on** —
   usually the tip of the PR stack (or a new stacked branch). Never author
   shared code directly on the deploy branch.
2. **Bring it into deploy by `git merge` of that branch — NEVER `git
   cherry-pick`.** Merges share commit identity; cherry-picks mint twins that
   conflict later. Then run the full suite on deploy (it has features the PR
   line lacks, e.g. makemkv_sdf/tier33).
3. Deploy-only commits (`.claude/memory/` session state, hifi overlay tweaks)
   go straight on deploy and never into a PR.
4. **Absorb wolfy `main` into deploy promptly after every upstream merge** —
   small frequent merges, never a big bang. Check with
   `git merge-tree --write-tree deploy/... wolfy/main` (rc 1 = conflicts).
5. If a PR branch gets force-pushed (review rework), re-merge it into deploy
   immediately — the old commits in deploy's ancestry are then superseded and
   the new ones must join it.
6. A PR's diff vs its base is unaffected by any of this; keep PRs scoped
   (see [[project_session_state_2026-07-05]] — #41 was untangled once already).
7. Watch for auto-merge near-misses: the a5102e1a merge auto-resolved a
   duplicated `drive_poll` import without flagging a conflict — eyeball
   imports and run the suite after every reconciliation merge.
8. **Batch memory commits.** One `docs(memory)` commit per session wind-down
   (or per major milestone), not one per action — 7 of 20 commits at the
   2026-07-06 tip were memory noise interleaved with product code.
9. **History legibility notes:** the four 2026-07-05/06 fix subjects appear
   3x in deploy history (original + #48-line variant + #49-backport variant,
   three distinct patch-ids) — the one-time cost of converting cherry-pick
   twins into merge ancestry. Tag `deploy-reconciled-20260706` (origin only;
   never push tags to wolfy — release.yml consumes its tag namespace) marks
   the reconciliation point. When redeploying hifi next, cut
   `deploy/hifi-<date>` from the current tip per convention; don't rename
   mid-deploy. Dead PR branches get deleted on wolfy once superseded
   (#48's branch removed 2026-07-06; restorable from the PR page).

10. **Rebuilding a published stack branch (splits, history surgery): tree
    identity is NOT enough.** GitHub's PR diffs/mergeability use the
    merge-base, which moves when history is rewritten even if the tip tree
    is byte-identical — the direct child PR goes CONFLICTING with an
    inflated diff. Immediately `git merge -s ours <rebuilt-base>` on the
    child branch to link ancestry (zero content change; verify with
    `git diff HEAD~1 --stat` = empty), then the child's diff recomputes
    correctly. Done 2026-07-07 for the Tier-2 split (#51/#52/#7).
