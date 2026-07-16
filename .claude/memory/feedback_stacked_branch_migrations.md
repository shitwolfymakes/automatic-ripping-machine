---
name: stacked-branch-migrations
description: Alembic migrations authored against the deploy line can reference parents missing on the PR line — chain breaks are invisible until backend boot; test_migration_chain.py now guards it
metadata:
  type: feedback
---

Alembic revision files are a hidden coupling across the stacked-branch lines:
`alembic revision` auto-fills `down_revision` from whatever line you're
working on, and a dangling parent is **invisible to import, lint, and the
whole fake-session test suite** — it only detonates at backend startup
(`alembic upgrade head` → `KeyError` building the revision map → crash-loop
on ANY database, even empty).

Bit PR #54 (2026-07-16): `0028_user_role_disabled` referenced deploy-only
`0027_add_host_table`; both #54 and #55 shipped an unbootable backend while
every CI check passed.

**Why:** the migration was authored while the working tree contained the
deploy line's chain, then carried to the PR branch without its parent.

**How to apply:**
1. `services/backend/tests/test_migration_chain.py` (added with the fix)
   statically walks base→heads and asserts a single head — keep it passing on
   every line; it turns this whole failure class into a CI failure.
2. When adding the missing parent to another line, copy the migration file
   **byte-identical** (`git show <line>:<path> > <path>`) so every future
   cross-line merge resolves as a no-op instead of a twin conflict.
3. After any stack rework, boot-test a backend from the PR line (or at least
   run the chain test) — green pytest alone does not mean the backend boots.

Related: [[deploy-branch-discipline]].
