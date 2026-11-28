"""The "one version of the film" policy: a global default and a per-job snapshot (#751, D58-D60).

`config.tick_one_version` is the default for new discs (NOT NULL, true). `jobs.tick_one_version`
is the value a job snapshotted at creation and the card edits: NULL for a job that is not a
video disc. Video jobs that have not started yet take the default (true), so their review card
behaves as a new disc would; started jobs keep NULL.

Revision ID: 0057_tick_one_version
Revises: 0056_rip_end_on_completion
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_tick_one_version"
down_revision: Union[str, None] = "0056_rip_end_on_completion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("tick_one_version", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("jobs", sa.Column("tick_one_version", sa.Boolean(), nullable=True))
    op.execute(
        "UPDATE jobs SET tick_one_version = true "
        "WHERE disc_type IN ('dvd', 'bluray') "
        "AND status IN ('created', 'awaiting_user_id', 'identified', 'awaiting_review')"
    )


def downgrade() -> None:
    op.drop_column("jobs", "tick_one_version")
    op.drop_column("config", "tick_one_version")
