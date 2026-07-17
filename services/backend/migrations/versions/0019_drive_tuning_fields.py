"""Add operator-tunable drive fields.

Seven nullable tuning columns the UI has live controls for: rip_speed,
drive_mode (VARCHAR enum auto/manual), uhd_capable, prescan_cache_mb,
prescan_timeout, prescan_retries, disc_enum_timeout. NULL = unset; the ripper
uses its built-in default. Pure additive column-add, reversible.

Revision ID: 0019_drive_tuning_fields
Revises: 0018_config_makemkv_key_status
Create Date: 2026-06-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_drive_tuning_fields"
down_revision: Union[str, None] = "0018_config_makemkv_key_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("rip_speed", sa.Integer(), nullable=True))
    op.add_column("drives", sa.Column("drive_mode", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("uhd_capable", sa.Boolean(), nullable=True))
    op.add_column("drives", sa.Column("prescan_cache_mb", sa.Integer(), nullable=True))
    op.add_column("drives", sa.Column("prescan_timeout", sa.Integer(), nullable=True))
    op.add_column("drives", sa.Column("prescan_retries", sa.Integer(), nullable=True))
    op.add_column("drives", sa.Column("disc_enum_timeout", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("drives", "disc_enum_timeout")
    op.drop_column("drives", "prescan_retries")
    op.drop_column("drives", "prescan_timeout")
    op.drop_column("drives", "prescan_cache_mb")
    op.drop_column("drives", "uhd_capable")
    op.drop_column("drives", "drive_mode")
    op.drop_column("drives", "rip_speed")
