---
name: project-tv-season-selection
description: State of the TV season selection work (wolfy draft PR #402, stacked on #379): what shipped, what is still to validate, and the agreed follow-ups
metadata:
  type: project
---

Since 2026-10-24 the TV season selection work is wolfy draft PR #402
(`feat/tv-season-selection`, stacked on `feat/home-episode-match`, #379).
Design `docs/superpowers/specs/2026-10-23-tv-season-selection-design.md`,
plan `docs/superpowers/plans/2026-10-23-tv-season-selection.md`.

Shipped: uncapped hint-ordered season scan with `hold_reasons`; episode-shaped
anchor and nominal rule; siblings by show id; operator-placed tracks as
constraints; `scan_seasons` and the seasons endpoint; clearing forgets;
TheDiscDB job claims; season in the Info form on card and job page; per-row
season and runtime-sorted picker; "Fill the rest"; shared `SeasonSelect`.

Still to do before undraft: walk the design's Definition of done (section 7)
on a dev stack with a TV disc or ISO, items 6 and 8 first.

Agreed follow-ups, not in the PR: (1) a hand pick in the middle of a disc
fills only one side ("Fill the rest" uses the best single run) — reserve
operator-placed episodes without splitting runs; (2) an "interleaved seasons"
baseline scenario (disc 2 of one season, then disc 3 of another, with and
without label seasons); (3) the alignment model itself (title order is not
episode order on 42% of real discs) remains the next project.

**Why:** the owner chose to stabilise the operator's path first and accept
held results; the matcher rewrite is separate.

**How to apply:** any change in `identity/episodes/` or `episode_stage.py`
runs `devtools/tv-match-baseline.py` before and after (see
[[project-tv-match-corpus]]); UI season work builds on `SeasonSelect` and
never defaults a season.
