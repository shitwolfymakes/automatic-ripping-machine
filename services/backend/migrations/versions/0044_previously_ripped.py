"""What to do with a disc ARM has already ripped (D-132).

Adds `config.on_previously_ripped` (VARCHAR, app-validated against
PreviouslyRippedAction; default `hold`), `drives.notice` (the drive card's
"ejected: already ripped" note), and subscribes the system in-app channel to
the new `rip.duplicate_rejected` event so a rejected disc shows up in the bell.

Revision ID: 0044_previously_ripped
Revises: 0043_setup_deferred
Create Date: 2026-10-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_previously_ripped"
down_revision: Union[str, None] = "0043_setup_deferred"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVENT = "rip.duplicate_rejected"


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("on_previously_ripped", sa.String(), nullable=False, server_default="hold"),
    )
    op.add_column("drives", sa.Column("notice", sa.String(), nullable=True))
    op.execute(
        f"""
        UPDATE notification_channels
        SET subscribed_events = array_append(subscribed_events, '{_EVENT}')
        WHERE id = 'ncl_inbox' AND NOT ('{_EVENT}' = ANY(subscribed_events))
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE notification_channels
        SET subscribed_events = array_remove(subscribed_events, '{_EVENT}')
        WHERE '{_EVENT}' = ANY(subscribed_events)
        """
    )
    op.drop_column("drives", "notice")
    op.drop_column("config", "on_previously_ripped")
