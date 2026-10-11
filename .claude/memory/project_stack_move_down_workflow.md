---
name: stack-move-down-workflow
description: How defect-register "move-down" rows are hoisted into their origin PR on the v3 stack, and why a full restack is deferred
metadata:
  type: project
---

Move-down (2026-10-03, first batch D-002/013/014/015/051/053/054/055/069):
cherry-pick the fixing commit from the later PR onto the origin PR's branch
(`recut/<branch>` in the stack-recut worktree), run the zero-infra checks at
that head (`uv run pytest`, `bash devtools/test-setup-dev.sh`, the one vitest
file), push to arm-v3 first (draft mirror PRs #129-#133 give CI; arm-v3 CI
only runs on pull_request events, never on bare pushes), then fast-forward
wolfy, close the register issue with the hoist SHA, relabel `status/hoisted`,
and mark the row `hoisted` in `docs/plans/DEFECT_REGISTER.md`.

When the later commit bundles unrelated work (34260a69 also added
`--ripper-only`), port only the relevant functions by hand instead of
cherry-picking; keep the later PR's own scope where it is.

The duplicate copy higher in the stack is left in place: it becomes empty on
restack and GitHub's PR diff for the higher PR is unchanged until then.

**Why no full restack yet:** a dry run rebasing every PR above #62 onto its
restacked parent hit 12 conflicts in #74 alone (the 212-file styling pass;
the stack's bases are all stale, so the restack absorbs that drift too). It
costs more than the merge-forward it replaces. Restack bottom-up as PRs
merge instead.

**How to apply:** hoist, verify, push arm-v3, then wolfy, then close the
row. Never leave a conflict-marker file in a commit (check
`grep -c '^<<<<<<<'` before `git commit`). Chains of hoists into the same
branch go in original commit order.
