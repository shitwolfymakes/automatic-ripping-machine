"""Merge the identification line (0045_identification_sources) with the S4 sweep line (0045-0048).

Both lines branched from 0044_previously_ripped. Neither touches the other's
tables, so the merge carries no DDL; it only gives ``alembic upgrade head`` a
single head again.

Revision ID: 0049_merge_identification_and_s4
Revises: 0045_identification_sources, 0048_transcode_task_telemetry
Create Date: 2026-10-25
"""

from typing import Sequence, Union

revision: str = "0049_merge_identification_and_s4"
down_revision: Union[str, Sequence[str], None] = ("0045_identification_sources", "0048_transcode_task_telemetry")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
