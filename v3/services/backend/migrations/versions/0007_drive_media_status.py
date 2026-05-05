"""Drive media_status / media_status_at columns.

Each ripper sends a periodic heartbeat carrying the host's
CDROM_DRIVE_STATUS reading. The backend stores the latest value here so
the manual-rip endpoint can fast-fail clicks made while the tray is
open or empty, instead of letting identify land an empty scan_result.

Both columns are nullable (existing rows + brand-new rippers that
haven't sent their first heartbeat yet) and stored as VARCHAR via
arm_common's enum_column helper — no Postgres ENUM type is created.

Revision ID: 0007_drive_media_status
Revises: 0006_disc_fingerprints
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_drive_media_status"
down_revision: Union[str, None] = "0006_disc_fingerprints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("media_status", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("media_status_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("drives", "media_status_at")
    op.drop_column("drives", "media_status")
