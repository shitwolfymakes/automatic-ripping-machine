"""First-run setup walkthrough state on the config singleton.

Revision ID: 0042_setup_state
Revises: 0041_virtual_drives
Create Date: 2026-10-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_setup_state"
down_revision: Union[str, None] = "0041_virtual_drives"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "setup_completed_at",
    "setup_progress",
    "setup_checklist_dismissed_at",
    "makemkv_key_checked_by_drive_id",
)

# An install already in use (admin password changed) must not see the
# first-run walkthrough after upgrading. A fresh DB has no config row yet at
# migration time, so the seeder creates it later with setup_completed_at NULL.
BACKFILL_SQL = (
    "UPDATE config SET setup_completed_at = now() "
    "WHERE EXISTS (SELECT 1 FROM users WHERE username = 'admin' AND password_must_change = false)"
)


def upgrade() -> None:
    op.add_column("config", sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "config",
        sa.Column("setup_progress", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("config", sa.Column("setup_checklist_dismissed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("config", sa.Column("makemkv_key_checked_by_drive_id", sa.String(), nullable=True))
    op.execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    for name in _COLUMNS:
        op.drop_column("config", name)
