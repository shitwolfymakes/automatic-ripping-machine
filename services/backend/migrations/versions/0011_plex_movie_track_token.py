"""Add `Track {track}` to the three built-in Movie → Plex session templates.

The Plex movie sessions originally shipped without `{track}` in their
output_path_template. Main-feature rip presets normally pick one video
title, but if the rip stage keeps multiple titles (or a user swaps the
rip preset to one that does), every track resolves to the same path and
the apply step has to refuse the whole session as a duplicate-in-request
collision. Adding `Track {track}` makes the default safe regardless of
how many tracks the rip preset retains.

Conservative on user-modified built-ins: only updates rows that still
carry the exact original template, so a hand-edited copy on someone's
DB is left alone.

Revision ID: 0011_plex_movie_track_token
Revises: 0010_fix_passthrough_mkv_preset
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_plex_movie_track_token"
down_revision: Union[str, None] = "0010_fix_passthrough_mkv_preset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = "{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}"
_NEW = "{title} ({year})/{title} ({year}) - Track {track} - {transcode_slug}.{ext}"

_SESSION_IDS = (
    "ses_builtin_movie_plex_1080p",
    "ses_builtin_movie_plex_1080p_gpu",
    "ses_builtin_movie_plex_2160p",
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sessions
               SET output_path_template = :new
             WHERE id IN :ids
               AND output_path_template = :old
            """
        ).bindparams(
            sa.bindparam("ids", expanding=True),
            new=_NEW,
            old=_OLD,
            ids=list(_SESSION_IDS),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sessions
               SET output_path_template = :old
             WHERE id IN :ids
               AND output_path_template = :new
            """
        ).bindparams(
            sa.bindparam("ids", expanding=True),
            new=_NEW,
            old=_OLD,
            ids=list(_SESSION_IDS),
        )
    )
