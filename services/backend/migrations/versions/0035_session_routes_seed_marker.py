"""One-shot seed marker for session_routes (I1).

`_seed_session_routes` (seeders.py) gates on "table empty" so it stays
idempotent across every backend boot. That gate has a bug: a user who
deliberately clears every route (e.g. both built-in music routes) gets them
silently reseeded on the very next restart, because "empty" can't
distinguish "never seeded" from "seeded then deleted".

Fix: `config.session_routes_seeded` is a one-shot marker. The seeder now
seeds only when the table is empty AND this flag is false, and always sets
it true afterward (whether it seeded fresh rows or found the table already
populated) — see the updated `_seed_session_routes`.

This migration sets the new column to TRUE in `upgrade()` only where
`session_routes` currently has rows (`WHERE EXISTS (SELECT 1 FROM
session_routes)`), never unconditionally. Reasoning: an empty
`session_routes` table at migration time is ambiguous between two
deployments, and only a rows-present table proves which one we're looking
at:
  * The operator never touched routes and the seeder already ran (rows
    present) -> marking `seeded=true` is simply catching the flag up to
    reality, no behavior change.
  * The operator deliberately cleared the routes (rows absent, but they
    HAD run before) -> indistinguishable at the SQL level from the next
    case, so this migration cannot special-case it; conflating it with
    "never seeded" and marking seeded=true anyway would be the safer of
    two imperfect choices IF it didn't collide with the far more common
    case below.
  * The install predates the seeder shipping at all, or never had
    `_seed_session_routes` run for any other reason (rows absent, never
    seeded) -> this is the common case for an existing deployment picking
    up 0034+0035 in the same upgrade. It never deliberately deleted
    anything, so `seeded=false` is correct here: the boot seeder's
    existing empty-table-AND-flag-false gate (see `_seed_session_routes`)
    seeds the built-ins exactly once, on the first boot after upgrade.
A brand-new database created after this migration exists gets the column's
`false` default from the very first boot (no upgrade() involved), so its
seeder still runs once, normally.

Downgrade drops the column (a rerun of the seeder next boot returns to the
old empty-table-gate behavior).

Revision ID: 0035_session_routes_seed_marker
Revises: 0034_session_routes
Create Date: 2026-09-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_session_routes_seed_marker"
down_revision: Union[str, None] = "0034_session_routes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("session_routes_seeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # See module docstring: only mark seeded=true where session_routes
    # already has rows — that's the only state an empty table can't fake,
    # and it's the only state where the old empty-table seed gate is known
    # to have already fired. An empty table with no prior proof of a seed
    # is left seeded=false so the boot seeder gets its one real shot.
    op.execute(
        sa.text("UPDATE config SET session_routes_seeded = true WHERE EXISTS (SELECT 1 FROM session_routes)")
    )


def downgrade() -> None:
    op.drop_column("config", "session_routes_seeded")
