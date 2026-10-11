"""Server-wide "Finish later" for the first-run setup walkthrough.

Revision ID: 0043_setup_deferred
Revises: 0042_setup_state
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_setup_deferred"
down_revision: Union[str, None] = "0042_setup_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("setup_deferred_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("config", "setup_deferred_at")
