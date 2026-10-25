---
name: feedback-humanizer-outward-text
description: Run the humanizer skill over any outward-facing text (docs, PR bodies, commit messages, issue comments) before it ships
metadata:
  type: feedback
---

Use the `humanizer:humanizer` skill (embedded mode) on outward-facing text:
user and developer docs, PR descriptions, commit messages, and GitHub issue or
PR comments.

**Why:** owner directive 2026-10-20, given while fixing the S4 docs-drift batch.

**How to apply:** draft the text, check it against the humanizer patterns
(contrasts, one-line closers, triads, dashes, bold labels, inflated words),
then write the final version. Code, commands, paths and link targets stay
unchanged. Pairs with [[feedback-no-em-dashes-in-ui-copy]] and
[[feedback-docs-describe-current-state]].
