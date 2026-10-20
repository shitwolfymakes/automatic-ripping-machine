---
name: feedback-no-head-branch-rename
description: Renaming a PR's head branch on GitHub closes the PR (only base-branch renames retarget); pick the final branch name before opening
metadata:
  type: feedback
---

Renaming the head branch of an open PR (the `branches/{b}/rename` API or the
web UI) closes that PR, and it cannot be reopened because its head ref is gone.
Only a renamed *base* branch carries its PRs along.

**Why:** 2026-10-20, renaming `docs/s4-docs-drift` to `fix/s4-defects` closed
wolfy #382; it was replaced by #383.

**How to apply:** ask whether a branch will grow beyond its first batch before
naming it. To rename later, push the new name, open a new PR, and comment on
the old one; never call the rename API on a head branch.
