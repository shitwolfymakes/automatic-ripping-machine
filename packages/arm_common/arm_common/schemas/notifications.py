"""Wire schemas for notification channels (apprise arm only this batch).

The ``config`` union is apprise-only for now; ``type`` is constrained to
``"apprise"`` so create/patch reject webhook/bash until those arms ship.
``last_*`` and ``id`` are server-managed and live only on the View.
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
    type: Literal["apprise"] = "apprise"
    name: str
    enabled: bool = True
    config: AppriseChannelConfig
    subscribed_events: list[str] = Field(default_factory=list)
    templates: dict[str, ChannelTemplate] = Field(default_factory=dict)


class NotificationChannelUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: AppriseChannelConfig | None = None
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
