"""Job poster columns.

`poster_url` is set at identify time from TMDB / OMDB / Cover Art Archive;
`poster_url_manual` is a user override editable from the UI. UI prefers
`poster_url_manual` if set, otherwise falls back to `poster_url`.

Both nullable strings — no length limit since registries push CDN paths
that can be over 256 chars (TMDB's full hashed URL) and we have no upside
from truncating.

Revision ID: 0005_job_poster_columns
Revises: 0004_auto_rip_on_insert
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_job_poster_columns"
down_revision: Union[str, None] = "0004_auto_rip_on_insert"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("poster_url", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("poster_url_manual", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "poster_url_manual")
    op.drop_column("jobs", "poster_url")
