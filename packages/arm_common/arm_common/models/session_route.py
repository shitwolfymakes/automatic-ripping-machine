from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import DiscType, MediaType
from arm_common.ulid import new_id


def _session_route_id() -> str:
    return new_id("srt")


class SessionRoute(SQLModel, table=True):
    """Config-level (media_type, disc_type) -> session routing rule.

    Sits behind the per-rip explicit choice (`Job.pending_session_id`) and
    the per-drive default (`Drive.default_session_id`) in
    `resolve_routed_session_id` (gap analysis G-02/G-17): a route only
    applies when neither of those wins. `disc_type=None` is the wildcard row
    for a `media_type` (matches any disc type); an exact
    `(media_type, disc_type)` row is preferred over the wildcard.

    Unique on `(media_type, disc_type)` — see migration 0033's docstring for
    how NULL-distinctness is handled so at most one wildcard row can exist
    per media_type.
    """

    __tablename__ = "session_routes"
    __table_args__ = (
        UniqueConstraint(
            "media_type",
            "disc_type",
            name="uq_session_routes_media_disc",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: str = Field(default_factory=_session_route_id, primary_key=True)
    media_type: MediaType = Field(sa_column=enum_column(MediaType, "media_type"))
    # Nullable VARCHAR, app-validated like every enum column here (never a
    # Postgres enum). None = wildcard: matches any disc_type for this media_type.
    disc_type: DiscType | None = Field(default=None, sa_column=enum_column(DiscType, "disc_type", nullable=True))
    session_id: str = Field(sa_column=Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
