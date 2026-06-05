"""Fix the built-in `tpr_builtin_passthrough_mkv` preset.

The built-in shipped with `tool='handbrake', preset_ref='Matroska Passthrough'`
which was wrong — HandBrake doesn't have a passthrough preset, so every
Movie → Archive MKV transcode failed with `HandBrakeCLI exited rc=2` and
the preset list dumped to stderr. The right expression is
`tool='none', preset_ref=NULL`, which routes through `transcode_none`
(file rename onto /media). This migration corrects existing rows in
place; the seeder ships the same values for fresh installs.

Conservative on user-modified built-ins: only updates rows that still
carry the broken values, so a hand-edited copy on someone's DB is left
alone.

Revision ID: 0010_fix_passthrough_mkv_preset
Revises: 0009_track_expected_size_bytes
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_fix_passthrough_mkv_preset"
down_revision: Union[str, None] = "0009_track_expected_size_bytes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE transcode_presets
               SET tool = 'none',
                   preset_ref = NULL
             WHERE id = 'tpr_builtin_passthrough_mkv'
               AND tool = 'handbrake'
               AND preset_ref = 'Matroska Passthrough'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE transcode_presets
               SET tool = 'handbrake',
                   preset_ref = 'Matroska Passthrough'
             WHERE id = 'tpr_builtin_passthrough_mkv'
               AND tool = 'none'
               AND preset_ref IS NULL
            """
        )
    )
