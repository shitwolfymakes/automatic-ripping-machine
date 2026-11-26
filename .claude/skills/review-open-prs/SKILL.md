---
name: review-open-prs
description: Review this repo's open pull requests one at a time with Opus reviewer subagents. Each PR gets a code review for correctness plus checks against the CLAUDE.md quality guidelines, with findings split into blockers and nits and cited by file and line, and the owner gives a go or no-go after reading each report before anything is posted to GitHub. Use this whenever the user asks to review, triage or work through the open PRs, a PR stack or the review queue, asks for a go/no-go on pull requests, or asks for a code review of a specific PR number in this repo, even if they do not mention subagents or the guidelines.
---

# Review open PRs

This skill carries out the following request, in the owner's words:

> Spawn Opus agents do code review on the open pull requests. Also do spot checks on each PR against our CLAUDE.md quality guidelines. Specify nits vs blockers, and cite the lines for findings. One subagent at a time, and I'll give a go/no go on whether the PR is approved after I read the subagent report returned in this session.

The owner makes every decision. Your job is to put an accurate report in front of them for each PR, one they can check line by line, and then to post exactly the verdict they give. A reviewer subagent does the reading and measuring. You prepare its brief, check what it reports, and handle GitHub.

## The loop

1. Find the PRs. Check which repository `gh` resolves to before listing anything: in a fork checkout it can default to the upstream repository, whose open PRs are a different set. The PRs under review are the ones on the repository that `origin` points at, so pass `-R <owner>/<repo>` for origin on every `gh` call, and say in your first message which repository you are reviewing.

2. Order them. When the PRs form a stack, go from the bottom up, because a defect in a lower PR is inherited by everything above it. Review each PR against its own base branch, so the diff is from the merge-base of the base branch's head and the PR's head. A parent PR's content belongs to the parent's review.

3. Prepare one PR.
   - Record the head and base commit SHAs and work from those. Refs you fetch under `refs/remotes/origin/pr/<n>` can be pruned by a later fetch.
   - Add a detached worktree for the PR head in the session scratchpad. The base commit usually already has a worktree there from the parent PR's review, with dependencies installed.
   - Summarise the shape of the diff: files added, modified, deleted and renamed, lines by area, the commit list, the CI rollup and the PR description. The brief needs this to tell the reviewer where the weight is and what is generated.

4. Check out the PR's branch in the main checkout, if its working tree is clean. The reviewer never uses the main checkout. This is only so the file links in your report open in the owner's editor at the cited lines.

5. Spawn one reviewer with the Agent tool: `general-purpose`, model `opus`. Build the brief from [references/reviewer-brief.md](references/reviewer-brief.md).

6. Check the report before you relay it.
   - Open every cited `path:line` at the PR head. Reviewers get line numbers wrong often enough, and paths now and then, that an unchecked citation is not worth relaying. Correct what is wrong and say that you did.
   - Read the code behind each blocker yourself.
   - Confirm that both worktrees and the main checkout have no tracked changes and that nothing the reviewer started is still running.

7. Relay the report in this order: the recommendation, the blockers, the nits, the per-fix or guideline results, what the review did not cover. Keep correctness blockers apart from guideline blockers, and gaps the PR introduced apart from older ones. For each blocker say whether it was reproduced or inferred, and by whom. End by saying you are waiting for the go or no-go on that PR.

8. Start the next reviewer while the owner reads. "One subagent at a time" means reviewers never overlap. It does not mean waiting idle for a verdict, because the next review does not depend on it. When more than one report is waiting, list them by number at the end of each message. If the owner then answers without naming a PR, take the answer as covering every report you listed as waiting, and say so in your reply so they can correct you.

9. Act on the verdict as described in [references/posting-reviews.md](references/posting-reviews.md).

10. After the last PR, give a table of verdicts and what is left open: PRs whose heads moved after their review, findings that were not posted, the branch the main checkout is on, and the worktrees in the scratchpad.

## What a verdict means

A plain approval is an approving review with no comment body, pinned to the PR's current head.

"Comment the correctness and guideline findings and request changes", or any variant, is a request-changes review with inline comments for the findings the owner named and nothing else. Nits stay off the PR unless the owner asks for them. Tell the owner what you left off, so they can ask for more.

When the wording leaves it open whether a finding is included, post the narrower reading and say which finding you left out. A missing comment is easy to add. A comment the owner did not want is already in front of the PR's author.

When a finding is marked unverified and the owner asks for it to be verified, spawn a second agent for that one question and include its evidence in the comment. Layout and paint questions need a real browser, which jsdom is not. The "Scheme screenshots without the stack" note in `.claude/memory/project_dev_host_validation.md` has a recipe that works here: the UI's own dev server, a local mock for `/api`, and Playwright driving a system browser.

## Why the checks are there

Each of these has gone wrong in a real run.

- A PR's head can move while its review is running, because the author rebases the stack or pushes fixes. Before posting, compare the current head with the reviewed one. When only the SHA changed, compare `git patch-id` of the old and new PR diffs to see whether the content is the same.
- A reviewer can stall waiting on a command it started in the background. The brief tells it to run commands in the foreground.
- The SonarQube for IDE endpoint only analyses files in the main workspace that it has already indexed, so it cannot measure a worktree. For TypeScript and Svelte, run ESLint with the `sonarjs/cognitive-complexity` threshold set to 0 to get a number for every function. Python complexity is counted by hand with the S3776 rules and labelled that way. `.claude/memory/project_guidelines_audit.md` has the detail.
- Coverage gaps come in three kinds, and the owner weighs them differently: a gap on a line the PR added or changed, a gap that was already in a symbol the PR touches, and a Svelte-compiled fallback arm that cannot run and only needs naming in the test file's header comment. A report that lumps them together cannot be acted on.
- A test can look like a guard and not be one. The patterns that have slipped through are an unescaped `|` in a regex and optional chaining in front of `not.toBeNull()`, which passes when the element is missing. The brief asks the reviewer to run the PR's tests against the base commit, which shows which tests cannot fail.
- A PR description's claims about tests, coverage and "no behaviour change" are claims. Test counts in descriptions have been stale more often than not.
- Reviewers given a worktree have edited the main checkout before. See `.claude/memory/feedback_subagents_stay_in_worktree.md`.
- If the dev stack is running on the machine, it stays untouched. A reviewer that needs a backend uses a mock of its own.
