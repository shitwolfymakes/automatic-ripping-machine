"""Phase 8 wire schemas for drive mutations.

Read views still return the `Drive` SQLModel directly (the UI hand-types its
projection); this module only houses the update request body so the manual
PATCH endpoint and any future helpers can share validation rules.
"""

from pydantic import BaseModel, ConfigDict


class DriveUpdateRequest(BaseModel):
    """PATCH /api/drives/{id} body. Both fields optional + nullable.

    `default_session_id=None` (explicit null) clears the field; omitting it
    leaves it untouched. `extra="forbid"` keeps the API honest — UI typos
    surface as 422 instead of being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    default_session_id: str | None = None
