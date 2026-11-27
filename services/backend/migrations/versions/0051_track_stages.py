"""Add `track_stages`: one track's copy from /raw into staging (#708, D7).

One row per track (unique `track_id`), created at session fan-out for a
non-passthrough preset and worked by the backend's stager. `status` is a
plain VARCHAR validated in the app layer (`arm_common.models._columns.enum_column`);
no Postgres `CREATE TYPE`, per project convention. Both FKs are
`ON DELETE CASCADE`: a stage row is bookkeeping for its track, so deleting
the track or its job takes it along.

Downgrade drops the table.

Revision ID: 0051_track_stages
Revises: 0050_handbrake_settings
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_track_stages"
down_revision: Union[str, None] = "0050_handbrake_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "track_stages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("track_id", sa.String(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("source_size", sa.BigInteger(), nullable=True),
        sa.Column("source_mtime_ns", sa.BigInteger(), nullable=True),
        sa.Column("dest_path", sa.String(), nullable=False),
        sa.Column("bytes_durable", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("linked", sa.Boolean(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_track_stages_track_id", "track_stages", ["track_id"], unique=True)
    op.create_index("ix_track_stages_job_id", "track_stages", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_track_stages_job_id", table_name="track_stages")
    op.drop_index("ix_track_stages_track_id", table_name="track_stages")
    op.drop_table("track_stages")
