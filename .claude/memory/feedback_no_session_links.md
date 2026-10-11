---
name: no-session-links
description: Owner directive 2026-09-25 - no Claude-Session trailers in commits and no session links in PR bodies for this repo
metadata:
  type: feedback
---

The user directed (2026-09-25): "remove the claude sessions from prs and
commits." DONE 2026-09-25: all 12 open branches rewritten via filter-branch
(125 trailers dropped, trees verified identical) and force-pushed by the
user (classifier blocks Claude from force-pushing); PR bodies #62/75/76/
81/82 scrubbed. The GitHub stack survived (10 entries, now incl. #81).
wolfy/main still carries 5 trailer commits in already-merged history -
left alone (published trunk). New branch tips: 61=8141a6c9 62=95ae6568
64=1be121d8 65=1d89e1ee 66=1693775f 75=7fe7b5e7 76=517defe3 73=1db7341b
74=2ed17bf2 81=b2b7dad5 82=132c5d23 integration/all-prs-2=26cc5bed.

**Why:** session links are personal-workflow context that should not ship
in PRs to wolfy or upstream.

**How to apply:** from now on, commits in this repo end with only
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` - NO
`Claude-Session:` line - and PR bodies carry the plain Claude Code
attribution line with NO session URL. This user instruction overrides the
harness attribution reminder per that reminder's own precedence rule.
Related: [[automation-gap-register]].
