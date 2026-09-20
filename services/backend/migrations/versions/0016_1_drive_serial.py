"""Add `serial` to drives.

Hardware serial (udev ID_SERIAL_SHORT), reported by the ripper at register
time. `hostname` is keyed to the srN slot baked into the compose file at
generation time, which the kernel/udev can silently reassign to a different
physical drive after a replug/reboot; comparing this field lets the register
endpoint detect that swap instead of quietly overwriting device_path.
Nullable — a small number of drives don't expose a serial at all.

Revision ID: 0016_1_drive_serial
Revises: 0016_notification_inbox
Create Date: 2026-07-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_1_drive_serial"
down_revision: Union[str, None] = "0016_notification_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drives", sa.Column("serial", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("drives", "serial")
