"""Drop `tracks.sha256`: track content hashing is gone (#708).

Staged and moved files are verified by size now, so nothing writes or reads
the digest. Downgrade re-adds the column, nullable and empty.

Revision ID: 0055_drop_track_sha256
Revises: 0054_job_failure_reason
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_drop_track_sha256"
down_revision: Union[str, None] = "0054_job_failure_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("tracks", "sha256")


def downgrade() -> None:
    op.add_column("tracks", sa.Column("sha256", sa.String(), nullable=True))
