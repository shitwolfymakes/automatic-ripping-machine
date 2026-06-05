"""Phase 6 wire schemas: session/preset CRUD + apply + collision detection.

Read views (`SessionView`, `RipPresetView`, `TranscodePresetView`) project the
SQLModel rows for the UI; create/update requests are deliberately split so
server-managed fields (`is_builtin`, `created_by_user_id`, timestamps) can't
be smuggled in.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import (
    ContainerFormat,
    HwPreference,
    IdentificationMode,
    MediaType,
    OutputMode,
    SessionApplicationStatus,
    TrackSelection,
    TranscodeTaskStatus,
    TranscodeTool,
    VideoCodec,
)


class TrackFilters(BaseModel):
    """Declarative custom-track-selection rules persisted as `rip_presets.track_filters_json`.

    All conditions ANDed. `title_indices` (when set) restricts the candidate
    pool first; duration filters and `title_indices_exclude` apply after.
    """

    min_duration_seconds: int | None = Field(default=None, ge=0)
    max_duration_seconds: int | None = Field(default=None, ge=0)
    title_indices: list[int] | None = None
    title_indices_exclude: list[int] | None = None


# --- RipPreset ---------------------------------------------------------------


class RipPresetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    media_type: MediaType
    is_builtin: bool
    track_selection: TrackSelection
    identification_mode: IdentificationMode
    output_mode: OutputMode
    track_filters_json: dict[str, Any] | None
    created_by_user_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class RipPresetCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    media_type: MediaType
    track_selection: TrackSelection
    identification_mode: IdentificationMode
    output_mode: OutputMode
    track_filters_json: dict[str, Any] | None = None


class RipPresetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    track_selection: TrackSelection | None = None
    identification_mode: IdentificationMode | None = None
    output_mode: OutputMode | None = None
    track_filters_json: dict[str, Any] | None = None


# --- TranscodePreset ---------------------------------------------------------


class TranscodePresetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    media_type: MediaType
    is_builtin: bool
    tool: TranscodeTool
    preset_ref: str | None
    preset_json: dict[str, Any] | None
    container: ContainerFormat
    codec: VideoCodec | None
    hw_preference: HwPreference | None
    extra_args: str | None
    created_by_user_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class TranscodePresetCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    media_type: MediaType
    tool: TranscodeTool
    preset_ref: str | None = None
    preset_json: dict[str, Any] | None = None
    container: ContainerFormat
    codec: VideoCodec | None = None
    hw_preference: HwPreference | None = None
    extra_args: str | None = None


class TranscodePresetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    tool: TranscodeTool | None = None
    preset_ref: str | None = None
    preset_json: dict[str, Any] | None = None
    container: ContainerFormat | None = None
    codec: VideoCodec | None = None
    hw_preference: HwPreference | None = None
    extra_args: str | None = None


# --- Session -----------------------------------------------------------------


class SessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    media_type: MediaType
    is_builtin: bool
    rip_preset_id: str
    transcode_preset_id: str | None
    output_path_template: str
    overrides_json: dict[str, Any] | None
    created_by_user_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class SessionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    media_type: MediaType
    rip_preset_id: str
    transcode_preset_id: str | None = None
    output_path_template: str = Field(min_length=1)
    overrides_json: dict[str, Any] | None = None


class SessionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    rip_preset_id: str | None = None
    transcode_preset_id: str | None = None
    output_path_template: str | None = Field(default=None, min_length=1)
    overrides_json: dict[str, Any] | None = None


class SessionCloneRequest(BaseModel):
    name: str = Field(min_length=1)


# --- SessionApplication / TranscodeTask --------------------------------------


class SessionApplicationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    job_id: str
    status: SessionApplicationStatus
    overrides_json: dict[str, Any] | None
    overwrite: bool
    created_by_user_id: str | None
    created_at: datetime | None
    completed_at: datetime | None


class TranscodeTaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_application_id: str
    source_track_id: str
    status: TranscodeTaskStatus
    output_path: str | None
    progress_pct: int
    attempts: int
    claimed_by: str | None
    claim_heartbeat_at: datetime | None
    last_error: str | None
    created_at: datetime | None
    updated_at: datetime | None


# --- Apply -------------------------------------------------------------------


class ApplySessionRequest(BaseModel):
    session_id: str
    overwrite: bool = False


class CollisionInfo(BaseModel):
    output_path: str
    existing_task_id: str | None
    on_filesystem: bool
    # Why the path was flagged: an existing live task in the DB, an existing
    # file on disk under MEDIA_ROOT, or two tracks in the same apply request
    # resolving to the same path (template missing `{track}` for a multi-track rip).
    reason: Literal["existing_task", "on_disk", "duplicate_in_request"]


class ApplySessionResponse(BaseModel):
    session_application: SessionApplicationView
    tasks: list[TranscodeTaskView]
    collisions: list[CollisionInfo]
    idempotent: bool


# --- Template preview --------------------------------------------------------


class TemplatePreviewRequest(BaseModel):
    template: str = Field(min_length=1)
    media_type: MediaType
    has_transcode_preset: bool = True


class TemplatePreviewResponse(BaseModel):
    expansion: str
