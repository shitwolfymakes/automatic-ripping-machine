"""Identification settings (spec 2026-10-14 §5.4).

Adds the per-media-type online-source lists, the job page's search provider
per type, the per-type auto-apply gates and the ARM community CRC64 database
switch to the config singleton, seeds the movie order and search providers
from the old `metadata_provider` choice (D-8), then drops that column.

Revision ID: 0045_identification_sources
Revises: 0044_previously_ripped
Create Date: 2026-10-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_identification_sources"
down_revision: Union[str, None] = "0044_previously_ripped"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "movie_sources",
    "music_sources",
    "search_provider_movie",
    "search_provider_tv",
    "search_provider_music",
    "movie_auto_apply",
    "music_auto_apply",
    "crc64service_enabled",
)


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column(
            "movie_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{tmdb,omdb}'::text[]"),
        ),
    )
    op.add_column(
        "config",
        sa.Column(
            "music_sources",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{musicbrainz}'::text[]"),
        ),
    )
    op.add_column(
        "config", sa.Column("search_provider_movie", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.add_column(
        "config", sa.Column("search_provider_tv", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.add_column(
        "config",
        sa.Column("search_provider_music", sa.String(), nullable=False, server_default=sa.text("'musicbrainz'")),
    )
    op.add_column("config", sa.Column("movie_auto_apply", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("config", sa.Column("music_auto_apply", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column(
        "config", sa.Column("crc64service_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    # D-8: no install changes behaviour on upgrade. The old choice leads the
    # movie order and stays the job page's movie search provider; the TV
    # search provider is the first episode source.
    op.execute(
        sa.text(
            "UPDATE config SET "
            "movie_sources = CASE WHEN metadata_provider = 'omdb' THEN '{omdb,tmdb}'::text[] "
            "ELSE '{tmdb,omdb}'::text[] END, "
            "search_provider_movie = CASE WHEN metadata_provider IN ('tmdb', 'omdb') THEN metadata_provider "
            "ELSE 'tmdb' END, "
            "search_provider_tv = COALESCE(episode_sources[1], 'tmdb')"
        )
    )
    op.drop_column("config", "metadata_provider")


def downgrade() -> None:
    op.add_column(
        "config", sa.Column("metadata_provider", sa.String(), nullable=False, server_default=sa.text("'tmdb'"))
    )
    op.execute(
        sa.text(
            "UPDATE config SET metadata_provider = CASE WHEN movie_sources[1] IN ('tmdb', 'omdb') "
            "THEN movie_sources[1] ELSE 'tmdb' END"
        )
    )
    for name in reversed(_COLUMNS):
        op.drop_column("config", name)
