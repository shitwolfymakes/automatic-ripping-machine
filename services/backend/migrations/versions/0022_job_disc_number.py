"""Add disc_number and disc_total columns to jobs table.

Stores the disc index and total disc count for multi-disc CD sets,
populated during music metadata matching.

Revision ID: 0022_job_disc_number
Revises: 0021_community_keydb_fields
Create Date: 2026-06-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_job_disc_number"
down_revision: Union[str, None] = "0021_community_keydb_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("disc_number", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("disc_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "disc_total")
    op.drop_column("jobs", "disc_number")
