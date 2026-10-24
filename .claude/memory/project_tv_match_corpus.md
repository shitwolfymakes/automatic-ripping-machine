---
name: project-tv-match-corpus
description: Real-disc TV corpus from TheDiscDB under services/backend/tests/fixtures/thediscdb/ (260 discs, 9 series) and the matcher baseline it measures; use it for any episode-matching change
metadata:
  type: project
---

A corpus of 260 real TV discs (9 series, two of them deep-season) built from the
TheDiscDB data repo lives at `services/backend/tests/fixtures/thediscdb/`
(generator `devtools/thediscdb-fixture.py`, upstream commit in
`manifest.json`; loader `tests/thediscdb_corpus.py`; baseline harness
`devtools/tv-match-baseline.py`; regression floor
`services/backend/tests/test_tv_match_baseline.py`). Review
and numbers: `../arm-ai/arm-v3/docs/superpowers/specs/2026-10-23-tv-season-selection-review.md`.

Baseline of the matcher on it (`--min-seconds 60`, all 9 series): 24% of
titles placed correctly with the season known, 16% with nothing known, 47%
with lower discs already ripped. On the original 7 series the correct
placements are: nothing known 164, season known 242, season + disc known 308,
lower discs held 467, higher discs held 253, all others held 381 (the
regression test's floor). Causes of the misses: extras inflate the
anchor's title count, 42% of discs list episodes out of MakeMKV title order
(16% out of playlist order too), uniform runtimes are always ambiguous, bonus
discs repeat a season.

**Why:** the matcher was written and tested against synthetic in-order discs;
the corpus is the only check against real layouts.

**How to apply:** any change to `identity/episodes/` or `episode_stage.py`
runs the baseline before and after and quotes both; a new disc shape goes
into the corpus by adding the series to `SERIES` in the generator, not as a
hand-written fixture. TheDiscDB's new ODM sidecars (`discNN.odm.json`, 126 on
2026-10-23) are deliberately not consumed: the owner chose to stabilise the
existing MakeMKV-based process first; keep identifier kinds, the corpus reader
and the source registry open for them (review doc section 9). See
[[project-s4-sweep]] for the branch hold rules.
