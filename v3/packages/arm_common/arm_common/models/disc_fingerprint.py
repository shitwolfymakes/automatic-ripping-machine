"""Per-disc fingerprint pairs (algo, value) attached to a Job.

A single disc may carry multiple fingerprints — e.g. a DVD has a CRC64 (via
pydvdid) plus the volume label as a weak fingerprint; a Blu-ray would
carry an AACS Disc ID; a CD has a MusicBrainz Disc ID; future custom
algos like matrix256 slot in without a schema change.

Reverse lookup is the medium-term motivation: "have I ripped this disc
before?" needs an index on (algo, value), so this table is shaped for
that lookup pattern. (No reverse lookups in v3.0 itself yet — but the
canonical algo names (crc64, aacs, musicbrainz, matrix256) need to be
stable now to avoid migrating later.)
"""

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column
from arm_common.ulid import new_id


def _disc_fingerprint_id() -> str:
    return new_id("dfp")


class DiscFingerprint(SQLModel, table=True):
    __tablename__ = "disc_fingerprints"
    __table_args__ = (
        UniqueConstraint("job_id", "algo", name="uq_disc_fingerprints_job_algo"),
        Index("ix_disc_fingerprints_algo_value", "algo", "value"),
    )

    id: str = Field(default_factory=_disc_fingerprint_id, primary_key=True)
    job_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    # Free-form to permit new algos without migrations. Canonical values:
    # "crc64" (pydvdid DVD), "aacs" (Blu-ray AACS Disc ID), "musicbrainz"
    # (CD disc id), "matrix256" (future ARM-native fingerprint).
    algo: str = Field(sa_column=Column(String, nullable=False))
    value: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime | None = Field(sa_column=created_at_column())
