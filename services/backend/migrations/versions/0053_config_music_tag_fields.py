"""Configurable music file tags.

`config.music_tag_fields` lists the tags, and the cover, the transcoder
writes into an encoded audio CD track. Every choice is on by default, so an
upgraded install keeps tagging exactly as before.

Revision ID: 0053_config_music_tag_fields
Revises: 0052_config_min_title_length
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_config_music_tag_fields"
down_revision: Union[str, None] = "0052_config_min_title_length"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALL_TAGS = (
    "'{artist,album_artist,album,title,track_number,track_total,disc_number,year,musicbrainz_release_id,cover}'::text[]"
)


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column(
            "music_tag_fields",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text(_ALL_TAGS),
        ),
    )


def downgrade() -> None:
    op.drop_column("config", "music_tag_fields")
