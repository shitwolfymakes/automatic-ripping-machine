---
name: stack-linear-restack
description: The v3 PR stack was linearised on 2026-10-03 (zero merge commits, every PR descends from its base); how it was done, the backup, and the rules for keeping it linear
metadata:
  type: project
---

On 2026-10-03 the whole wolfy stack (#61 → #110, with #82 moved into the chain
above #101 and #105 above #82) was rewritten linear: 494 commits, 0 merge
commits, every PR head descends from its base's current head, every PR
MERGEABLE. GitHub's native stack feature now tracks #101..#110 (stack 114);
#82 sits outside it with base feat/iso-source-rip, and #105's base could not
be moved onto #82 through the API ("part of a stack") – use the web stack
editor if that matters.

Backup of every pre-restack head: `backup/pre-linear-20261003/<branch>` on
arm-v3 (38 refs), local tags of the same name, and a SHA manifest in the
session scratchpad. `integration/all-prs-4` (both remotes) is the merge of the
new top with #103; its tree is byte-identical to the pre-restack union.

Method (scratchpad `linearize.sh`, worth re-creating if needed): per PR,
replay old-parent..old-head onto the restacked parent with `--empty=drop`
(flattens base-refresh merges, drops replayed copies of hoisted commits by
patch-id or subject+file-set). Conflict policies in order: hoist duplicate →
ours; commit deletes a file → delete; last branch-side toucher → reference
tree; original merge M holds the resolution (no branch commit between touches
the file) → M's version; one-line definition replacement → ours minus line +
theirs; else theirs. Then REALIGN the branch to a reference tree in one
trailing commit (`restack: realign …`): reference = 3-way merge
(base = old parent head, ours = new parent, theirs = old head), conflicts to
the PR's own content in-chain, to the integration tip off-chain. 8 realign
commits remain; the large one in #88 is a package-lock approximation.

**Why:** stacking tools and GitHub stacks need linear branches; the stack had
been maintained by merging parents forward (14 branches with merge commits,
#74 with 27), which also made every hoist require a full restack.

**How to apply:** never merge a parent into a child again; restack (rebase)
the children instead, bottom-up, and force-push with a lease to BOTH remotes.
Keep-both conflict resolution is unsafe for code (it duplicated imports); use
the reference-tree realign instead. Parse `git merge-tree --name-only`
conflicts as the lines right after the tree id, up to the first blank line.
Never run two git commands concurrently in the same worktree (index.lock).
