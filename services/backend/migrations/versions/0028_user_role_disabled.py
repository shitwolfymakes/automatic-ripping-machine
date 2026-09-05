"""users: role + disabled for the fixed admin/guest model

Revision ID: 0028_user_role_disabled
Revises: 0026_add_makemkv_sdf_columns
Create Date: 2026-07-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_user_role_disabled"
down_revision: Union[str, None] = "0026_add_makemkv_sdf_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(), nullable=False, server_default="admin"))
    op.add_column("users", sa.Column("disabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "disabled")
    op.drop_column("users", "role")
