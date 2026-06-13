"""Add `metadata_provider` to the config singleton.

The persisted metadata provider for the identify flow (search + detail).
Default `tmdb` — free, effectively unlimited, richer than OMDb. Validated
app-side to {tmdb, omdb}; tvdb/makemkv are key-test-only, not search
providers.

Revision ID: 0017_config_metadata_provider
Revises: 0016_notification_inbox
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_config_metadata_provider"
down_revision: Union[str, None] = "0016_notification_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("metadata_provider", sa.String(), nullable=False, server_default=sa.text("'tmdb'")),
    )


def downgrade() -> None:
    op.drop_column("config", "metadata_provider")
