"""add hosts table

Revision ID: 0027_add_host_table
Revises: 0026_add_makemkv_sdf_columns
Create Date: 2026-07-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_add_host_table"
down_revision: Union[str, None] = "0026_add_makemkv_sdf_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hosts",
        sa.Column("hostname", sa.String(), primary_key=True, nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False, server_default=""),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hosts_last_seen", "hosts", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_hosts_last_seen", table_name="hosts")
    op.drop_table("hosts")
