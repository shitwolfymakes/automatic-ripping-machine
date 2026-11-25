"""The largest cover file a music session embeds.

Adds `sessions.music_cover_max_size`: "500kb", "1mb", "2mb", "5mb", "10mb" or
"unlimited". VARCHAR, validated app-side by MusicCoverMaxSize. Every session
starts at "2mb", the limit every cover fetch had before this setting existed.

Revision ID: 0056_session_cover_max_size
Revises: 0055_session_music_cover_size
Create Date: 2026-11-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_session_cover_max_size"
down_revision: Union[str, None] = "0055_session_music_cover_size"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("music_cover_max_size", sa.String(), nullable=False, server_default="2mb"))


def downgrade() -> None:
    op.drop_column("sessions", "music_cover_max_size")
