"""Persist heartbeat telemetry on transcode_tasks (D-242, D-248).

The heartbeat handler used to keep only progress_pct; the ETA, pass and
frame rate the transcoder reported reached the UI through the live WS event
alone, so a polling client or a card that mounted mid-encode never saw them.
Nullable, no backfill: the next heartbeat fills them in.

Revision ID: 0049_transcode_task_telemetry
Revises: 0048_drive_status_ripping
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_transcode_task_telemetry"
down_revision: Union[str, None] = "0048_drive_status_ripping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transcode_tasks", sa.Column("current_pass", sa.String(), nullable=True))
    op.add_column("transcode_tasks", sa.Column("eta_seconds", sa.Integer(), nullable=True))
    op.add_column("transcode_tasks", sa.Column("fps", sa.Float(), nullable=True))
    op.add_column("transcode_tasks", sa.Column("avg_fps", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("transcode_tasks", "avg_fps")
    op.drop_column("transcode_tasks", "fps")
    op.drop_column("transcode_tasks", "eta_seconds")
    op.drop_column("transcode_tasks", "current_pass")
