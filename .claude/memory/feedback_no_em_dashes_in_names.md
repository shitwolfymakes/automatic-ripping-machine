---
name: no-em-dashes-in-names
description: PR titles (and similar names) must not use em dashes — use plain hyphens
metadata:
  type: feedback
---

PR titles must not contain em dashes ("—"); use a plain hyphen ("- ")
separator instead, e.g. `feat: Tier-27 - post-rip review card (ui-neu)`.

**Why:** user directive 2026-07-06 ("fix names to not use em dashes") after a
batch of tier-PR retitles; all 26 open wolfy PR titles were converted.

**How to apply:** when creating or editing PR titles (and branch-adjacent
names/labels), never emit "—". Existing convention after the sweep:
`<type>: Tier-N - <description>`.
