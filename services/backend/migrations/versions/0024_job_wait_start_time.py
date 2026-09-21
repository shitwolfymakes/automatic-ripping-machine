"""Add wait_start_time column to jobs table.

Stamps when a disc's timed review-gate countdown started (AWAITING_REVIEW), so
the ripper can compute the remaining auto-start delay and the UI a countdown.

Revision ID: 0024_job_wait_start_time
Revises: 0023_config_hold_for_review
Create Date: 2026-06-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_job_wait_start_time"
down_revision: Union[str, None] = "0023_config_hold_for_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("wait_start_time", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "wait_start_time")
