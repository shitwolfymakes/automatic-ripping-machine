---
name: install-sh-is-legacy
description: install.sh is legacy; no PR touches it unless load-bearing. Fixes are parked in arm-ai's installer-rewrite-carryover doc until the rewrite.
metadata:
  type: feedback
---

`install.sh` predates the drive-lifecycle model (still emits per-drive ripper
services) and is scheduled for a rewrite. Owner rule (2026-09-05): **do not
change `install.sh` in a PR unless the change is load-bearing**; PR #49's
installer half was cut for this reason.

**Why:** effort spent on the legacy script is thrown away by the rewrite, and
installer hunks are the main source of cross-PR merge conflicts.

**How to apply:** put installer fixes/notes in
`../arm-ai/arm-v3/docs/installer-rewrite-carryover.md` instead. `devtools/setup-dev.sh`
is the model the rewrite follows (no drive enumeration, build-only `arm-ripper`,
host-wide udev rule). See also [[no-em-dashes-in-ui-copy]] for the other owner copy rule.
