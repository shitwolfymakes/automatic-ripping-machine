"""Session routing table (gap analysis G-02/G-17).

Adds `session_routes`: config-level `(media_type, disc_type) -> session_id`
rules consulted by `resolve_routed_session_id` behind the per-rip pending
choice and the per-drive default. `disc_type` is nullable and means
"wildcard for this media_type" (matches any disc_type not covered by a more
specific row). Plain `create_table`, VARCHAR enum columns validated in the
app layer (`arm_common.models._columns.enum_column`) — no Postgres
`CREATE TYPE` per project convention.

FK `session_id -> sessions.id` is `ON DELETE CASCADE`: a route row is pure
config (it has no history or audit value of its own once its target session
is gone), so cascading the delete is safe and avoids leaving an orphaned
route pointing at nothing.

Unique constraint on `(media_type, disc_type)`. Plain Postgres unique
constraints treat NULL as distinct from every other NULL, which would allow
more than one wildcard (`disc_type IS NULL`) row per `media_type` — not what
we want, since the resolver picks the first wildcard match arbitrarily.
SQLAlchemy 2.0.49 (pinned in uv.lock; `postgresql_nulls_not_distinct` landed
in 2.0.20) supports the modern Postgres 15+ `NULLS NOT DISTINCT` clause via
the `postgresql_nulls_not_distinct=True` table/constraint option, so this
migration uses that instead of relying on router-side enforcement: the
database itself now rejects a second `(media_type, NULL)` row for the same
media_type, which is a stronger guarantee than an app-layer check that a
future write path could bypass.

Downgrade drops the table.

Revision ID: 0034_session_routes
Revises: 0033_drop_metadata_mirrors
Create Date: 2026-09-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_session_routes"
down_revision: Union[str, None] = "0033_drop_metadata_mirrors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_routes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("disc_type", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "media_type",
            "disc_type",
            name="uq_session_routes_media_disc",
            postgresql_nulls_not_distinct=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("session_routes")
