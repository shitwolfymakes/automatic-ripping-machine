---
name: pytest-invocation-and-no-tests-init
description: Never add __init__.py to any tests/ dir; file-path pytest runs are fine, the full suite is the root invocation
metadata:
  type: feedback
---

Each service's `tests/` dir (`backend`, `ripper`, `transcode`, and `packages/arm_common`) is a namespace package with no `__init__.py`, importable as `tests.*` (for example `from tests._fakes import FakeSession`). They coexist only as namespace packages.

**Why:** a stray empty `packages/arm_common/tests/__init__.py` (created by a subagent) turned that dir into a concrete `tests` package that shadowed the backend's namespace `tests` and broke `tests._fakes` collection for every backend module. Removing it restored collection.

**How to apply:**
- Never create an `__init__.py` in any `tests/` directory.
- The full suite is `uv run pytest` from the repo root (`testpaths` in the root `pyproject.toml`). Running one file by path from the repo root also works, and since D-238 (2026-10-20) `services/backend/tests/conftest.py` sets `DATABASE_URL` and `ARM_SERVICE_TOKEN` once, so any backend file collects alone. An earlier version of this note said file paths break collection; that was the `__init__.py` shadowing, not the path.
- A subagent's "N/N pass" from a per-file run is not the full suite: run the root invocation once before claiming green.
