---
name: project-s4-sweep
description: State of the S4 defect sweep on wolfy PR #383 (branch fix/s4-defects): which batches are done, which are held and why
metadata:
  type: project
---

Since 2026-10-20 the open `sev/S4` defects on shitwolfymakes/automatic-ripping-machine
are being fixed on one branch, `fix/s4-defects` (wolfy PR #383, one section per batch).

- Done: A docs drift (10), B CI/devtools (4, plus a vitest Node 25+ localStorage fix),
  E backend edge cases + WS hardening (19, via five parallel worktree agents).
- C1 (done 2026-10-20): ui-neu fixes in files no open PR touches:
  #253, #324, #331, #337, #389, #266.
- C2 HELD until UI PRs #375-#379 merge (same files): #265, #334, #343, #321, #333,
  #393. Each issue has a hold comment. Re-check each against main after they merge.
- D (ui-neu hygiene) also held for the same PRs. D-184 (#313) held for #374/#375 (config_metadata.py). F (common/migrations, minus D-184) done 2026-10-20. G
  (ripper/transcode/installer, 7) done 2026-10-20; D-174/175/179/217 unverified on hardware. D-158 (#287) left to the
  identification rework (#374-#376). D-118 (#240) is the owner's keep-or-delete call.

**Why:** fixing files the large UI reworks also change would force a rebase on one side.

**How to apply:** after each batch, review agent findings and file follow-ups as new
D-ids (last filed: D-248 = #401; note #399 is D-247 and #400 is D-246); see [[feedback-no-head-branch-rename]] and
[[feedback-run-affected-ci-suites]].
