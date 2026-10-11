---
name: feedback-subagents-stay-in-worktree
description: Subagent implementers given a worktree path have also edited the main checkout; dispatches must forbid it and the controller must check the main checkout after each task
metadata:
  type: feedback
---

Implementer subagents dispatched to a `.claude/worktrees/<name>` worktree (2026-10-04, Blu-ray backup PR #121, cheapest-tier model) committed in the worktree **and** left identical uncommitted edits in the main checkout `/home/upb/src/automatic-ripping-machine`, which was on an unrelated branch (`feat/installer-rewrite`). The stray copy of `dispatcher.py` imported a module that does not exist on that branch.

**Why:** absolute paths to the main checkout leak into the agent's edits (it reads files by the main path, then edits them there). The worktree commit still looks right, so per-task review of the worktree diff does not catch it.

**How to apply:** in every implementer dispatch, state "edit files only under <worktree path>; never write to /home/upb/src/automatic-ripping-machine/<...> outside it". After each implementer reports, run `git -C <main checkout> status --short` and compare with the status before dispatch; revert stray copies only after confirming they match a commit on the feature branch. See [[project-armv3-tracking-fork]] for the branch layout.
