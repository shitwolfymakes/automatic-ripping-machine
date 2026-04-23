"""disc fingerprint columns on jobs

Revision ID: 0002_disc_fingerprint
Revises: 0001_initial
Create Date: 2026-04-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_disc_fingerprint"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("disc_fingerprint", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("disc_fingerprint_algo", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("aacs_disc_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "aacs_disc_id")
    op.drop_column("jobs", "disc_fingerprint_algo")
    op.drop_column("jobs", "disc_fingerprint")
