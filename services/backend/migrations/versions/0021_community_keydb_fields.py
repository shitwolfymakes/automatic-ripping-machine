"""Add community-keydb (FindVUK) fields to the config singleton.

Operator toggle (community_keydb_enabled, default on) plus three
ripper-reported status columns (state / vuk_count / checked_at). Pure
additive, reversible. Mirrors 0018's makemkv status columns.

Revision ID: 0021_community_keydb_fields
Revises: 0020_track_operator_fields
Create Date: 2026-06-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_community_keydb_fields"
down_revision: Union[str, None] = "0020_track_operator_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("community_keydb_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("config", sa.Column("community_keydb_state", sa.String(), nullable=True))
    op.add_column("config", sa.Column("community_keydb_vuk_count", sa.Integer(), nullable=True))
    op.add_column("config", sa.Column("community_keydb_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "community_keydb_checked_at")
    op.drop_column("config", "community_keydb_vuk_count")
    op.drop_column("config", "community_keydb_state")
    op.drop_column("config", "community_keydb_enabled")
