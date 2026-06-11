"""Wire schemas for notification channels + the in-app inbox.

The channel ``config`` is a discriminated union keyed on ``type``:
``apprise`` (url/fields, server-composed + masked) and ``inapp`` (the UI
bell — no destination, delivery is an inbox-row write). webhook/bash arms
remain deferred. ``last_*`` and ``id`` are server-managed and live only on
the View.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AppriseChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["apprise"] = "apprise"
    # Composed server-side when {service_id, fields} are supplied; may also
    # be a raw pasted apprise URL.
    url: str = ""
    service_id: str | None = None
    fields: dict[str, str] | None = None


class InAppChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["inapp"] = "inapp"
    # No url/fields — delivery is a DB write (inbox row), not a destination.


class ChannelTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    body: str | None = None


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
    type: Literal["apprise", "inapp"] = "apprise"
    name: str
    enabled: bool = True
    config: AppriseChannelConfig | InAppChannelConfig = Field(discriminator="type")
    subscribed_events: list[str] = Field(default_factory=list)
    templates: dict[str, ChannelTemplate] = Field(default_factory=dict)


class NotificationChannelUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: AppriseChannelConfig | InAppChannelConfig | None = Field(default=None, discriminator="type")
    subscribed_events: list[str] | None = None
    templates: dict[str, ChannelTemplate] | None = None


class NotificationTestRequest(BaseModel):
    """Ad-hoc test of an unsaved apprise config."""

    config: AppriseChannelConfig
    event_type: str | None = None


class NotificationChannelTestRequest(BaseModel):
    """Test a saved channel, optionally with re-entered field values."""

    fields: dict[str, str] = Field(default_factory=dict)
    event_type: str | None = None


class NotificationTestResult(BaseModel):
    ok: bool
    error: str | None = None


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
