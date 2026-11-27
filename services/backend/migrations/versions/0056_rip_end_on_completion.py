"""Add the end-on-completion rip setting: a global default on config, a per-drive override on drives.

config.rip_end_on_completion_message is NOT NULL and defaults to false. drives.rip_end_on_completion_message is
nullable; NULL follows the global. Both are plain booleans (no enum).

Downgrade drops both columns.

Revision ID: 0056_rip_end_on_completion
Revises: 0055_drop_track_sha256
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_rip_end_on_completion"
down_revision: Union[str, None] = "0055_drop_track_sha256"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("rip_end_on_completion_message", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("drives", sa.Column("rip_end_on_completion_message", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("drives", "rip_end_on_completion_message")
    op.drop_column("config", "rip_end_on_completion_message")
