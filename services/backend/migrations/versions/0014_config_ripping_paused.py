"""Add `ripping_paused` to the config singleton.

Global pause switch: when true the backend refuses to create NEW rip jobs
(identify / manual-trigger return 409). In-flight rips are unaffected (stopping
them needs a ripper WS command — deferred). Default false.

Revision ID: 0014_config_ripping_paused
Revises: 0013_config_tvdb_key
Create Date: 2026-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_config_ripping_paused"
down_revision: Union[str, None] = "0013_config_tvdb_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("ripping_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("config", "ripping_paused")
