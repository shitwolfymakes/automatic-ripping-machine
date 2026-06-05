"""Add config.auto_rip_on_insert master switch.

Default `true` to preserve current behaviour: a freshly inserted disc kicks
off scan/identify/rip automatically. When toggled off in the Config UI, the
ripper ignores DISC_OK transitions, leaving the disc in the tray until the
user kicks the rip off explicitly via the manual-rip form.

Revision ID: 0004_auto_rip_on_insert
Revises: 0003_notifications
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_auto_rip_on_insert"
down_revision: Union[str, None] = "0003_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("auto_rip_on_insert", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("config", "auto_rip_on_insert")
