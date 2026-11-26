"""Store HandBrake settings in place of preset_json; add handbrake_schemas.

transcode_presets.preset_json (an inline HandBrake preset) is replaced by
handbrake_settings, a nullable JSONB of common and per-encoder settings.
handbrake_schemas holds the schema dumps transcoder images report, keyed by
content hash. VARCHAR only; no enums.

Downgrade re-adds preset_json (nullable, empty) and drops the new column and
table: settings stored in handbrake_settings are LOST on downgrade.

Revision ID: 0050_handbrake_settings
Revises: 0049_transcode_task_telemetry
Create Date: 2026-11-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_handbrake_settings"
down_revision: Union[str, None] = "0049_transcode_task_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("transcode_presets", "preset_json")
    op.add_column("transcode_presets", sa.Column("handbrake_settings", postgresql.JSONB(), nullable=True))
    op.create_table(
        "handbrake_schemas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_hash", sa.String(), nullable=False, unique=True),
        sa.Column("handbrake_tag", sa.String(), nullable=False),
        sa.Column("preset_version", sa.String(), nullable=False),
        sa.Column("image_ref", sa.String(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("handbrake_schemas")
    op.drop_column("transcode_presets", "handbrake_settings")
    op.add_column("transcode_presets", sa.Column("preset_json", postgresql.JSONB(), nullable=True))
