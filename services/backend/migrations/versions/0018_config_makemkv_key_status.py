"""Add makemkv key-validity columns to the config singleton.

Disc-free makemkv key-validity reported by the ripper probe. All nullable,
default null (= never checked). See the 2026-06-12 makemkv-key-validity spec.

Revision ID: 0018_config_makemkv_key_status
Revises: 0017_config_metadata_provider
Create Date: 2026-06-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_config_makemkv_key_status"
down_revision: Union[str, None] = "0017_config_metadata_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("makemkv_key_valid", sa.Boolean(), nullable=True))
    op.add_column("config", sa.Column("makemkv_key_state", sa.String(), nullable=True))
    op.add_column("config", sa.Column("makemkv_key_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "makemkv_key_checked_at")
    op.drop_column("config", "makemkv_key_state")
    op.drop_column("config", "makemkv_key_valid")
