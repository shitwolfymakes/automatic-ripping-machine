"""TheDiscDB integration: tracks.season + config toggle/refresh columns.

Pure additive, reversible. Mirrors 0026's config-columns pattern.

Revision ID: 0030_thediscdb
Revises: 0029_drive_lifecycle
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_thediscdb"
down_revision: Union[str, None] = "0029_drive_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("season", sa.Integer(), nullable=True))
    op.add_column(
        "config",
        sa.Column("thediscdb_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "config",
        sa.Column("thediscdb_refresh_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
    )
    op.add_column("config", sa.Column("thediscdb_refreshed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "thediscdb_refreshed_at")
    op.drop_column("config", "thediscdb_refresh_days")
    op.drop_column("config", "thediscdb_enabled")
    op.drop_column("tracks", "season")
