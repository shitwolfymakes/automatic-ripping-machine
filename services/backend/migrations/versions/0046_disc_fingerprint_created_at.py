"""Give disc_fingerprints.created_at its default and NOT NULL (D-185).

0006 created the column nullable with no server default, while the model
declares NOT NULL DEFAULT now() and leaves it out of the INSERT, so every
fingerprint row on Postgres stored NULL. Backfill existing rows from the
owning job's created_at (the fingerprint is recorded at scan, right after the
job is created), then set the default and the constraint the model expects.

Revision ID: 0046_disc_fingerprint_created_at
Revises: 0045_transcode_task_started_at
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046_disc_fingerprint_created_at"
down_revision: Union[str, None] = "0045_transcode_task_started_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE disc_fingerprints SET created_at = COALESCE("
        "(SELECT jobs.created_at FROM jobs WHERE jobs.id = disc_fingerprints.job_id), now()) "
        "WHERE created_at IS NULL"
    )
    op.alter_column(
        "disc_fingerprints",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "disc_fingerprints",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        nullable=True,
    )
