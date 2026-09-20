"""Add MakeMKV SDF (decryption data file) fields to the config singleton.

Operator toggle (makemkv_sdf_enabled, default on) plus two ripper-reported
status columns (state / checked_at). Pure additive, reversible. Mirrors
0021's community_keydb_fields pattern.

Revision ID: 0026_add_makemkv_sdf_columns
Revises: 0025_job_manual_pause
Create Date: 2026-06-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_add_makemkv_sdf_columns"
down_revision: Union[str, None] = "0025_job_manual_pause"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "config",
        sa.Column("makemkv_sdf_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("config", sa.Column("makemkv_sdf_state", sa.String(), nullable=True))
    op.add_column("config", sa.Column("makemkv_sdf_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "makemkv_sdf_checked_at")
    op.drop_column("config", "makemkv_sdf_state")
    op.drop_column("config", "makemkv_sdf_enabled")
