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

2026-10-25 tester walk follow-ups (on the PR): Season row on the card with
"Season not set" opening Info focused; one-line hold text with an (i) for the
rest ("Season 3 is a guess: ..."); "Accept and pin TMDb"; the held season as
a fact line plus one "Fix match" button (opens the re-run form); "View
sources"; the panel's `onchanged` so the card and job page reload tracks
after a write; Info tracks table uses the scan estimate pre-rip and labels
extras; placed count ignores a held suggestion. Backend: the ISO watchdog
restarts the ripper of a rip parked at a review gate once instead of failing
it, and identify on a virtual drive reuses its newest non-terminal job
(ISO scans carry no fingerprints). Both were proven live on hifi: the parked
Kolchak job survived two backend restarts; the first restart (before the
dedupe fix) left a duplicate parked job the owner retires by hand.

2026-10-25, second wave (design
`docs/superpowers/specs/2026-10-25-episode-match-no-accept-design.md`): no
accept step. A held result is applied as a guess (resolver ranks clean over
held, `identity_claims.unsure`, `JobView.episodes_unsure`); the ripper holds
the review countdown while it is a guess; the panel's only controls are Fix
match and Clear episodes (`DELETE /identity/match`); Accept, Pin and Unpin
are gone from the UI (the pin stays in the claims as the source chosen in
Fix match). The design canvas "TV Season Flow" still shows the old flow and
needs its A/B row redrawn against this.

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
