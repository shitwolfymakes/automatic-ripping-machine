"""The cover art size a music session embeds.

Adds `sessions.music_cover_size`: the Cover Art Archive variant ("250",
"500", "1200" or "source", the image as uploaded). VARCHAR, validated
app-side by MusicCoverSize. Every session starts at "500", the size ARM
embedded before this setting existed.

Revision ID: 0055_session_music_cover_size
Revises: 0054_session_music_tag_fields
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_session_music_cover_size"
down_revision: Union[str, None] = "0054_session_music_tag_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("music_cover_size", sa.String(), nullable=False, server_default="500"))


def downgrade() -> None:
    op.drop_column("sessions", "music_cover_size")
