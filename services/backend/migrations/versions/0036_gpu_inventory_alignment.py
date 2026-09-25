"""GPU inventory alignment (G-30 groundwork + env->DB config move).

Two columns, one alignment principle (env is for bootstrap and host wiring;
the DB is for anything an operator changes while the system runs):

* `gpus.enabled` — operator switch for the new Settings > GPUs card. The
  backend stops truncate-and-filling the gpus table from ARM_GPUS on every
  boot (which made UI edits impossible by construction); rows are now
  DB-authoritative and the env descriptor only seeds an empty table.
* `config.max_parallel_transcodes` — the dispatcher's parallelism cap moves
  from the MAX_PARALLEL_TRANSCODES env var into operator config. Backfilled
  by the backend's config seeder from the env value on the first boot after
  upgrade (a migration cannot see the container's env), then editable live
  from Settings; the dispatcher reads it per tick. NULL here means "not yet
  seeded" so the seeder can tell a fresh upgrade from an operator-set value.

Revision ID: 0036_gpu_inventory_alignment
Revises: 0035_session_routes_seed_marker
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_gpu_inventory_alignment"
down_revision: Union[str, None] = "0035_session_routes_seed_marker"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "gpus",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "config",
        sa.Column("max_parallel_transcodes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("config", "max_parallel_transcodes")
    op.drop_column("gpus", "enabled")
