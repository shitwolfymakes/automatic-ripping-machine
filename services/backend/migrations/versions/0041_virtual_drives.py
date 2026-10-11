"""virtual drives (ISO rips) + max_parallel_iso_rips

Revision ID: 0041_virtual_drives
Revises: 0040_identity_settings
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_virtual_drives"
down_revision: Union[str, None] = "0040_identity_settings"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("kind", sa.String(), nullable=False, server_default="optical"))
    op.add_column("drives", sa.Column("source_kind", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("source_path", sa.String(), nullable=True))
    op.add_column(
        "config", sa.Column("max_parallel_iso_rips", sa.Integer(), nullable=False, server_default=sa.text("1"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM drives WHERE kind = 'virtual'")
    op.drop_column("config", "max_parallel_iso_rips")
    for name in ("source_path", "source_kind", "kind"):
        op.drop_column("drives", name)
