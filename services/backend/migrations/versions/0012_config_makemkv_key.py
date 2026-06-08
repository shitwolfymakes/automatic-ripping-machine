"""Add `makemkv_key` to the config singleton.

Persists the operator's MakeMKV registration key as a Config setting,
editable from the UI, so rippers no longer depend on the `MAKEMKV_KEY`
env var (now a fallback) or the monthly beta-key forum scrape (last
resort). Nullable; empty preserves the existing env/scrape behaviour.

Revision ID: 0012_config_makemkv_key
Revises: 0011_plex_movie_track_token
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_config_makemkv_key"
down_revision: Union[str, None] = "0011_plex_movie_track_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("makemkv_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "makemkv_key")
