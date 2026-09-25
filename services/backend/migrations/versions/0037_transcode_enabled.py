"""Runtime transcode toggle (no-transcode mode).

`config.transcode_enabled` is the operator's runtime switch for encode work
(Settings > Transcoding). Nullable so the seeder can distinguish an upgrade
row (NULL, backfilled to true on next boot) from an operator choice; the
server_default covers rows inserted after upgrade. Deployment capability
(ARM_TRANSCODE_CAPABLE) is env, not a column: it describes the install, not
an operator decision.

Revision ID: 0037_transcode_enabled
Revises: 0036_gpu_inventory_alignment
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_transcode_enabled"
down_revision: Union[str, None] = "0036_gpu_inventory_alignment"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("transcode_enabled", sa.Boolean(), nullable=True, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("config", "transcode_enabled")
