"""Job identity columns: media_type, season, pending_session_id.

Step 2 of docs/plans/AUTOMATION_GAP_ANALYSIS.md (§3.4): facts that drive
routing, naming or queries move out of the free-form metadata_json bag into
real columns.

- media_type — the identified kind (movie/tv/music/data/iso), set at
  identify from the provider result, correctable at resolve. VARCHAR +
  app-layer validation; never a Postgres enum.
- season — user-supplied TV season (G-14: the {season} naming token reads
  this column now).
- pending_session_id — the explicit per-rip session choice, previously a
  metadata key. FK → sessions.id ON DELETE SET NULL: a deleted session must
  not strand the job (the routed-session resolver falls back).

Data lift (PostgreSQL only — the tooling that runs migrations elsewhere has
no legacy rows):
- pending_session_id is copied from the metadata key where that id still
  resolves to a session (the FK would reject the rest); the metadata mirror
  is left in place — both UIs still read it until the JobMetadata schema
  migration removes it.
- season / disc metadata keys are lifted into season / disc_number where
  numeric and the column is unfilled, and the loose keys are dropped so the
  naming tokens and the columns can no longer disagree (G-14).

Downgrade drops the columns; lifted-and-dropped season/disc keys are not
restored to metadata_json.

Revision ID: 0030_job_identity_columns
Revises: 0029_thediscdb
Create Date: 2026-09-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_job_identity_columns"
down_revision: Union[str, None] = "0029_thediscdb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("media_type", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("season", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("pending_session_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_pending_session_id",
        "jobs",
        "sessions",
        ["pending_session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # metadata_json is a JSON (not JSONB) column: `->>` works directly, but
    # key deletion needs a jsonb round-trip.
    bind.execute(
        sa.text(
            """
            UPDATE jobs
               SET pending_session_id = metadata_json->>'pending_session_id'
             WHERE metadata_json->>'pending_session_id' IS NOT NULL
               AND EXISTS (
                     SELECT 1 FROM sessions s
                      WHERE s.id = metadata_json->>'pending_session_id'
                   )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE jobs
               SET season = (metadata_json->>'season')::int,
                   metadata_json = (metadata_json::jsonb - 'season')::json
             WHERE season IS NULL
               AND metadata_json->>'season' ~ '^[0-9]+$'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE jobs
               SET disc_number = COALESCE(disc_number, (metadata_json->>'disc')::int),
                   metadata_json = (metadata_json::jsonb - 'disc')::json
             WHERE metadata_json->>'disc' ~ '^[0-9]+$'
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_pending_session_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "pending_session_id")
    op.drop_column("jobs", "season")
    op.drop_column("jobs", "media_type")
