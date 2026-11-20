"""Minimum title length as operator config (#647).

`config.min_title_length_seconds` is the shortest title the ripper's scan
lists and its rip writes, replacing the ripper's ARM_MIN_LENGTH_SECONDS env
baseline. The column is added without a default so existing rows stay NULL:
the config seeder fills them once from that env value (the way
max_parallel_transcodes moved from env to config). The default of 120
(MakeMKV's own) is set afterwards and applies to rows inserted later.

Revision ID: 0050_config_min_title_length
Revises: 0049_transcode_task_telemetry
Create Date: 2026-11-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050_config_min_title_length"
down_revision: Union[str, None] = "0049_transcode_task_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config", sa.Column("min_title_length_seconds", sa.Integer(), nullable=True))
    op.alter_column("config", "min_title_length_seconds", server_default="120")


def downgrade() -> None:
    op.drop_column("config", "min_title_length_seconds")
