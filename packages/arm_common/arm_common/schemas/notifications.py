"""Wire schemas for notification channels + the in-app inbox.

The channel ``config`` is a discriminated union keyed on ``type``:
``apprise`` (url/fields, server-composed + masked), ``inapp`` (the UI
bell - no destination, delivery is an inbox-row write), and ``bash`` runs a
script from the scripts mount; the webhook arm remains deferred. ``last_*``
and ``id`` are server-managed and live only on the View.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppriseChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["apprise"] = "apprise"
    # Composed server-side when {service_id, fields} are supplied; may also
    # be a raw pasted apprise URL.
    url: str = ""
    service_id: str | None = None
    fields: dict[str, str | int | float | bool] | None = None


class InAppChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["inapp"] = "inapp"
    # No url/fields — delivery is a DB write (inbox row), not a destination.


class BashChannelConfig(BaseModel):
    """A script under the backend's ``/scripts`` mount (bare file name), run as
    ``bash <script> "<title>" "<body>"`` with ``ARM_*`` env vars plus one env
    var per declared input. ``secret_keys`` is server-written from the script
    header so masking does not depend on the file still existing; it is
    ignored on input (the field stays on the wire for round-tripping)."""

    model_config = ConfigDict(extra="ignore")
    type: Literal["bash"] = "bash"
    script: str
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    inputs: dict[str, str] = Field(default_factory=dict)
    secret_keys: list[str] = Field(default_factory=list)


class ScriptInput(BaseModel):
    key: str
    label: str
    required: bool = False
    secret: bool = False
    default: str = ""
    values: list[str] | None = None


class BashScriptSummary(BaseModel):
    name: str
    executable: bool
    description: str = ""


class BashScriptInfo(BashScriptSummary):
    size_bytes: int
    modified_at: datetime
    inputs: list[ScriptInput]
    preview: str


class BashRunResult(BaseModel):
    ok: bool
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    error: str | None


ChannelConfig = AppriseChannelConfig | InAppChannelConfig | BashChannelConfig


class ChannelTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    body: str | None = None
    inputs: dict[str, str] | None = None


class NotificationChannelView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    name: str
    enabled: bool
    config: dict[str, Any]  # masked on the way out by the router
    subscribed_events: list[str]
    templates: dict[str, ChannelTemplate]
    last_fired_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    created_by_user_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class NotificationChannelCreateRequest(BaseModel):
    type: Literal["apprise", "inapp", "bash"] = "apprise"
    name: str
    enabled: bool = True
    config: ChannelConfig = Field(discriminator="type")
    subscribed_events: list[str] = Field(default_factory=list)
    templates: dict[str, ChannelTemplate] = Field(default_factory=dict)


class NotificationChannelUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: ChannelConfig | None = Field(default=None, discriminator="type")
    subscribed_events: list[str] | None = None
    templates: dict[str, ChannelTemplate] | None = None


class NotificationTestRequest(BaseModel):
    """Ad-hoc test of an unsaved apprise or bash config."""

    config: AppriseChannelConfig | BashChannelConfig = Field(discriminator="type")
    event_type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_config_type(cls, data: Any) -> Any:
        """A config without ``type`` is an apprise config (pre-bash clients)."""
        if isinstance(data, dict):
            config = data.get("config")
            if isinstance(config, dict) and "type" not in config:
                data = {**data, "config": {**config, "type": "apprise"}}
        return data


class NotificationChannelTestRequest(BaseModel):
    """Test a saved channel, optionally with re-entered field values."""

    fields: dict[str, str | int | float | bool] = Field(default_factory=dict)
    event_type: str | None = None


class NotificationTestResult(BaseModel):
    ok: bool
    error: str | None = None


class BashPreviewRequest(BaseModel):
    """Resolve (and optionally run) a bash hook for one event with sample context."""

    config: BashChannelConfig
    event_type: str
    template: ChannelTemplate | None = None
    # When set, <hidden> secret inputs are filled from the stored channel.
    channel_id: str | None = None
    run: bool = False


class BashPreviewResult(BaseModel):
    title: str
    body: str
    inputs: dict[str, str]  # secrets masked
    env: dict[str, str]  # secrets masked
    argv: list[str]
    error: str | None = None
    result: BashRunResult | None = None


class CatalogField(BaseModel):
    key: str
    label: str
    type: str
    private: bool
    required: bool
    default: Any | None = None
    values: list[str] | None = None


class CatalogService(BaseModel):
    id: str
    name: str
    docs_url: str
    url_scheme: str
    required_fields: list[CatalogField]
    advanced_fields: list[CatalogField]


class ServiceCatalog(BaseModel):
    featured: list[str]
    services: list[CatalogService]


class ComposeUrlRequest(BaseModel):
    required: dict[str, Any] = Field(default_factory=dict)
    advanced: dict[str, Any] = Field(default_factory=dict)


class ComposeUrlResult(BaseModel):
    url: str


class NotificationDispatchLogView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel_id: str | None
    event_id: str | None
    event_type: str
    title: str
    body: str
    success: bool
    error: str | None
    created_at: datetime | None


class NotificationInboxView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str | None
    channel_id: str | None
    event_type: str
    title: str
    message: str
    job_id: str | None
    seen: bool
    cleared: bool
    seen_at: datetime | None
    cleared_at: datetime | None
    created_at: datetime | None


class NotificationInboxUpdateRequest(BaseModel):
    seen: bool | None = None
    cleared: bool | None = None


class NotificationInboxCountView(BaseModel):
    unseen: int
    seen: int
    cleared: int
    total: int


class EventTypeInfo(BaseModel):
    key: str
    label: str
    variables: list[str]
    default_title: str
    default_body: str
