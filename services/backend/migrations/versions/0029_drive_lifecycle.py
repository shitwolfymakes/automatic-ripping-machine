"""drives: lifecycle + stable identity; config: scanner tunables (spec §1, §2)

Green-field: no backfill. Rows that predate this revision take the
server defaults (lifecycle=enrolled, present=true) — see the plan's
"Transitional state" note.

Revision ID: 0029_drive_lifecycle
Revises: 0028_user_role_disabled
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_drive_lifecycle"
down_revision: Union[str, None] = "0028_user_role_disabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("by_id_name", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("sysfs_port", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("identity_kind", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("lifecycle", sa.String(), nullable=False, server_default="enrolled"))
    op.add_column("drives", sa.Column("present", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("drives", sa.Column("vendor", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("model", sa.String(), nullable=True))
    op.add_column("drives", sa.Column("last_error", sa.String(), nullable=True))
    op.create_unique_constraint("uq_drives_by_id_name", "drives", ["by_id_name"])
    op.add_column("config", sa.Column("drive_scan_interval_seconds", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("config", sa.Column("drive_detected_prune_days", sa.Integer(), nullable=False, server_default="7"))


def downgrade() -> None:
    op.drop_column("config", "drive_detected_prune_days")
    op.drop_column("config", "drive_scan_interval_seconds")
    op.drop_constraint("uq_drives_by_id_name", "drives", type_="unique")
    for name in ("last_error", "model", "vendor", "present", "lifecycle", "identity_kind", "sysfs_port", "by_id_name"):
        op.drop_column("drives", name)
