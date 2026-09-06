---
name: glyph-icons-not-emoji
description: UI status/indicator icons are inline SVG glyphs (the heroicons-style ones ui-neu already uses), never emoji or unicode symbols like ✓ ✗ ○.
metadata:
  type: feedback
---

Use inline SVG glyph icons for status and action indicators in the UIs, not
emoji and not unicode symbols (`✓`, `✗`, `⚠`, `○`).

**Why:** owner directive (2026-09-05, key-check UI): "use glyph icons and not
emojis". Emoji render differently per platform and clash with the themes.

**How to apply:** copy the existing inline `<svg class="h-4 w-4" ...>` patterns
in ui-neu (e.g. the amber warning triangle in the Drives diagnostics panel);
colour via Tailwind text classes. See also [[no-em-dashes-in-ui-copy]].
