"""Encoder-first presets.

transcode_presets.encoder (an arm_common.encoders catalog id) replaces
codec + hw_preference; gpus gains probed_at/probe_error and encoder_kinds is
reset so nothing is eligible until the backend's first per-device probe.

Revision ID: 0038_encoder_first
Revises: 0037_transcode_enabled
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_encoder_first"
down_revision: Union[str, None] = "0037_transcode_enabled"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "transcode_presets",
        sa.Column("encoder", sa.String(), nullable=False, server_default=sa.text("'preset'")),
    )
    op.execute("""
        UPDATE transcode_presets SET encoder = CASE
            WHEN tool <> 'handbrake' OR codec IS NULL THEN 'preset'
            WHEN hw_preference = 'cpu_only' THEN 'cpu_' || codec
            ELSE 'any_' || codec
        END
    """)
    op.drop_column("transcode_presets", "hw_preference")
    op.drop_column("transcode_presets", "codec")
    op.add_column("gpus", sa.Column("probed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gpus", sa.Column("probe_error", sa.String(), nullable=True))
    op.execute("UPDATE gpus SET encoder_kinds = '{}'")


def downgrade() -> None:
    op.drop_column("gpus", "probe_error")
    op.drop_column("gpus", "probed_at")
    op.add_column("transcode_presets", sa.Column("codec", sa.String(), nullable=True))
    op.add_column("transcode_presets", sa.Column("hw_preference", sa.String(), nullable=True))
    op.execute("""
        UPDATE transcode_presets SET
            codec = CASE WHEN encoder = 'preset' THEN NULL ELSE split_part(encoder, '_', 2) END,
            hw_preference = CASE WHEN encoder LIKE 'cpu\\_%' ESCAPE '\\' THEN 'cpu_only' ELSE NULL END
    """)
    op.drop_column("transcode_presets", "encoder")
