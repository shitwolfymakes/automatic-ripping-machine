"""Add `tvdb_api_key` to the config singleton.

Persists the operator's TVDB v4 API key as a Config setting, editable
from the UI. Consumed by the metadata test-key endpoint (and, later, TVDB
episode matching). Nullable; empty means no TVDB key configured.

Revision ID: 0013_config_tvdb_key
Revises: 0012_config_makemkv_key
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_config_tvdb_key"
down_revision: Union[str, None] = "0012_config_makemkv_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("tvdb_api_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "tvdb_api_key")
