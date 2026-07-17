---
name: pytest-invocation-and-no-tests-init
description: Run pytest from repo root with NO file path; never add __init__.py to any tests/ dir
metadata:
  type: feedback
---

The Python test suite must be invoked as bare `uv run pytest` (optionally `-k <name>`) **from the repo root** — it relies on `testpaths` in the root `pyproject.toml`. Passing an explicit file path (`uv run pytest services/backend/tests/foo.py`) breaks collection with `ModuleNotFoundError: No module named 'tests._fakes'`, because each service's `tests/` is a **namespace package** (no `__init__.py`) and pytest's rootdir/sys.path insertion only happens under the testpaths-driven invocation.

**Why:** `backend`, `ripper`, and `transcode` each have a `tests/` dir importable as `tests.*` (e.g. `from tests._fakes import FakeSession`). They coexist only as namespace packages.

**How to apply:**
- Run subsets with `uv run pytest -q -k "<name>"` from the repo root, never by file path.
- **Never create an `__init__.py` in any `tests/` directory.** A stray empty `packages/arm_common/tests/__init__.py` (created by a subagent) turned that dir into a concrete `tests` package that **shadowed** the backend's namespace `tests`, breaking `tests._fakes` collection for all 49 backend test modules. Removing it restored the full 1166-test collection.
- When a subagent reports "N/N tests pass" from a path-based or per-package run, distrust it — verify with the root invocation, which is the only one that exercises the real cross-service collection.
