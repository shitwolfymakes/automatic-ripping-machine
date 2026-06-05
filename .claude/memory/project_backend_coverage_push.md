---
name: project_backend_coverage_push
description: Backend coverage push — COMPLETE (100% statements / 99% branch); how it's structured and the remaining residual partial-branches
metadata:
  type: project
---

Effort (2026-05-16, branch `wolfy/v3-improvments`) to drive
`services/backend` to full coverage. **Done.** See
[[project_backend_test_harness]] for the two test tiers.

**Result: 70% → 99%** (branch coverage); **100% of statements** (2833/2833),
842 branches with **7 residual partial-branches**, 617 backend tests, all
green. Committed in ~25 small per-module `test(v3-backend): ...` commits.
The whole-suite CI command (`uv run pytest`) is green (745 passed) after
the test_dispatcher.py basename collision was fixed (ripper's renamed to
`test_rip_dispatcher.py`).

**Every backend module is at 100% statements.** The only non-100% (by
branch) are deep async/race code, left as documented residual partial-
branches (not worth fragile fault-injection): `routers/sessions.py`
(139->146), `routers/transcoder.py` (4 owner/early-return arrows),
`transcode_dispatcher.py` (182->204 stale-aggregate-None, 385->387 GPU
env). Genuinely-unreachable code carries justified `# pragma: no cover`
(short inline + a comment on the line above — ruff reflows long inline
pragmas and misplaces them) or `# pragma: no branch`: db.get_session,
main()/lifespan defensive+shutdown arms, ws union fallthrough, exhaustive-
enum raises, the dead docker-py ImportError fallback, two dispatcher race
guards. Coverage config also excludes Protocol/overload `...` stubs.

CI **measures** coverage (`coverage run -m pytest` + `coverage report`,
config in `pyproject.toml [tool.coverage]`, branch=true) but does
**not gate** — the user explicitly chose "measure but don't fail yet". A
`fail_under` ratchet (≈97–98, below the achieved 99 to allow noise) is
ready to add when they want the regression floor; it was deliberately
left off, not forgotten.
