"""First-run setup walkthrough wire schemas (setup spec 2026-10-01 §6.1, §6.5)."""

from datetime import datetime

from pydantic import BaseModel

from arm_common.enums import MediaType, SetupStep, SetupStepState


class SetupStatusPublic(BaseModel):
    """Unauthenticated: the login page and the first-run guard read it."""

    first_run: bool
    arm_version: str


class SetupStepProgress(BaseModel):
    state: SetupStepState
    at: datetime | None = None


class SetupView(BaseModel):
    completed_at: datetime | None
    progress: dict[str, SetupStepProgress]
    current_step: SetupStep
    admin_default_password: bool
    checklist_dismissed: bool


class SetupStepUpdate(BaseModel):
    state: SetupStepState


class DiscRouteSummary(BaseModel):
    """What one kind of disc gets with no drive default and no per-rip choice."""

    kind: MediaType
    session_id: str | None = None
    session_name: str | None = None
    rip_summary: str | None = None
    transcode_summary: str | None = None
    output_template: str | None = None
