"""initial: enums + drives + jobs

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DISC_TYPE_VALUES = ("dvd", "bluray", "cd", "data", "unknown")
DRIVE_STATUS_VALUES = ("online", "offline", "ripping", "error")
JOB_STATUS_VALUES = (
    "created",
    "awaiting_user_id",
    "identified",
    "ripping",
    "ripped",
    "ripped_partial",
    "abandoned",
    "failed",
)
TRACK_STATUS_VALUES = ("queued", "in_progress", "done", "failed")


def upgrade() -> None:
    disc_type = postgresql.ENUM(*DISC_TYPE_VALUES, name="disc_type", create_type=False)
    drive_status = postgresql.ENUM(*DRIVE_STATUS_VALUES, name="drive_status", create_type=False)
    job_status = postgresql.ENUM(*JOB_STATUS_VALUES, name="job_status", create_type=False)
    track_status = postgresql.ENUM(*TRACK_STATUS_VALUES, name="track_status", create_type=False)

    bind = op.get_bind()
    for enum in (disc_type, drive_status, job_status, track_status):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "drives",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("hostname", sa.String(), nullable=False, unique=True),
        sa.Column("device_path", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("status", drive_status, nullable=False, server_default="online"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rip_params_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("default_session_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drives_hostname", "drives", ["hostname"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "drive_id",
            sa.String(),
            sa.ForeignKey("drives.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("disc_type", disc_type, nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", job_status, nullable=False, server_default="created"),
        sa.Column("resumed_from_crash", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ripped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_drive_id", "jobs", ["drive_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_drive_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_drives_hostname", table_name="drives")
    op.drop_table("drives")

    bind = op.get_bind()
    for name in ("track_status", "job_status", "drive_status", "disc_type"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
