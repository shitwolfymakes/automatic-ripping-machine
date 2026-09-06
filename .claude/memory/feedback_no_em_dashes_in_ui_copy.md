---
name: no-em-dashes-in-ui-copy
description: Owner rule on AI-typical special characters in the UI — no em-dashes, and no unicode symbols (✓ ✗ ⚠ → · … ≥ ▾ ○) used as UI; correct the characters, do not reword or change what is shown.
metadata:
  type: feedback
---

Correct AI-agent character habits in anything a user sees, in ui-neu and the
wolfy UI, and in backend strings the UI renders (diagnostic notes, `detail`
messages):

- No em-dashes (`—`). Use `:`, `,`, `.` or `and` in sentences; `-` for an
  empty cell; `(none)` for an empty select option.
- No unicode symbols standing in for UI: `✓ ✗ ⚠ ⏱ ✕ × → ← ▴ ▾ ▲ ▼ ○ ▸` become
  inline SVG glyphs (see [[glyph-icons-not-emoji]]); `…` becomes `...`; `≥`
  becomes `>=`; `·` field separators become `|` (or `,` in prose).

**Why:** owner directives 2026-09-04/05: "no em-dashes. I never want to see
them" and "I don't want to humanize or sanitize, I want to correct special
char usage commonly used by ai agents".

**How to apply:** this is character correction only. Do not reword copy, change
layout, logic or what is displayed while doing it. Comments and generated
files are out of scope. Seeded data names (built-in sessions/presets) are data,
not copy; changing them is a seeder + migration decision. Check with
`grep -rnP "[^\x00-\x7F]" src` minus comments/tests/generated before committing UI work.
