"""Add drives.scanning: a ripper-reported pre-job scan is running.

Revision ID: 0051_drive_scanning
Revises: 0050_handbrake_settings
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_drive_scanning"
down_revision: Union[str, None] = "0050_handbrake_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("scanning", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("drives", "scanning")
