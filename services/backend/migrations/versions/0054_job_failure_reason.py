"""Add jobs.failure_reason: why a FAILED job failed, as text for the operator.

Free text, so a plain nullable VARCHAR (no enum). Jobs that failed before this
column existed keep it NULL.

Revision ID: 0054_job_failure_reason
Revises: 0053_drive_scanning
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_job_failure_reason"
down_revision: Union[str, None] = "0053_drive_scanning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("failure_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "failure_reason")
