"""Add operator-editable per-track fields.

Per-track identity (title/year/imdb_id/poster_url/video_type/episode_number/
episode_name, null=inherit job-level) + control (excluded omits from transcode
output; custom_filename overrides the rendered name). Pure additive, reversible.

Revision ID: 0020_track_operator_fields
Revises: 0019_drive_tuning_fields
Create Date: 2026-06-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_track_operator_fields"
down_revision: Union[str, None] = "0019_drive_tuning_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("title", sa.String(), nullable=True))
    op.add_column("tracks", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("tracks", sa.Column("imdb_id", sa.String(), nullable=True))
    op.add_column("tracks", sa.Column("poster_url", sa.String(), nullable=True))
    op.add_column("tracks", sa.Column("video_type", sa.String(), nullable=True))
    op.add_column("tracks", sa.Column("episode_number", sa.Integer(), nullable=True))
    op.add_column("tracks", sa.Column("episode_name", sa.String(), nullable=True))
    op.add_column(
        "tracks",
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("tracks", sa.Column("custom_filename", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("tracks", "custom_filename")
    op.drop_column("tracks", "excluded")
    op.drop_column("tracks", "episode_name")
    op.drop_column("tracks", "episode_number")
    op.drop_column("tracks", "video_type")
    op.drop_column("tracks", "poster_url")
    op.drop_column("tracks", "imdb_id")
    op.drop_column("tracks", "year")
    op.drop_column("tracks", "title")
