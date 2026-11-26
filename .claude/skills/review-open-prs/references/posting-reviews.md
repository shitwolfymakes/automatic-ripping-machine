# Posting a verdict

A review is posted from the owner's account and lands in front of the PR's author, so nothing goes up until the owner has given a verdict for that PR, and only what the verdict names goes up.

## Before posting

1. Check the PR's current head against the reviewed commit, and check that auto-merge is off:

   ```bash
   gh pr view <n> -R <owner>/<repo> --json headRefOid,autoMergeRequest,reviewDecision
   ```

   If the head moved, fetch it and compare the content of the old and new PR diffs:

   ```bash
   git diff <old-base> <old-head> | git patch-id --stable
   git diff <new-merge-base> <new-head> | git patch-id --stable
   ```

   When the ids match, the PR was only rebased and the review still applies; pin the review to the new head. When they differ, tell the owner what changed before posting anything.

2. Re-run the reproduction for each correctness finding you are about to post. The reviewer leaves its probes in the scratchpad. Copy one into the worktree, run it and delete it. A finding that no longer reproduces goes back to the owner and does not go on the PR.

3. For coverage findings, read the numbers and line lists from the reviewer's coverage output. Do not copy them from the prose of the report.

## Approving

An approval has no body:

```bash
gh api -X POST repos/<owner>/<repo>/pulls/<n>/reviews \
  -f commit_id=<head-sha> -f event=APPROVE
```

## Requesting changes

Post one review with a short body and one inline comment per finding. Write each comment to a file, build the payload from the files, and send it with `--input`, which avoids shell quoting problems with long Markdown.

```json
{
  "commit_id": "<head-sha>",
  "event": "REQUEST_CHANGES",
  "body": "<summary>",
  "comments": [
    { "path": "<repo-relative path>", "line": 123, "side": "RIGHT", "body": "<comment>" }
  ]
}
```

```bash
gh api -X POST repos/<owner>/<repo>/pulls/<n>/reviews --input payload.json
```

### Anchors

GitHub rejects an inline comment on a line that is outside the diff's hunks. List the hunk ranges on the head side for each file you want to comment on:

```bash
git diff -U3 <base> <head> -- <path> | grep '^@@'
```

A line in a new file is always in range. When the finding is on a line the PR did not change, as older coverage gaps usually are, anchor the comment on the nearest changed line in that file and name the real line in the text. When the file is not in the diff at all, for example a stale doc elsewhere in the repo, put the point in the review body.

Several findings of the same kind in different files can share one comment, anchored in one of the files, with the others listed by file and line.

### What a comment says

The reader is the PR's author, who has not seen the report. Each comment stands by itself:

- what is wrong, and where, with the line numbers of the other places involved;
- the concrete input or state that triggers it, and what the user sees;
- how to reproduce it, in a sentence the author can turn into a test;
- the suggested fix, worded as a suggestion when it reaches outside the PR;
- for a coverage gap, the measured numbers, and a plain statement when the gap is older than the PR.

Leave out local paths, the review process, and anything about who or what found the problem. Follow the repo's rule for outward-facing text in `.claude/memory/feedback_humanizer_outward_text.md`, and the rule on session links in `.claude/memory/feedback_no_session_links.md`.

The review body is two or three sentences: that changes are requested, what the inline comments cover, and any point that had no line to sit on. Do not add praise or findings the owner did not name.

## After posting

Confirm the result:

```bash
gh pr view <n> -R <owner>/<repo> --json reviewDecision
gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate \
  -q '.[] | "\(.path):\(.line // .original_line)"'
```

Then tell the owner:

- the link to the review;
- each comment, with its file and line and a one-line description;
- anything you added on your own reading of the verdict, so they can have it removed;
- what you left off the PR;
- the running table of verdicts.
