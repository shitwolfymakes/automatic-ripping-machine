"""Map the retired drives.status value 'ripping' to 'offline' (D-151).

Builds between 3d6c1d40 and b865234b wrote DriveStatus.RIPPING; the member is
gone and enum columns now reject a non-member at bind time, so a row still
holding 'ripping' would fail every read of /api/drives. The next ripper
heartbeat moves the drive back to 'online'.

Revision ID: 0047_drive_status_ripping
Revises: 0046_disc_fingerprint_created_at
Create Date: 2026-10-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0047_drive_status_ripping"
down_revision: Union[str, None] = "0046_disc_fingerprint_created_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE drives SET status = 'offline' WHERE status = 'ripping'")


def downgrade() -> None:
    # The old value cannot be told apart from a drive that was offline anyway.
    pass
