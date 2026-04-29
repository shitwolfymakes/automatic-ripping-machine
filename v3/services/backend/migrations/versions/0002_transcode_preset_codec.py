"""transcode_presets: add `codec` column

Phase 7b uses `codec` as the explicit predicate for GPU dispatch
(`Gpu.encoder_kinds @> ARRAY[preset.codec]`) so the dispatcher does not
have to regex-mine `preset_ref`. Backfill seeded rows by matching the
existing preset_ref strings; user-created presets land with NULL and
fall through to CPU until updated.

Revision ID: 0002_transcode_preset_codec
Revises: 0001_initial
Create Date: 2026-04-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_transcode_preset_codec"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transcode_presets", sa.Column("codec", sa.String(), nullable=True))
    # Backfill seeded presets: preset_ref name carries the codec verbatim.
    op.execute(
        "UPDATE transcode_presets SET codec = 'h265' WHERE preset_ref ILIKE '%h.265%' OR preset_ref ILIKE '%hevc%'"
    )
    op.execute(
        "UPDATE transcode_presets SET codec = 'h264' WHERE preset_ref ILIKE '%h.264%' OR preset_ref ILIKE '%avc%'"
    )


def downgrade() -> None:
    op.drop_column("transcode_presets", "codec")
