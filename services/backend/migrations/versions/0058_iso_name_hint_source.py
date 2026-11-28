"""iso_name joins the disc-hint sources, on by default

Revision ID: 0058_iso_name_hint_source
Revises: 0057_tick_one_version
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058_iso_name_hint_source"
down_revision: Union[str, None] = "0057_tick_one_version"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.alter_column(
        "config",
        "disc_hint_sources",
        server_default=sa.text("'{bd_title,iso_name,label}'::text[]"),
    )
    # The setting is a set: an install that never listed the new source gets it on.
    op.execute(
        "UPDATE config SET disc_hint_sources = array_append(disc_hint_sources, 'iso_name') "
        "WHERE NOT ('iso_name' = ANY(disc_hint_sources))"
    )


def downgrade() -> None:
    op.execute("UPDATE config SET disc_hint_sources = array_remove(disc_hint_sources, 'iso_name')")
    op.alter_column(
        "config",
        "disc_hint_sources",
        server_default=sa.text("'{bd_title,label}'::text[]"),
    )
