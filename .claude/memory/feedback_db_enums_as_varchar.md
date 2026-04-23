---
name: DB enums stored as VARCHAR, not native Postgres enum types
description: In ARM v3 (and user's general preference), enum-valued columns are stored as plain VARCHAR and validated at the app layer — never as Postgres CREATE TYPE enums.
type: feedback
originSessionId: ecee9cac-70aa-42e9-b9f7-0285aaa7138d
---
Columns that carry a finite set of string values (status, mode, kind, vendor, etc.) are stored as `VARCHAR`. The `StrEnum` class in `packages/arm_common/arm_common/enums.py` is the source of truth; validation runs in the SQLModel/Pydantic layer at write time. No `CREATE TYPE ... AS ENUM`, no native enum columns, no CHECK constraints.

**Why:** (1) `ALTER TYPE ... ADD VALUE` is awkward in transactional migrations and Alembic autogenerate misses it. (2) Schema-diff tools like Atlas and Bytebase gate enum-diff features behind paid tiers — VARCHAR keeps their free tiers usable. (3) Validated at write time in the app anyway, so DB-level enforcement is redundant defense-in-depth that isn't worth the operational cost. The tradeoff accepted: a bad value inserted via raw psql or a rogue migration isn't caught by the DB.

**How to apply:** When adding a new status/mode/kind column, use `sa.String()` in Alembic migrations and `sa.String` in SQLModel `Field(sa_column=...)`. Use the `enum_column()` helper in `services/backend/arm_backend/models/_columns.py` — it takes the StrEnum class for call-site legibility but still emits a plain `String` column. Never import `sqlalchemy.Enum` or `postgresql.ENUM` in this project. Documented in `v3/docs/arch/04-data-model.md § Conventions`.
