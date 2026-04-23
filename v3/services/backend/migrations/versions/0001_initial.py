"""initial schema — all phase-1 tables

Enum-valued columns are stored as VARCHAR; the StrEnum classes in
packages/arm_common/arm_common/enums.py are the source of truth and validation
runs in the SQLModel/Pydantic layer. See 04-data-model.md § Conventions.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # users — created first so downstream FKs can reference it.
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column(
            "password_must_change",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # config (singleton — id=1)
    op.create_table(
        "config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("tmdb_api_key", sa.String(), nullable=True),
        sa.Column("omdb_api_key", sa.String(), nullable=True),
        sa.Column("musicbrainz_user_agent", sa.String(), nullable=True),
        sa.Column(
            "auto_transcode_on_idle",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "block_on_miss",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "default_retention_policy",
            sa.String(),
            nullable=False,
            server_default="prune_after_session",
        ),
        sa.Column(
            "notification_apprise_urls",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("session_signing_key", sa.LargeBinary(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # drives — default_session_id FK added after sessions table exists.
    op.create_table(
        "drives",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("hostname", sa.String(), nullable=False, unique=True),
        sa.Column("device_path", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="online"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rip_params_json",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("default_session_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drives_hostname", "drives", ["hostname"], unique=True)

    # jobs
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "drive_id",
            sa.String(),
            sa.ForeignKey("drives.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("disc_type", sa.String(), nullable=False),
        sa.Column("disc_fingerprint", sa.String(), nullable=True),
        sa.Column("disc_fingerprint_algo", sa.String(), nullable=True),
        sa.Column("aacs_disc_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            _jsonb(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("resumed_from_crash", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ripped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_drive_id", "jobs", ["drive_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    # tracks
    op.create_table(
        "tracks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("role_source", sa.String(), nullable=True),
        sa.Column("edition", sa.String(), nullable=True),
        sa.Column("expected_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_path", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tracks_job_id", "tracks", ["job_id"])

    # rip_presets
    op.create_table(
        "rip_presets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("track_selection", sa.String(), nullable=False),
        sa.Column("identification_mode", sa.String(), nullable=False),
        sa.Column("output_mode", sa.String(), nullable=False),
        sa.Column("track_filters_json", _jsonb(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # transcode_presets
    op.create_table(
        "transcode_presets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("preset_ref", sa.String(), nullable=True),
        sa.Column("preset_json", _jsonb(), nullable=True),
        sa.Column("container", sa.String(), nullable=False),
        sa.Column("hw_preference", sa.String(), nullable=True),
        sa.Column("extra_args", sa.String(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "rip_preset_id",
            sa.String(),
            sa.ForeignKey("rip_presets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "transcode_preset_id",
            sa.String(),
            sa.ForeignKey("transcode_presets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("output_path_template", sa.String(), nullable=False),
        sa.Column("overrides_json", _jsonb(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # now that sessions exists, bolt the FK onto drives.default_session_id
    op.create_foreign_key(
        "fk_drives_default_session_id",
        source_table="drives",
        referent_table="sessions",
        local_cols=["default_session_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # session_applications
    op.create_table(
        "session_applications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("overrides_json", _jsonb(), nullable=True),
        sa.Column("overwrite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_applications_session_id", "session_applications", ["session_id"])
    op.create_index("ix_session_applications_job_id", "session_applications", ["job_id"])

    # transcode_tasks
    op.create_table(
        "transcode_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_application_id",
            sa.String(),
            sa.ForeignKey("session_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_track_id",
            sa.String(),
            sa.ForeignKey("tracks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("claim_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_path", sa.String(), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_transcode_tasks_session_application_id",
        "transcode_tasks",
        ["session_application_id"],
    )
    op.create_index(
        "ix_transcode_tasks_status_heartbeat",
        "transcode_tasks",
        ["status", "claim_heartbeat_at"],
    )
    # Partial unique index: only one live task can own a given output_path.
    op.create_index(
        "uq_transcode_tasks_output_path_live",
        "transcode_tasks",
        ["output_path"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'in_progress', 'done')"),
    )

    # gpus
    op.create_table(
        "gpus",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("vendor", sa.String(), nullable=False),
        sa.Column("device_path", sa.String(), nullable=False),
        sa.Column(
            "encoder_kinds",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="available"),
        sa.Column(
            "claimed_by_task_id",
            sa.String(),
            sa.ForeignKey("transcode_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # events
    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "track_id",
            sa.String(),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "session_application_id",
            sa.String(),
            sa.ForeignKey("session_applications.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("payload_json", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_emitted_at", "events", ["emitted_at"])
    op.create_index("ix_events_job_id", "events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_events_job_id", table_name="events")
    op.drop_index("ix_events_emitted_at", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_table("events")

    op.drop_table("gpus")

    op.drop_index("uq_transcode_tasks_output_path_live", table_name="transcode_tasks")
    op.drop_index("ix_transcode_tasks_status_heartbeat", table_name="transcode_tasks")
    op.drop_index("ix_transcode_tasks_session_application_id", table_name="transcode_tasks")
    op.drop_table("transcode_tasks")

    op.drop_index("ix_session_applications_job_id", table_name="session_applications")
    op.drop_index("ix_session_applications_session_id", table_name="session_applications")
    op.drop_table("session_applications")

    op.drop_constraint("fk_drives_default_session_id", "drives", type_="foreignkey")

    op.drop_table("sessions")
    op.drop_table("transcode_presets")
    op.drop_table("rip_presets")

    op.drop_index("ix_tracks_job_id", table_name="tracks")
    op.drop_table("tracks")

    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_drive_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_drives_hostname", table_name="drives")
    op.drop_table("drives")

    op.drop_table("config")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
