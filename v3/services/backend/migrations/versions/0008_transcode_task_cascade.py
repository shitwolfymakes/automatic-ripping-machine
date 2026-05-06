"""Switch transcode_tasks.source_track_id FK from RESTRICT to CASCADE.

The original RESTRICT was a defensive choice ("don't delete a track
that's still referenced"), but it makes job deletion fail whenever the
job ever produced a transcode task — Postgres cascade-deletes don't
honour ordering across multiple FK chains, so the cascade from
`jobs → tracks` runs before (or in parallel with) the cascade from
`jobs → session_applications → transcode_tasks` and trips the
RESTRICT.

CASCADE matches the semantic the rest of the delete chain already
uses: when the job goes, every derivative row goes with it. The
transcode-task row is purely operational state; we don't need it
to survive the source track.

Revision ID: 0008_transcode_task_cascade
Revises: 0007_drive_media_status
Create Date: 2026-05-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_transcode_task_cascade"
down_revision: Union[str, None] = "0007_drive_media_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "transcode_tasks_source_track_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK_NAME, "transcode_tasks", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "transcode_tasks",
        "tracks",
        ["source_track_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, "transcode_tasks", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "transcode_tasks",
        "tracks",
        ["source_track_id"],
        ["id"],
        ondelete="RESTRICT",
    )
