"""Notification channels + dispatch log; import the flat apprise URL list.

Creates `notification_channels` and `notification_dispatch_log`. Imports
any existing `config.notification_apprise_urls` into one channel per URL
(name "Imported N", enabled = config.notifications_enabled, subscribed to
every notifiable event). The flat `config.notification_apprise_urls`
column is LEFT IN PLACE (read-stopped by the dispatcher; dropped later).

Revision ID: 0015_notification_channels
Revises: 0014_config_ripping_paused
Create Date: 2026-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_notification_channels"
down_revision: Union[str, None] = "0014_config_ripping_paused"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with NOTIFIABLE_EVENT_TYPES in notification_dispatcher.py.
_NOTIFIABLE = [
    "rip.completed",
    "rip.failed",
    "rip.partial",
    "session.completed",
    "session.failed",
    "session.partial",
]


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "subscribed_events",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("templates", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "notification_dispatch_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "channel_id",
            sa.String(),
            sa.ForeignKey("notification_channels.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notification_dispatch_log_channel_id", "notification_dispatch_log", ["channel_id"])
    op.create_index("ix_notification_dispatch_log_created_at", "notification_dispatch_log", ["created_at"])

    # Import the flat apprise URL list into one channel per URL.
    events_array = "ARRAY[" + ",".join(f"'{e}'" for e in _NOTIFIABLE) + "]"
    op.execute(
        f"""
        INSERT INTO notification_channels
            (id, type, name, enabled, config, subscribed_events, templates, created_at)
        SELECT
            'ncl_' || substr(md5(random()::text || u.url || u.ord::text), 1, 24),
            'apprise',
            'Imported ' || u.ord::text,
            c.notifications_enabled,
            jsonb_build_object('type', 'apprise', 'url', u.url),
            {events_array},
            '{{}}'::jsonb,
            now()
        FROM config c
        CROSS JOIN LATERAL unnest(c.notification_apprise_urls)
            WITH ORDINALITY AS u(url, ord)
        WHERE c.id = 1
          AND c.notification_apprise_urls IS NOT NULL
          AND array_length(c.notification_apprise_urls, 1) > 0
        """
    )


def downgrade() -> None:
    op.drop_index("ix_notification_dispatch_log_created_at", table_name="notification_dispatch_log")
    op.drop_index("ix_notification_dispatch_log_channel_id", table_name="notification_dispatch_log")
    op.drop_table("notification_dispatch_log")
    op.drop_table("notification_channels")
