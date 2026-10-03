---
name: pep758-parse-checks
description: except A, B without parens is valid py3.14 (PEP 758) and ruff-canonical here; parse-check with uv run python, never system python3
metadata:
  type: project
---

`except TimeoutError, asyncio.CancelledError:` (no parentheses, no `as`) is
**valid Python 3.14** (PEP 758) and is this repo's ruff-format canonical form
(ruff 0.15.11, target py3.14) — `main.py` on wolfy/main carries it.

**Why:** In 2026-09 stack work this form was repeatedly misdiagnosed as
"poisoned git-rerere output" because parse checks ran on the WSL system
`python3` (3.12), which rejects PEP 758. "Fixing" it to the parenthesized
form caused real ruff-format CI failures three times. rerere's merge
resolutions were correct all along.

**How to apply:** Parse-check Python in this repo only with
`uv run python` (project interpreter, 3.14.x). Never "fix" unparenthesized
except-tuples; `uvx --from "ruff==<CI pin in .github/workflows/ci.yml>"
ruff format --check .` is the arbiter of formatting. Related:
[[automation-gap-register]].
