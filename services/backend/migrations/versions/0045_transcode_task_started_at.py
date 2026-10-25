"""Add started_at to transcode_tasks (D-130, D-202).

When the current attempt was claimed. `created_at` is apply time, so a task
that waited in the queue counted the wait as encode time in the UI's ETA and
"Took" label; `claim_heartbeat_at` is overwritten by every heartbeat. Set at
claim, nullable (rows claimed before this revision have none).

Revision ID: 0045_transcode_task_started_at
Revises: 0044_previously_ripped
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_transcode_task_started_at"
down_revision: Union[str, None] = "0044_previously_ripped"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transcode_tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("transcode_tasks", "started_at")
