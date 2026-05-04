"""Multi-fingerprint table for jobs; drop singleton columns.

A disc can carry several fingerprints — DVDs CRC64 + volume-label-as-weak-
fingerprint, Blu-ray AACS Disc ID, CD MusicBrainz Disc ID, future matrix256
ARM-native fingerprints. The pre-existing single-value columns
(`disc_fingerprint`, `disc_fingerprint_algo`, `aacs_disc_id`) on `jobs` are
replaced by a per-(job, algo) row.

Reverse lookup ("have I ripped this disc before?") motivates the
(algo, value) index: a future scan flow checks whether a fingerprint has
been seen and can short-circuit identification. Not used in v3.0; the
shape is here to avoid migrating it later.

Revision ID: 0006_disc_fingerprints
Revises: 0005_job_poster_columns
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_disc_fingerprints"
down_revision: Union[str, None] = "0005_job_poster_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disc_fingerprints",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("algo", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_disc_fingerprints_job_id", "disc_fingerprints", ["job_id"])
    op.create_unique_constraint(
        "uq_disc_fingerprints_job_algo",
        "disc_fingerprints",
        ["job_id", "algo"],
    )
    op.create_index(
        "ix_disc_fingerprints_algo_value",
        "disc_fingerprints",
        ["algo", "value"],
    )

    # Backfill from the singleton columns into the new table before dropping.
    # No-ops on a fresh DB; preserves history for any v3-alpha installs.
    op.execute(
        """
        INSERT INTO disc_fingerprints (id, job_id, algo, value, created_at)
        SELECT
            'dfp_' || substr(md5(random()::text || jobs.id), 1, 24),
            jobs.id,
            jobs.disc_fingerprint_algo,
            jobs.disc_fingerprint,
            jobs.created_at
        FROM jobs
        WHERE jobs.disc_fingerprint IS NOT NULL
          AND jobs.disc_fingerprint_algo IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO disc_fingerprints (id, job_id, algo, value, created_at)
        SELECT
            'dfp_' || substr(md5(random()::text || jobs.id || 'aacs'), 1, 24),
            jobs.id,
            'aacs',
            jobs.aacs_disc_id,
            jobs.created_at
        FROM jobs
        WHERE jobs.aacs_disc_id IS NOT NULL
        """
    )

    op.drop_column("jobs", "disc_fingerprint")
    op.drop_column("jobs", "disc_fingerprint_algo")
    op.drop_column("jobs", "aacs_disc_id")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("disc_fingerprint", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("disc_fingerprint_algo", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("aacs_disc_id", sa.String(), nullable=True))
    op.drop_index("ix_disc_fingerprints_algo_value", table_name="disc_fingerprints")
    op.drop_constraint("uq_disc_fingerprints_job_algo", "disc_fingerprints", type_="unique")
    op.drop_index("ix_disc_fingerprints_job_id", table_name="disc_fingerprints")
    op.drop_table("disc_fingerprints")
