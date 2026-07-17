"""Denormalize the drive's hardware serial onto `jobs` and let `jobs.drive_id`
survive a drive deletion.

`jobs.drive_id` was `NOT NULL` with `ON DELETE RESTRICT`, so deleting any
drive with job history raised an IntegrityError (see the DELETE
/api/drives/{id} pre-review note). Since `drives.serial` (0016_1) now
captures the physical drive's hardware identity independent of the `drives`
row's lifecycle, snapshot it onto each job at creation time and let the FK go
`SET NULL` on delete — a drive row is disposable operational state, but which
physical drive ripped a disc is permanent job history and must survive the
row being removed.

Revision ID: 0016_2_jobs_drive_serial
Revises: 0016_1_drive_serial
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_2_jobs_drive_serial"
down_revision: Union[str, None] = "0016_1_drive_serial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("drive_serial", sa.String(), nullable=True))
    op.execute(
        "UPDATE jobs SET drive_serial = drives.serial "
        "FROM drives WHERE jobs.drive_id = drives.id AND drives.serial IS NOT NULL"
    )
    op.alter_column("jobs", "drive_id", nullable=True)
    op.drop_constraint("jobs_drive_id_fkey", "jobs", type_="foreignkey")
    op.create_foreign_key(
        "jobs_drive_id_fkey",
        source_table="jobs",
        referent_table="drives",
        local_cols=["drive_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("jobs_drive_id_fkey", "jobs", type_="foreignkey")
    op.create_foreign_key(
        "jobs_drive_id_fkey",
        source_table="jobs",
        referent_table="drives",
        local_cols=["drive_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )
    # Any job orphaned by a drive delete under the SET NULL regime has no
    # sane drive_id to restore; downgrading past this point on a DB that hit
    # that path isn't reversible. Fresh/test DBs (no orphans) still downgrade
    # cleanly.
    op.alter_column("jobs", "drive_id", nullable=False)
    op.drop_column("jobs", "drive_serial")
