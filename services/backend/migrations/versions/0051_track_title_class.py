"""Scan facts and the Blu-ray title verdict on tracks (#705, D13).

Four nullable columns, no backfill: jobs scanned before this are dead, and a
stored scan re-read later classifies as all-PRIMARY. `title_class` is VARCHAR
validated by the app (`enum_column`), never a native enum type.

Revision ID: 0051_track_title_class
Revises: 0050_handbrake_settings
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_track_title_class"
down_revision = "0050_handbrake_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("source_file", "playlist_name", "title_class", "title_class_ref")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("tracks", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("tracks", name)
