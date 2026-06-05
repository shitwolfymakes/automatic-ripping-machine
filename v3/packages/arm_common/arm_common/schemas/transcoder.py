"""Phase 7 wire schemas: transcoder ↔ Backend.

The transcode container is short-lived and single-purpose; its API surface is
five endpoints (register / claim / heartbeat / complete / fail). The Backend
spawns one container per `transcode_tasks` row, the container runs the
encoder, and these schemas carry the state-machine transitions.
"""

from pydantic import BaseModel, Field

from arm_common.schemas.jobs import TrackView
from arm_common.schemas.sessions import (
    SessionView,
    TranscodePresetView,
    TranscodeTaskView,
)


class HardwareCaps(BaseModel):
    """Self-reported transcoder capabilities. Phase 7 (CPU-only) ignores these;
    Phase 7b consumes them for GPU dispatch + `gpus` row writes.
    """

    cpu_count: int = Field(ge=1)
    has_vaapi: bool = False
    has_nvenc: bool = False
    has_qsv: bool = False


class RegisterTranscoderRequest(BaseModel):
    task_id: str
    hostname: str
    hw_caps: HardwareCaps


class RegisterTranscoderResponse(BaseModel):
    """Bootstrap bundle the transcoder needs before it can claim + run.

    `raw_input_path` is the absolute path the transcoder should read from
    (`/raw/<job>/title_tNN.mkv` for video, `/raw/<job>/track_NN.wav` for
    audio, `/raw/<job>/dump.iso` for data). `media_root` plus the task's
    `output_path` is where the final file lands.
    """

    task: TranscodeTaskView
    session: SessionView
    transcode_preset: TranscodePresetView | None
    source_track: TrackView
    raw_input_path: str
    media_root: str


class ClaimTaskResponse(BaseModel):
    task: TranscodeTaskView


class HeartbeatRequest(BaseModel):
    progress_pct: int = Field(ge=0, le=100)
    current_pass: str | None = None
    eta_seconds: int | None = Field(default=None, ge=0)


class CompleteTaskRequest(BaseModel):
    output_path: str
    size_bytes: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    sha256: str | None = None


class FailTaskRequest(BaseModel):
    last_error: str = Field(min_length=1)
