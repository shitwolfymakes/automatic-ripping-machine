"""Session-routing wire schemas (gap analysis G-02/G-17).

`SessionRouteView` projects a `SessionRoute` row; `SessionRouteUpsert` is the
PUT body, keyed by `(media_type, disc_type)` — `disc_type=None` is the
wildcard route for that media_type.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from arm_common.enums import DiscType, MediaType


class SessionRouteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    media_type: MediaType
    disc_type: DiscType | None
    session_id: str
    created_at: datetime | None
    updated_at: datetime | None


class SessionRouteUpsert(BaseModel):
    media_type: MediaType
    disc_type: DiscType | None = None
    session_id: str
