"""Music file tags move from Settings to music sessions.

Adds `sessions.music_tag_fields` with every tag on, copies the global
`config.music_tag_fields` (0053) onto the operator's own music sessions so
they keep tagging as before, and drops the config column. Built-in sessions
are read-only, so they keep every tag; clone one to change it.

Revision ID: 0054_session_music_tag_fields
Revises: 0053_config_music_tag_fields
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_session_music_tag_fields"
down_revision: Union[str, None] = "0053_config_music_tag_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALL_TAGS = (
    "'{artist,album_artist,album,title,track_number,track_total,disc_number,year,musicbrainz_release_id,cover}'::text[]"
)


def _tag_column() -> sa.Column:
    return sa.Column(
        "music_tag_fields",
        postgresql.ARRAY(sa.String()),
        nullable=False,
        server_default=sa.text(_ALL_TAGS),
    )


def upgrade() -> None:
    op.add_column("sessions", _tag_column())
    op.execute(
        "UPDATE sessions SET music_tag_fields = config.music_tag_fields "
        "FROM config WHERE config.id = 1 AND sessions.media_type = 'music' AND NOT sessions.is_builtin"
    )
    op.drop_column("config", "music_tag_fields")


def downgrade() -> None:
    op.add_column("config", _tag_column())
    op.drop_column("sessions", "music_tag_fields")
