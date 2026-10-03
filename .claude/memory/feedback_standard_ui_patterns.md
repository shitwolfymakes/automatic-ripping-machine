---
name: standard-ui-patterns
description: Common UI elements (sort indicators, close buttons, status glyphs, filter chips) must be shared components, not one-off inline markup.
metadata:
  type: feedback
---

When a UI pattern recurs (sort buttons/indicators, close buttons, status
glyphs, segment/chip filters, action bars), implement it once as a shared
component under `services/ui-neu/frontend/src/lib/components/` and use that
everywhere; never paste one-off inline SVGs or bespoke markup per site.
Existing standards: `Glyph` (icon paths, `name` prop), `SortIndicator`,
`CloseButton`, `ConfirmDialog`, `LoadState`, `LogView`, `SectionFrame`.

**Why:** owner directive 2026-09-05: "for common patterns like sort-buttons or
other ui elements they should be standard and not one-off when possible".

**How to apply:** before adding markup, check the components dir for an
existing standard; if the pattern appears in two places, extract it. When
touching a site that still has a one-off, migrate it. See also
[[glyph-icons-not-emoji]] and [[no-em-dashes-in-ui-copy]].
