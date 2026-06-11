"""In-app notification inbox table + seed the inapp bell channel.

Creates `notification_inbox` (UI bell rows with seen/cleared state) and
seeds the single system inapp channel `ncl_inbox` (idempotent) so the bell
works on existing DBs. The channel table itself is unchanged — `inapp` is
just a new VARCHAR `type` value.

Revision ID: 0016_notification_inbox
Revises: 0015_notification_channels
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_notification_inbox"
down_revision: Union[str, None] = "0015_notification_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with DEFAULT_INBOX_EVENT_TYPES in notification_dispatcher.py.
_DEFAULT_INBOX_EVENTS = [
    "rip.completed",
    "rip.failed",
    "rip.needs_user_input",
    "session.completed",
    "session.failed",
]


def upgrade() -> None:
    op.create_table(
        "notification_inbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "channel_id", sa.String(), sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cleared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_notification_inbox_created_at", "notification_inbox", ["created_at"])

    # Seed the system inapp channel (idempotent).
    events_array = "ARRAY[" + ",".join(f"'{e}'" for e in _DEFAULT_INBOX_EVENTS) + "]::text[]"
    op.execute(
        f"""
        INSERT INTO notification_channels
            (id, type, name, enabled, config, subscribed_events, templates, created_at)
        SELECT
            'ncl_inbox', 'inapp', 'In-app notifications', true,
            '{{"type":"inapp"}}'::jsonb, {events_array}, '{{}}'::jsonb, now()
        WHERE NOT EXISTS (SELECT 1 FROM notification_channels WHERE id = 'ncl_inbox')
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM notification_channels WHERE id = 'ncl_inbox'")
    op.drop_index("ix_notification_inbox_created_at", table_name="notification_inbox")
    op.drop_table("notification_inbox")
