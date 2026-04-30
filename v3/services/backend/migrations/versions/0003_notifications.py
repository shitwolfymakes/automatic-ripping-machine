"""Phase 11 — notifications.

Adds two columns:

- `events.notified_at` — watermark used by the NotificationDispatcher to
  pick up unsent notifiable events. Backfilled to `emitted_at` on existing
  rows so deploying Phase 11 against a long-running DB does not flood
  every Apprise URL with the historical event log.
- `config.notifications_enabled` — explicit master toggle. Default False
  so notifications stay off until the user actively enables them in the UI,
  even if URLs are already saved.

Revision ID: 0003_notifications
Revises: 0002_transcode_preset_codec
Create Date: 2026-04-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_notifications"
down_revision: Union[str, None] = "0002_transcode_preset_codec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_events_notified_at", "events", ["notified_at"])
    op.execute("UPDATE events SET notified_at = emitted_at WHERE notified_at IS NULL")
    op.add_column(
        "config",
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("config", "notifications_enabled")
    op.drop_index("ix_events_notified_at", table_name="events")
    op.drop_column("events", "notified_at")
