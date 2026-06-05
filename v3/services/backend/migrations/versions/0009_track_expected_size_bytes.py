"""Track.expected_size_bytes — scan-time MakeMKV size estimate.

MakeMKV's scan emits per-title size in bytes (TINFO:t,11) — captured into
`ScanTitle.size_bytes` already; this column lets the JobDetail tracks
table render that estimate before the rip starts. Post-rip, the existing
`size_bytes` column carries the actual file size from disk.

Nullable BigInteger because BD main-feature titles routinely exceed the
INT max (2^31).

Revision ID: 0009_track_expected_size_bytes
Revises: 0008_transcode_task_cascade
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_track_expected_size_bytes"
down_revision: Union[str, None] = "0008_transcode_task_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("expected_size_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tracks", "expected_size_bytes")
