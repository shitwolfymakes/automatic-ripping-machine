---
name: project-tv-match-corpus
description: Real-disc TV corpus from TheDiscDB under services/backend/tests/fixtures/thediscdb/ and the matcher baseline it measured (2026-10-23); use it for any episode-matching change
metadata:
  type: project
---

Since 2026-10-23 a corpus of 200 real TV discs (7 series) built from the
TheDiscDB data repo lives at `services/backend/tests/fixtures/thediscdb/`
(generator `devtools/thediscdb-fixture.py`, upstream commit in
`manifest.json`; loader `tests/thediscdb_corpus.py`; baseline harness
`devtools/tv-match-baseline.py`). Branch `feat/tv-season-selection`. Review
and numbers: `../arm-ai/arm-v3/docs/superpowers/specs/2026-10-23-tv-season-selection-review.md`.

Baseline of the current matcher on it: 24% of titles placed correctly with the
season known, 51% with lower discs already ripped. Causes: extras inflate the
anchor's title count, 42% of discs list episodes out of MakeMKV title order
(16% out of playlist order too), uniform runtimes are always ambiguous, bonus
discs repeat a season.

**Why:** the matcher was written and tested against synthetic in-order discs;
the corpus is the only check against real layouts.

**How to apply:** any change to `identity/episodes/` or `episode_stage.py`
runs the baseline before and after and quotes both; a new disc shape goes
into the corpus by adding the series to `SERIES` in the generator, not as a
hand-written fixture. See [[project-s4-sweep]] for the branch hold rules.
