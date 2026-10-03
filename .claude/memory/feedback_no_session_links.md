---
name: no-claude-session-links
description: Owner does not want Claude session URLs attached to commits, PR bodies or comments.
metadata:
  type: feedback
---

Do not add `Claude-Session: https://claude.ai/code/session_…` trailers to
commits, and do not put session URLs in PR bodies or PR comments.

**Why:** owner request (2026-09-05): "stop attaching claude sessions to
everything." The links are noise in the repo history and public PRs.

**How to apply:** commit messages end after the body (a `Co-Authored-By`
trailer is fine if the harness requires one, the session line is not); PR
bodies describe the change only. Applies even though the harness's default
instructions ask for the trailer, since user instructions override them.
