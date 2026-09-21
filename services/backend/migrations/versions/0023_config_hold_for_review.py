"""Add hold_for_review and manual_wait_seconds columns to config table.

Backs the timed pre-rip review gate: hold_for_review toggles the gate on, and
manual_wait_seconds is the review countdown duration before the rip auto-starts.

Revision ID: 0023_config_hold_for_review
Revises: 0022_job_disc_number
Create Date: 2026-06-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_config_hold_for_review"
down_revision: Union[str, None] = "0022_job_disc_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("hold_for_review", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "config",
        sa.Column("manual_wait_seconds", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("config", "manual_wait_seconds")
    op.drop_column("config", "hold_for_review")
