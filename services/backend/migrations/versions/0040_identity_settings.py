"""identity settings: ranked episode / disc-hint sources, tolerance, auto-apply

Revision ID: 0040_identity_settings
Revises: 0039_identity_core
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_identity_settings"
down_revision: Union[str, None] = "0039_identity_core"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column(
            "episode_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{tmdb,tvmaze,tvdb}'::text[]"),
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "disc_hint_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{bd_title,label}'::text[]"),
        ),
    )
    op.add_column(
        "config",
        sa.Column("episode_match_tolerance_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
    )
    op.add_column(
        "config",
        sa.Column("episode_auto_apply", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    for name in ("episode_auto_apply", "episode_match_tolerance_seconds", "disc_hint_sources", "episode_sources"):
        op.drop_column("config", name)
