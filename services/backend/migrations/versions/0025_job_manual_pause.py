"""Add manual_pause column to jobs table.

Per-job review-gate pause: freezes a single held disc's auto-start countdown
(distinct from the global ripping_paused). Defaults false.

Revision ID: 0025_job_manual_pause
Revises: 0024_job_wait_start_time
Create Date: 2026-06-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_job_manual_pause"
down_revision: Union[str, None] = "0024_job_wait_start_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("manual_pause", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "manual_pause")
