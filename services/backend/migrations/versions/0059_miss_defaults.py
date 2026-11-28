"""Defaults for a disc that misses identification.

Adds config.miss_media_type (movie|tv) and config.miss_titles_kept (all|preset),
both VARCHAR validated app-side by MissMediaType / MissTitlesKept.

Revision ID: 0059_miss_defaults
Revises: 0058_iso_name_hint_source
Create Date: 2026-11-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0059_miss_defaults"
down_revision: Union[str, None] = "0058_iso_name_hint_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("miss_media_type", sa.String(), nullable=False, server_default="movie"))
    op.add_column("config", sa.Column("miss_titles_kept", sa.String(), nullable=False, server_default="all"))


def downgrade() -> None:
    op.drop_column("config", "miss_titles_kept")
    op.drop_column("config", "miss_media_type")
