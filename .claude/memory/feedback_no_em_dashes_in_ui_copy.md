---
name: no-em-dashes-in-ui-copy
description: Owner never wants em-dashes (—) in anything a user sees — UI strings, API notes/messages rendered by the UI, empty states, placeholders.
metadata:
  type: feedback
---

No em-dashes in user-facing copy. Applies to Svelte/Vue markup text, string
constants that render (labels, empty states, confirm dialogs), and backend
strings the UI shows (diagnostic notes, HTTP `detail` messages, notification
titles). Code comments and docs are not covered.

**Why:** Owner directive (2026-09-04, Plan 6 smoke): "no em-dashes. I never
want to see them."

**How to apply:** Rewrite with a colon, comma, period, or "and"
(`drive is detached: reconnect it`, `Plug one in and it appears here`).
Empty table cells use `-`; empty select options use `(none)`. Before
committing UI work, `grep -rn -- "—"` the touched markup/strings and the
backend messages they render. A repo-wide sweep of pre-existing strings
(e.g. `notification_events.py` titles, older ui-neu components) is still
open, see [[drive-lifecycle-followups]].
