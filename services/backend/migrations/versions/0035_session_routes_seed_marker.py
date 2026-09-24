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

This migration sets the new column to TRUE unconditionally in `upgrade()`
for every already-deployed Postgres database, not just where
`session_routes` currently has rows. Reasoning: by the time this migration
runs, any real deployment has already been through at least one boot of the
0033 code, which means `_seed_session_routes`'s old empty-table gate has
already had its one shot at seeding. Two cases:
  * The operator never touched routes -> the table already holds the
    built-in rows -> marking `seeded=true` is simply catching the flag up
    to reality, no behavior change.
  * The operator deliberately cleared the routes -> the table is empty, but
    re-seeding on the next boot would be exactly the bug this migration
    exists to close -> marking `seeded=true` here is what prevents that
    resurrection.
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
    # See module docstring: any DB reaching this migration has already had
    # its one shot at the old empty-table seed gate, so mark it seeded
    # unconditionally to stop the reseed-after-deliberate-delete bug.
    op.execute(sa.text("UPDATE config SET session_routes_seeded = true"))


def downgrade() -> None:
    op.drop_column("config", "session_routes_seeded")
